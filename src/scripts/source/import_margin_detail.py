#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从 Tushare Pro 下载融资融券交易明细数据，存入 MySQL。

数据接口:
  margin_detail  融资融券交易明细  https://tushare.pro/document/2?doc_id=59

用法:
  python import_margin_detail.py
  python import_margin_detail.py --start 20210101
  python import_margin_detail.py --start 20210101 --end 20211231
"""

import argparse
import math
import os
import time
from datetime import datetime, timedelta

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
    raise SystemExit('缺少 TUSHARE_TOKEN 环境变量（.env 中配置 TUSHARE_TOKEN=你的tushare token）')

PAGE_SIZE = 6000  # margin_detail 单次最大6000条
SLEEP = 0.3       # 两次请求间隔（秒）


def to_db(v):
    """将 tushare 返回的 NaN / 空值转为 None，其余原样返回。"""
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


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS margin_detail (
            trade_date      VARCHAR(8)    NOT NULL COMMENT '交易日期（YYYYMMDD）',
            ts_code         VARCHAR(12)   NOT NULL COMMENT 'TS股票代码（如000001.SZ）',
            name            VARCHAR(64)   COMMENT '股票名称（20190910后有数据）',
            rzye            DECIMAL(20,4) COMMENT '融资余额(元)',
            rqye            DECIMAL(20,4) COMMENT '融券余额(元)',
            rzmre           DECIMAL(20,4) COMMENT '融资买入额(元)',
            rqyl            DECIMAL(20,4) COMMENT '融券余量（股）',
            rzche           DECIMAL(20,4) COMMENT '融资偿还额(元)',
            rqchl           DECIMAL(20,4) COMMENT '融券偿还量(股)',
            rqmcl           DECIMAL(20,4) COMMENT '融券卖出量(股,份,手)',
            rzrqye          DECIMAL(20,4) COMMENT '融资融券余额(元)',
            update_time     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            PRIMARY KEY (trade_date, ts_code),
            KEY idx_ts_code (ts_code),
            KEY idx_trade_date (trade_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='融资融券交易明细（数据来源：Tushare Pro margin_detail 接口）'
    """)


def save_df(df):
    cols = ['trade_date', 'ts_code', 'rzye', 'rqye', 'rzmre', 'rqyl',
            'rzche', 'rqchl', 'rqmcl', 'rzrqye']
    if 'name' in df.columns:
        cols.insert(2, 'name')
    placeholders = ','.join(['%s'] * len(cols))
    col_names = ','.join(cols)
    sql = f"""
        INSERT INTO margin_detail ({col_names})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE
            name=VALUES(name), rzye=VALUES(rzye), rqye=VALUES(rqye),
            rzmre=VALUES(rzmre), rqyl=VALUES(rqyl), rzche=VALUES(rzche),
            rqchl=VALUES(rqchl), rqmcl=VALUES(rqmcl), rzrqye=VALUES(rzrqye),
            update_time=CURRENT_TIMESTAMP
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            rows = [tuple(to_db(r[c]) for c in cols)
                for _, r in df.iterrows()]
            cur.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()


def download_by_date(pro, date_str):
    """下载单个交易日的数据。"""
    df = pro.margin_detail(trade_date=date_str)
    if df is not None and len(df) > 0:
        save_df(df)
        return len(df)
    return 0


def download_by_range(pro, start_date, end_date):
    """按日期范围下载，如果返回行数达到上限则分段下载。"""
    df = pro.margin_detail(start_date=start_date, end_date=end_date)
    if df is None or len(df) == 0:
        return 0
    if len(df) < PAGE_SIZE:
        save_df(df)
        return len(df)
    # 达到上限，需要分段下载
    total = 0
    current = datetime.strptime(start_date, '%Y%m%d')
    end = datetime.strptime(end_date, '%Y%m%d')
    while current <= end:
        # 按月分段
        month_end = current.replace(day=28) + timedelta(days=4)
        month_end = month_end.replace(day=1) - timedelta(days=1)
        if month_end > end:
            month_end = end
        month_start_str = current.strftime('%Y%m%d')
        month_end_str = month_end.strftime('%Y%m%d')
        # 下载该月数据
        month_df = pro.margin_detail(start_date=month_start_str, end_date=month_end_str)
        if month_df is not None and len(month_df) > 0:
            if len(month_df) < PAGE_SIZE:
                save_df(month_df)
                total += len(month_df)
            else:
                # 该月数据也达到上限，按天下载
                day = current
                while day <= month_end:
                    day_str = day.strftime('%Y%m%d')
                    day_df = pro.margin_detail(trade_date=day_str)
                    if day_df is not None and len(day_df) > 0:
                        save_df(day_df)
                        total += len(day_df)
                    day += timedelta(days=1)
                    time.sleep(SLEEP)
        current = month_end + timedelta(days=1)
        time.sleep(SLEEP)
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=str, default='20210101',
                        help='开始日期（YYYYMMDD，默认20210101）')
    parser.add_argument('--end', type=str, default=None,
                        help='结束日期（YYYYMMDD，默认今天）')
    args = parser.parse_args()

    pro = ts.pro_api(API_KEY)

    conn = get_conn()
    try:
        cur = conn.cursor()
        create_tables(cur)
        conn.commit()
    finally:
        conn.close()

    end_date = args.end or datetime.now().strftime('%Y%m%d')
    print(f'开始下载融资融券交易明细数据：{args.start} 至 {end_date}')

    # 按月循环下载
    current = datetime.strptime(args.start, '%Y%m%d')
    end = datetime.strptime(end_date, '%Y%m%d')
    total = 0
    while current <= end:
        # 计算当月最后一天
        month_end = current.replace(day=28) + timedelta(days=4)
        month_end = month_end.replace(day=1) - timedelta(days=1)
        if month_end > end:
            month_end = end
        start_str = current.strftime('%Y%m%d')
        end_str = month_end.strftime('%Y%m%d')
        print(f'下载 {start_str} 至 {end_str} ...', end=' ', flush=True)
        count = download_by_range(pro, start_str, end_str)
        total += count
        print(f'{count} 条，累计 {total}')
        current = month_end + timedelta(days=1)
        time.sleep(SLEEP)

    print(f'下载完成，共 {total} 条')


if __name__ == '__main__':
    main()