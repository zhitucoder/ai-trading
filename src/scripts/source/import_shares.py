#!/home/rick/miniconda3/envs/aitrading/bin/python
"""导入总股本/流通股本/限售股本到 stock_shares 表

数据源优先级：
  1. 东方财富 API (quality=high) — 实时行情接口，总股本和流通股本
  2. pytdx gpcw 财务数据 (quality=medium) — 已有 fin_shareholder 数据，需单位转换
  3. 人工维护最低优先级

用法:
  python import_shares.py              # 默认从 EM API 导入
  python import_shares.py --source em   # 指定东方财富 API
  python import_shares.py --source pytdx  # 仅用 pytdx 已有数据
"""

import sys
import time
import argparse

import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4', cursorclass=DictCursor)


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def create_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_shares (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
            total_shares BIGINT COMMENT '总股本(股)',
            float_shares BIGINT COMMENT '流通股本(股)',
            non_float_shares BIGINT COMMENT '非流通/限售股本(股)',
            source VARCHAR(20) NOT NULL DEFAULT 'em' COMMENT '数据来源: em/pytdx/manual',
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_stock (stock_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股本结构（总股本/流通股本/限售股本）'
    """)


def import_from_fin_shareholder(cursor) -> int:
    """从 fin_shareholder 导入（pytdx gpcw），修正单位问题

    pytdx 字段约定：
      total_shares — 单位是"万股"
      float_shares — 单位是"股"（FIELD_MAP 注释写万股是错误的）
    """
    sql = """
        INSERT IGNORE INTO stock_shares (stock_code, total_shares, float_shares, non_float_shares, source, update_time)
        SELECT 
            s.stock_code,
            ROUND(s.total_shares * 10000) AS total_shares,
            ROUND(s.float_shares) AS float_shares,
            ROUND(GREATEST(s.total_shares * 10000 - s.float_shares, 0)) AS non_float_shares,
            'pytdx' AS source,
            NOW() AS update_time
        FROM fin_shareholder s
        INNER JOIN (
            SELECT stock_code, MAX(report_date) AS max_date
            FROM fin_shareholder
            WHERE total_shares IS NOT NULL AND float_shares IS NOT NULL
            GROUP BY stock_code
        ) latest ON s.stock_code = latest.stock_code AND s.report_date = latest.max_date
        WHERE s.total_shares IS NOT NULL AND s.float_shares IS NOT NULL
          AND s.total_shares > 0 AND s.float_shares > 0
          AND s.total_shares * 10000 >= s.float_shares
    """
    cursor.execute(sql)
    return cursor.rowcount


def import_from_em_api(cursor) -> int:
    """从东方财富 API 导入（实时行情）

    使用 push2.eastmoney.com 的接口，获取所有A股的实时总股本和流通股本。
    """
    import requests

    total_imported = 0
    page = 1
    page_size = 500

    while True:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": str(page),
            "pz": str(page_size),
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f12,f14,f20,f21,f84,f85,f100,f116"
        }
        try:
            resp = requests.get(url, params=params, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            data = resp.json()
        except Exception as e:
            print(f"  EM API 请求失败 (page={page}): {e}")
            break

        if not data.get('data') or not data['data'].get('diff'):
            break

        rows = data['data']['diff']
        if not rows:
            break

        batch = []
        for r in rows:
            stock_code = str(r.get('f12', ''))
            total_shares = r.get('f84')   # 总股本
            float_shares = r.get('f85')   # 流通股本
            if not stock_code or not total_shares or not float_shares:
                continue
            total = int(total_shares)
            f_float = int(float_shares)
            non_float = max(total - f_float, 0)
            batch.append({
                'stock_code': stock_code,
                'total_shares': total,
                'float_shares': f_float,
                'non_float_shares': non_float,
                'source': 'em'
            })

        if batch:
            cols = ['stock_code', 'total_shares', 'float_shares', 'non_float_shares', 'source']
            ph = ', '.join([f'%({c})s' for c in cols])
            sql = f"""
                INSERT INTO stock_shares ({', '.join(cols)}, update_time)
                VALUES ({ph}, NOW())
                ON DUPLICATE KEY UPDATE
                    total_shares = VALUES(total_shares),
                    float_shares = VALUES(float_shares),
                    non_float_shares = VALUES(non_float_shares),
                    source = VALUES(source),
                    update_time = NOW()
            """
            cursor.executemany(sql, batch)
            conn.commit()
            total_imported += len(batch)

        print(f"  page {page}: {len(rows)} rows, total {total_imported}")
        page += 1

        if len(rows) < page_size:
            break

    return total_imported


def validate(cursor):
    """数据质量校验"""
    issues = []

    cursor.execute("SELECT COUNT(*) as cnt FROM stock_shares")
    total = cursor.fetchone()['cnt']
    cursor.execute("SELECT COUNT(*) as cnt FROM stocks")
    stocks_cnt = cursor.fetchone()['cnt']
    issues.append(f"覆盖率: {total}/{stocks_cnt} = {total/stocks_cnt*100:.1f}%")

    cursor.execute("""
        SELECT COUNT(*) as cnt FROM stock_shares
        WHERE total_shares IS NULL OR float_shares IS NULL OR total_shares <= 0 OR float_shares <= 0
    """)
    bad = cursor.fetchone()['cnt']
    if bad:
        issues.append(f"⚠️ 异常数据（空值或非正数）: {bad} 条")

    cursor.execute("SELECT COUNT(*) as cnt FROM stock_shares WHERE total_shares < float_shares")
    bad2 = cursor.fetchone()['cnt']
    if bad2:
        issues.append(f"⚠️ 异常数据（总股本 < 流通股本）: {bad2} 条")

    cursor.execute("""
        SELECT COUNT(*) as cnt FROM stock_shares
        WHERE float_shares / total_shares < 0.05 AND total_shares > 0
    """)
    low_float = cursor.fetchone()['cnt']
    if low_float:
        issues.append(f"⚠️ 流通比例 < 5% 的股票: {low_float} 只（数据可能异常）")

    for msg in issues:
        print(f"  {msg}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='导入股本结构数据')
    parser.add_argument('--source', choices=['em', 'pytdx', 'auto'], default='auto',
                        help='数据来源: em(东方财富), pytdx(通达信), auto(先em再pytdx)')
    args = parser.parse_args()

    conn = get_conn()
    cursor = conn.cursor()

    print("创建/检查 stock_shares 表...")
    create_table(cursor)

    source = args.source
    if source == 'auto':
        print("\n尝试 EM API...")
        cnt = import_from_em_api(cursor)
        if cnt == 0:
            print("EM API 不可用，回退到 pytdx 数据...")
            cnt = import_from_fin_shareholder(cursor)
            print(f"pytdx 导入: {cnt} 条")
        else:
            print(f"EM API 导入: {cnt} 条")
    elif source == 'em':
        cnt = import_from_em_api(cursor)
        print(f"EM API 导入: {cnt} 条")
    else:
        cnt = import_from_fin_shareholder(cursor)
        print(f"pytdx 导入: {cnt} 条")

    print("\n=== 数据质量 ===")
    validate(cursor)

    cursor.close()
    conn.close()
    print("\n完成!")
