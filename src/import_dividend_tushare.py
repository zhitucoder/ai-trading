#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从 Tushare Pro 下载分红送股数据，存入 MySQL dividend_tushare 表。

数据接口:
  dividend  分红送股  https://tushare.pro/document/2?doc_id=103

用法:
  python import_dividend_tushare.py
  python import_dividend_tushare.py --since 20240101
"""

import argparse
import math
import os
import time

import pymysql
import tushare as ts
from pymysql.cursors import DictCursor

from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4', cursorclass=DictCursor)

API_KEY = os.environ.get('TUSHARE_TOKEN', '')
if not API_KEY:
    raise SystemExit('缺少 TUSHARE_TOKEN 环境变量')

SLEEP = 0.2

FIELDS = 'ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,' \
         'cash_div,cash_div_tax,record_date,ex_date,pay_date,div_listdate,' \
         'imp_ann_date,base_date,base_share'


def to_db(v):
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except TypeError:
        pass
    return v


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def create_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dividend_tushare (
            id              BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
            ts_code         VARCHAR(12)   NOT NULL COMMENT 'TS股票代码（如600519.SH）',
            end_date        VARCHAR(8)    COMMENT '分红年度（YYYYMMDD）',
            ann_date        VARCHAR(8)    COMMENT '公告日（预案/决案，YYYYMMDD）',
            div_proc        VARCHAR(16)   COMMENT '实施进度（预案/决案/实施）',
            stk_div         DECIMAL(12,4) COMMENT '每股送转（股）',
            stk_bo_rate     DECIMAL(12,4) COMMENT '每股送股比例',
            stk_co_rate     DECIMAL(12,4) COMMENT '每股转增比例',
            cash_div        DECIMAL(12,4) COMMENT '每股分红（税后，元）',
            cash_div_tax    DECIMAL(12,4) COMMENT '每股分红（税前，元）',
            record_date     VARCHAR(8)    COMMENT '股权登记日（YYYYMMDD）',
            ex_date         VARCHAR(8)    COMMENT '除权除息日（YYYYMMDD）',
            pay_date        VARCHAR(8)    COMMENT '派息日（YYYYMMDD）',
            div_listdate    VARCHAR(8)    COMMENT '红股上市日（YYYYMMDD）',
            imp_ann_date    VARCHAR(8)    COMMENT '实施公告日（YYYYMMDD）',
            base_date       VARCHAR(8)    COMMENT '基准日（YYYYMMDD）',
            base_share      DECIMAL(20,4) COMMENT '基准股本（万股）',
            update_time     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_ts_ann (ts_code, end_date, ann_date),
            KEY idx_ex_date (ex_date),
            KEY idx_end_date (end_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分红送股数据（数据来源：Tushare Pro dividend接口，doc_id=103）'
    """)


def get_stock_list():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, exchange FROM stocks WHERE exchange IN ('sh', 'sz')")
            rows = cur.fetchall()
            result = []
            for r in rows:
                suffix = '.SH' if r['exchange'] == 'sh' else '.SZ'
                result.append(r['stock_code'] + suffix)
            return result
    finally:
        conn.close()


def save_rows(rows):
    if not rows:
        return
    sql = """
        INSERT INTO dividend_tushare
            (ts_code, end_date, ann_date, div_proc, stk_div, stk_bo_rate,
             stk_co_rate, cash_div, cash_div_tax, record_date, ex_date,
             pay_date, div_listdate, imp_ann_date, base_date, base_share)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            div_proc=VALUES(div_proc), stk_div=VALUES(stk_div),
            stk_bo_rate=VALUES(stk_bo_rate), stk_co_rate=VALUES(stk_co_rate),
            cash_div=VALUES(cash_div), cash_div_tax=VALUES(cash_div_tax),
            record_date=VALUES(record_date), ex_date=VALUES(ex_date),
            pay_date=VALUES(pay_date), div_listdate=VALUES(div_listdate),
            imp_ann_date=VALUES(imp_ann_date), base_date=VALUES(base_date),
            base_share=VALUES(base_share), update_time=CURRENT_TIMESTAMP
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', type=str, default=None,
                        help='只下载公告日 >= 该日期（YYYYMMDD）的分红记录')
    parser.add_argument('--codes', type=str, default=None,
                        help='只下载指定股票代码（逗号分隔，用于测试）')
    args = parser.parse_args()

    pro = ts.pro_api(API_KEY)

    conn = get_conn()
    try:
        cur = conn.cursor()
        create_table(cur)
        conn.commit()
    finally:
        conn.close()

    if args.codes:
        stock_list = [c.strip() for c in args.codes.split(',')]
    else:
        stock_list = get_stock_list()

    print(f'股票总数: {len(stock_list)}', flush=True)

    total_saved = 0
    fail = 0

    for i, ts_code in enumerate(stock_list):
        try:
            df = pro.dividend(ts_code=ts_code, fields=FIELDS)
        except Exception as e:
            print(f'  [{i+1}/{len(stock_list)}] {ts_code}: FAIL {e}', flush=True)
            fail += 1
            time.sleep(1)
            continue

        if df is None or len(df) == 0:
            continue

        rows_to_save = []
        for _, r in df.iterrows():
            ann_date = str(r.get('ann_date') or '')
            if args.since and ann_date < args.since:
                continue
            rows_to_save.append(tuple(to_db(r[c]) for c in (
                'ts_code', 'end_date', 'ann_date', 'div_proc', 'stk_div',
                'stk_bo_rate', 'stk_co_rate', 'cash_div', 'cash_div_tax',
                'record_date', 'ex_date', 'pay_date', 'div_listdate',
                'imp_ann_date', 'base_date', 'base_share')))

        if rows_to_save:
            save_rows(rows_to_save)
            total_saved += len(rows_to_save)

        if (i + 1) % 200 == 0:
            print(f'  进度: {i+1}/{len(stock_list)} 已保存: {total_saved}', flush=True)

        time.sleep(SLEEP)

    print(f'完成: 保存 {total_saved} 条，失败 {fail}', flush=True)


if __name__ == '__main__':
    main()
