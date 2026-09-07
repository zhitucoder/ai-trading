#!/home/rick/miniconda3/envs/aitrading/bin/python
"""下载航运运价指数（波罗的海指数系列）到 MySQL 表 shipping_freight_index。

数据源：akshare（免费），覆盖波罗的海三大细分市场指数：
  - BDTI  原油轮运价指数（VLCC 主要参照）   对应招商轮船/中远海能的油运业务
  - BCTI  成品油轮运价指数                 油运补充
  - BDI   波罗的海干散货综合指数            对应招商轮船散货业务
  - BCI   波罗的海好望角型干散货运价指数    散货细分
  - BPI   波罗的海巴拿马型干散货运价指数    散货细分

说明：
  1. 中远海控(601919)为集装箱航运，其对应运价为 CCFI/SCFI（上海航交所，需订阅），
     本脚本不含该数据，分析时以现有数据说明局限。
  2. 每张表都带表注释/字段注释/update_time；可重复运行（INSERT IGNORE 幂等）。

用法：
  python import_freight_index.py            # 全量下载入库
  python import_freight_index.py --since 2024-01-01   # 只更新某日期之后
"""

import argparse
import sys
from datetime import datetime

import akshare as ak
import pandas as pd
import pymysql

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

# 指数 -> (表名, 中文名, 说明, 获取函数)
INDICES = [
    dict(table='shipping_bdti', code='BDTI', name='波罗的海原油轮运价指数',
         desc='波罗的海原油轮运价指数(Baltic Dirty Tanker Index)，VLCC等原油轮即期运价综合参照',
         fn=ak.macro_china_bdti_index),
    dict(table='shipping_bcti', code='BCTI', name='波罗的海成品油轮运价指数',
         desc='波罗的海成品油轮运价指数(Baltic Clean Tanker Index)，成品油轮即期运价',
         fn=ak.macro_shipping_bcti),
    dict(table='shipping_bdi', code='BDI', name='波罗的海干散货运价综合指数',
         desc='波罗的海干散货运价综合指数(Baltic Dry Index)，好望角/巴拿马/超灵便加权',
         fn=ak.macro_shipping_bdi),
    dict(table='shipping_bci', code='BCI', name='波罗的海好望角型干散货运价指数',
         desc='波罗的海好望角型船运价指数(Baltic Capesize Index)，载重10万吨以上',
         fn=ak.macro_shipping_bci),
    dict(table='shipping_bpi', code='BPI', name='波罗的海巴拿马型干散货运价指数',
         desc='波罗的海巴拿马型船运价指数(Baltic Panamax Index)，载重6-8万吨',
         fn=ak.macro_shipping_bpi),
]


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def create_table(conn, meta):
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS `{meta['table']}` (
            id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
            index_code  VARCHAR(10)  NOT NULL COMMENT '指数代码(BDTI/BCTI/BDI/BCI/BPI)',
            trade_date  DATE         NOT NULL COMMENT '交易日/报价日期',
            close_value DECIMAL(12,2) NOT NULL COMMENT '运价指数收盘值(点)',
            pct_chg     DECIMAL(10,4) NULL COMMENT '较上一交易日涨跌幅(%)',
            update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '本行最后更新时间',
            UNIQUE KEY uk_code_date (index_code, trade_date),
            KEY idx_date (trade_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
          COMMENT='{meta['name']}({meta['code']}) - {meta['desc']}'
    """)
    conn.commit()
    cur.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', type=str, default=None,
                        help='只更新该日期(YYYY-MM-DD)之后的数据')
    args = parser.parse_args()

    conn = get_conn()
    cur = conn.cursor()
    try:
        for meta in INDICES:
            fn = meta['fn']
            print(f"[{meta['code']}] 正在从 akshare 下载 {meta['name']} ...", flush=True)
            df = fn()
            if df is None or df.empty or '日期' not in df.columns:
                print(f"  !! {meta['code']} 返回空数据，跳过", flush=True)
                continue

            df = df.rename(columns={'日期': 'trade_date', '最新值': 'close_value',
                                    '涨跌幅': 'pct_chg'})
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df['index_code'] = meta['code']
            df['close_value'] = pd.to_numeric(df['close_value'], errors='coerce')
            df['pct_chg'] = pd.to_numeric(df['pct_chg'], errors='coerce')
            df = df.dropna(subset=['close_value'])

            if args.since:
                df = df[df['trade_date'] >= pd.to_datetime(args.since)]

            if df.empty:
                print(f"  {meta['code']}: 无符合条件数据", flush=True)
                continue

            create_table(conn, meta)

            rows = [(r.index_code, r.trade_date.date(), float(r.close_value),
                     None if pd.isna(r.pct_chg) else float(r.pct_chg))
                    for r in df.itertuples()]

            sql = f"""INSERT IGNORE INTO `{meta['table']}`
                      (index_code, trade_date, close_value, pct_chg)
                      VALUES (%s, %s, %s, %s)"""
            n = 0
            for i in range(0, len(rows), 2000):
                cur.executemany(sql, rows[i:i + 2000])
                conn.commit()
                n += len(rows[i:i + 2000])
            print(f"  {meta['code']}: 写入 {n} 行 "
                  f"({df['trade_date'].min().date()} ~ {df['trade_date'].max().date()})", flush=True)
    finally:
        cur.close()
        conn.close()
    print("完成!")


if __name__ == '__main__':
    main()
