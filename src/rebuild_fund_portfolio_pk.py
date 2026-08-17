#!/home/rick/miniconda3/envs/aitrading/bin/python
"""重建 fund_portfolio 表：以 (ts_code, end_date, symbol, ann_date) 联合主键替代 id 自增主键。

用法: python rebuild_fund_portfolio_pk.py
"""

import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4', cursorclass=DictCursor)

NEW_TABLE = 'fund_portfolio_new'


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def main():
    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) c FROM fund_portfolio")
        total = cur.fetchone()['c']
        cur.execute("SELECT COUNT(DISTINCT ts_code,end_date,symbol,ann_date) c FROM fund_portfolio")
        uniq = cur.fetchone()['c']
        assert total == uniq, f'数据存在重复({total}!={uniq})，拒绝重建'
        print(f'[rebuild] 原表 {total} 行，联合键唯一，开始重建', flush=True)

        cur.execute(f"DROP TABLE IF EXISTS {NEW_TABLE}")
        cur.execute(f"""
            CREATE TABLE {NEW_TABLE} (
                ts_code         VARCHAR(12)  NOT NULL COMMENT 'TS基金代码',
                ann_date        VARCHAR(8)   NOT NULL COMMENT '公告日期（YYYYMMDD）',
                end_date        VARCHAR(8)   NOT NULL COMMENT '报告期截止日期（YYYYMMDD，季度末）',
                symbol          VARCHAR(12)  NOT NULL COMMENT '股票代码（如600519.SH）',
                mkv             DECIMAL(20,4) COMMENT '持有股票市值(元)',
                amount          DECIMAL(20,4) COMMENT '持有股票数量(股)',
                stk_mkv_ratio   DECIMAL(10,4) COMMENT '占股票市值比(%)',
                stk_float_ratio DECIMAL(10,4) COMMENT '占流通股本比例(%)',
                update_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (ts_code, end_date, symbol, ann_date),
                KEY idx_end_date (end_date),
                KEY idx_symbol (symbol)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='公募基金持仓（季报，数据来源：Tushare Pro fund_portfolio 接口，联合主键防重复）'
        """)
        conn.commit()

        cur.execute(f"INSERT IGNORE INTO {NEW_TABLE} "
                    "(ts_code, ann_date, end_date, symbol, mkv, amount, stk_mkv_ratio, stk_float_ratio, update_time) "
                    "SELECT ts_code, ann_date, end_date, symbol, mkv, amount, stk_mkv_ratio, stk_float_ratio, update_time "
                    "FROM fund_portfolio")
        conn.commit()
        cur.execute(f"SELECT COUNT(*) c FROM {NEW_TABLE}")
        new_cnt = cur.fetchone()['c']
        print(f'[rebuild] 新表 {new_cnt} 行', flush=True)

        cur.execute("RENAME TABLE fund_portfolio TO fund_portfolio_old, "
                    f"{NEW_TABLE} TO fund_portfolio")
        conn.commit()
        print('[rebuild] 新表已生效，旧表改名 fund_portfolio_old', flush=True)

        cur.execute("SELECT COUNT(*) c FROM fund_portfolio")
        print(f'[rebuild] 完成，当前 fund_portfolio = {cur.fetchone()["c"]} 行', flush=True)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
