#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从 Tushare Pro 下载十大流通股东数据，筛选国家队（社保/证金/汇金/保险）持仓。

数据接口:
  top10_floatholders  前十大流通股东  https://tushare.pro/document/2?doc_id=62

用法:
  python import_top10_holders.py
  python import_top10_holders.py --start 20240101
  python import_top10_holders.py --quarter 20240930
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

SLEEP = 0.15

NATIONAL_TEAM_TYPES = [
    '社保基金、社保机构',
    '基本养老保险基金',
    '保险投资组合',
    '金融机构—保险公司',
    '保险资管产品',
]

NATIONAL_TEAM_KEYWORDS = [
    '中央汇金', '中国证券金融', '证金公司',
    '社保', '养老保险',
    '人寿保险', '保险公司',
    '太平洋', '平安保险', '中国人保', '新华保险',
    '泰康', '阳光保险',
]


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
        CREATE TABLE IF NOT EXISTS top10_float_holders (
            id              BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
            ts_code         VARCHAR(12)   NOT NULL COMMENT 'TS股票代码（如600519.SH）',
            ann_date        VARCHAR(8)    COMMENT '公告日期（YYYYMMDD）',
            end_date        VARCHAR(8)    NOT NULL COMMENT '报告期（YYYYMMDD，季度末日期）',
            holder_name     VARCHAR(128)  NOT NULL COMMENT '股东名称',
            hold_amount     DECIMAL(20,4) COMMENT '持股数量（股）',
            hold_ratio      DECIMAL(10,4) COMMENT '持股占总股本比例（%）',
            hold_float_ratio DECIMAL(10,4) COMMENT '持股占流通股比例（%）',
            hold_change     DECIMAL(20,4) COMMENT '持股变动（股，正数增持负数减持）',
            holder_type     VARCHAR(32)   COMMENT '股东类型（社保基金/保险投资组合/基本养老保险基金等）',
            update_time     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_holder (ts_code, end_date, holder_name),
            KEY idx_end_date (end_date),
            KEY idx_holder_name (holder_name(64)),
            KEY idx_holder_type (holder_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='十大流通股东-国家队持仓（数据来源：Tushare Pro top10_floatholders）'
    """)


def is_national_team(row):
    holder_type = row.get('holder_type', '') or ''
    holder_name = row.get('holder_name', '') or ''

    if holder_type in NATIONAL_TEAM_TYPES:
        return True

    for kw in NATIONAL_TEAM_KEYWORDS:
        if kw in holder_name:
            return True

    return False


def save_rows(rows):
    if not rows:
        return
    sql = """
        INSERT INTO top10_float_holders
            (ts_code, ann_date, end_date, holder_name, hold_amount,
             hold_ratio, hold_float_ratio, hold_change, holder_type)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            ann_date=VALUES(ann_date), hold_amount=VALUES(hold_amount),
            hold_ratio=VALUES(hold_ratio), hold_float_ratio=VALUES(hold_float_ratio),
            hold_change=VALUES(hold_change), holder_type=VALUES(holder_type),
            update_time=CURRENT_TIMESTAMP
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()


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


def quarters_in_range(start, end):
    quarters = []
    for year in range(int(start[:4]), int(end[:4]) + 1):
        for q in ['0331', '0630', '0930', '1231']:
            period = f'{year}{q}'
            if start <= period <= end:
                quarters.append(period)
    return quarters


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, default='20240101',
                        help='开始日期（YYYYMMDD，默认20240101）')
    parser.add_argument('--end', type=str, default=None,
                        help='结束日期（YYYYMMDD，默认今天）')
    parser.add_argument('--quarter', type=str, default=None,
                        help='只下载指定季度（如20240930）')
    parser.add_argument('--all', action='store_true',
                        help='下载全部数据（不限股东类型）')
    args = parser.parse_args()

    pro = ts.pro_api(API_KEY)

    conn = get_conn()
    try:
        cur = conn.cursor()
        create_table(cur)
        conn.commit()
    finally:
        conn.close()

    stock_list = get_stock_list()
    print(f'沪深股票总数: {len(stock_list)}', flush=True)

    if args.quarter:
        quarters = [args.quarter]
    else:
        end_date = args.end or time.strftime('%Y%m%d')
        quarters = quarters_in_range(args.start, end_date)

    print(f'下载季度: {quarters}', flush=True)
    print(flush=True)

    total_saved = 0

    for period in quarters:
        period_saved = 0
        print(f'--- {period} ---', flush=True)

        for i, ts_code in enumerate(stock_list):
            try:
                df = pro.top10_floatholders(ts_code=ts_code, period=period)
            except Exception as e:
                print(f'  [错误] {ts_code}: {e}', flush=True)
                time.sleep(1)
                continue

            if df is None or len(df) == 0:
                continue

            rows_to_save = []
            for _, r in df.iterrows():
                row_data = {
                    'ts_code': r.get('ts_code'),
                    'ann_date': r.get('ann_date'),
                    'end_date': r.get('end_date'),
                    'holder_name': r.get('holder_name'),
                    'hold_amount': r.get('hold_amount'),
                    'hold_ratio': r.get('hold_ratio'),
                    'hold_float_ratio': r.get('hold_float_ratio'),
                    'hold_change': r.get('hold_change'),
                    'holder_type': r.get('holder_type'),
                }
                if args.all or is_national_team(row_data):
                    rows_to_save.append(tuple(to_db(row_data[c]) for c in (
                        'ts_code', 'ann_date', 'end_date', 'holder_name', 'hold_amount',
                        'hold_ratio', 'hold_float_ratio', 'hold_change', 'holder_type')))

            if rows_to_save:
                save_rows(rows_to_save)
                period_saved += len(rows_to_save)
                total_saved += len(rows_to_save)

            if (i + 1) % 200 == 0:
                print(f'  进度: {i+1}/{len(stock_list)} 已保存: {total_saved}', flush=True)

            time.sleep(SLEEP)

        print(f'  {period} 完成，本季度保存: {period_saved}条，累计: {total_saved}条', flush=True)
        print(flush=True)

    print(f'全部完成，共保存 {total_saved} 条国家队持仓记录', flush=True)


if __name__ == '__main__':
    main()
