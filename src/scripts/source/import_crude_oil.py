#!/home/rick/miniconda3/envs/aitrading/bin/python
"""导入WTI（美原油）与布伦特原油日线数据到 MySQL

数据源: akshare (新浪外盘期货)
  - WTI:  symbol = 'CL'  (NYMEX WTI Crude Oil, 主力连续)
  - Brent: symbol = 'OIL' (ICE Brent Crude Oil, 主力连续)

表结构: crude_oil_daily
  - 每日 OHLCV + 持仓量 + 结算价
  - variety 字段区分 WTI / Brent
  - update_time 记录每次写入时间

用法:
  python import_crude_oil.py              # 全量导入（自动跳过已有日期）
  python import_crude_oil.py --force      # 强制重建（先删表再全量导入）
  python import_crude_oil.py --since 2026-01-01  # 仅导入指定日期之后
"""

import argparse
import pymysql
import pandas as pd
from datetime import datetime

DB_CONFIG = dict(
    host='127.0.0.1', port=3306, user='root',
    password='aitrading123', database='ai_trading',
    charset='utf8mb4',
)

TABLE_NAME = 'crude_oil_daily'

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    variety VARCHAR(10) NOT NULL COMMENT '品种: WTI/Brent',
    trade_date DATE NOT NULL COMMENT '交易日期',
    open_price DECIMAL(10,2) COMMENT '开盘价(美元/桶)',
    high_price DECIMAL(10,2) COMMENT '最高价(美元/桶)',
    low_price DECIMAL(10,2) COMMENT '最低价(美元/桶)',
    close_price DECIMAL(10,2) COMMENT '收盘价(美元/桶)',
    volume BIGINT COMMENT '成交量(手)',
    position BIGINT COMMENT '持仓量(手)',
    settlement_price DECIMAL(10,2) COMMENT '结算价(美元/桶)',
    source VARCHAR(20) NOT NULL DEFAULT 'akshare_sina' COMMENT '数据来源',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_variety_date (variety, trade_date),
    KEY idx_trade_date (trade_date),
    KEY idx_variety (variety)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='WTI与布伦特原油主力连续日线行情(akshare/新浪)'
"""

VARIETY_MAP = {
    'CL': 'WTI',
    'OIL': 'Brent',
}


def fetch_data(symbol: str) -> pd.DataFrame:
    """从 akshare 下载外盘期货历史日线"""
    import akshare as ak
    df = ak.futures_foreign_hist(symbol=symbol)
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df


def get_existing_dates(conn, variety: str) -> set:
    """获取表中已有的日期集合"""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT trade_date FROM {TABLE_NAME} WHERE variety = %s",
            (variety,),
        )
        return {row[0] for row in cur.fetchall()}


def upsert_rows(conn, variety: str, df: pd.DataFrame, since: str = None) -> int:
    """插入/更新数据行，返回新增行数"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = []
    for _, r in df.iterrows():
        trade_date = r['date']
        if since and str(trade_date) < since:
            continue
        rows.append((
            variety,
            trade_date,
            r.get('open'),
            r.get('high'),
            r.get('low'),
            r.get('close'),
            int(r['volume']) if pd.notna(r.get('volume')) else None,
            int(r['position']) if pd.notna(r.get('position')) else None,
            r.get('settlement') if 'settlement' in r.index and pd.notna(r.get('settlement')) else None,
            'akshare_sina',
            now,
        ))

    if not rows:
        return 0

    sql = f"""
        INSERT INTO {TABLE_NAME}
            (variety, trade_date, open_price, high_price, low_price, close_price,
             volume, position, settlement_price, source, update_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            open_price = VALUES(open_price),
            high_price = VALUES(high_price),
            low_price = VALUES(low_price),
            close_price = VALUES(close_price),
            volume = VALUES(volume),
            position = VALUES(position),
            settlement_price = VALUES(settlement_price),
            source = VALUES(source),
            update_time = VALUES(update_time)
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def update_crude_oil(force=False, since=None):
    """幂等更新原油数据，返回 dict 结果供 API 调用"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            if force:
                cur.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
            cur.execute(CREATE_TABLE_SQL)

        total = 0
        details = []
        for symbol, variety in VARIETY_MAP.items():
            try:
                df = fetch_data(symbol)
            except Exception as e:
                details.append({'variety': variety, 'error': str(e)})
                continue

            existing = get_existing_dates(conn, variety) if not force else set()
            new_df = df[~df['date'].isin(existing)]
            count = upsert_rows(conn, variety, new_df, since=since)
            conn.commit()
            total += count
            details.append({
                'variety': variety,
                'total_rows': len(df),
                'new_rows': count,
                'date_from': str(df['date'].min()),
                'date_to': str(df['date'].max()),
            })

        return {'status': 'ok', 'total': total, 'details': details}
    finally:
        conn.close()


def get_crude_oil_status():
    """查询原油数据状态，返回 dict 供 API 使用"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT variety, COUNT(*) AS cnt, MIN(trade_date) AS min_date,
                       MAX(trade_date) AS max_date, MAX(update_time) AS last_update
                FROM {TABLE_NAME}
                GROUP BY variety
            """)
            detail = []
            for row in cur.fetchall():
                detail.append({
                    'variety': row[0],
                    'rows': row[1],
                    'min_date': str(row[2]) if row[2] else '',
                    'max_date': str(row[3]) if row[3] else '',
                    'last_update': str(row[4]) if row[4] else '',
                })
            return {'status': 'ok', 'detail': detail}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='导入WTI与布伦特原油日线数据')
    parser.add_argument('--force', action='store_true', help='强制重建（先删表再全量导入）')
    parser.add_argument('--since', type=str, default=None, help='仅导入指定日期之后的数据，格式 YYYY-MM-DD')
    args = parser.parse_args()

    result = update_crude_oil(force=args.force, since=args.since)
    for d in result.get('details', []):
        if 'error' in d:
            print(f"[ERROR] {d['variety']}: {d['error']}")
        else:
            print(f"[OK] {d['variety']}: {d['total_rows']} 行, 新增 {d['new_rows']}, {d['date_from']} ~ {d['date_to']}")
    print(f"\n[DONE] 共写入 {result['total']} 行")


if __name__ == '__main__':
    main()
