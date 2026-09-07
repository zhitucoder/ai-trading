#!/home/rick/miniconda3/envs/aitrading/bin/python
"""导入主要宽基指数K线到 index_kline 表"""

import os
import struct
import pymysql
from datetime import datetime

DATA_DIR = '/mnt/d/programs/stock/vipdoc'
DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

RECORD_FMT = '<IIIIIfII'
RECORD_SIZE = 32

INDEX_MAP = {
    'sh000001': ('000001', '上证综指'),
    'sh000016': ('000016', '上证50'),
    'sh000300': ('000300', '沪深300'),
    'sh000905': ('000905', '中证500'),
    'sh000852': ('000852', '中证1000'),
}


def parse_day_file(filepath):
    records = []
    with open(filepath, 'rb') as f:
        while True:
            data = f.read(RECORD_SIZE)
            if len(data) < RECORD_SIZE:
                break
            date, o, h, l, c, amt, vol, _ = struct.unpack(RECORD_FMT, data)
            records.append((
                datetime.strptime(str(date), '%Y%m%d').date(),
                round(o / 100, 2), round(h / 100, 2),
                round(l / 100, 2), round(c / 100, 2),
                vol, round(amt, 2),
            ))
    return records


def main():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS index_kline")
    cursor.execute("""
        CREATE TABLE index_kline (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            index_code VARCHAR(10) NOT NULL COMMENT '指数代码(纯数字)',
            trade_date DATE NOT NULL COMMENT '交易日期',
            open_price DECIMAL(10,2) NOT NULL,
            high_price DECIMAL(10,2) NOT NULL,
            low_price DECIMAL(10,2) NOT NULL,
            close_price DECIMAL(10,2) NOT NULL,
            volume BIGINT NOT NULL,
            amount DECIMAL(16,2) NOT NULL,
            UNIQUE KEY uk_code_date (index_code, trade_date),
            KEY idx_date (trade_date),
            KEY idx_code (index_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
          COMMENT='主要宽基指数日K线(上证综指/上证50/沪深300/中证500/中证1000)'
    """)
    conn.commit()

    sql = """INSERT IGNORE INTO index_kline
             (index_code, trade_date, open_price, high_price, low_price, close_price, volume, amount)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""

    total = 0
    for filename, (code, name) in INDEX_MAP.items():
        filepath = os.path.join(DATA_DIR, 'sh', 'lday', f'{filename}.day')
        if not os.path.isfile(filepath):
            print(f'  SKIP {filename}: file not found')
            continue
        records = parse_day_file(filepath)
        batch = [(code, *r) for r in records]
        for i in range(0, len(batch), 5000):
            chunk = batch[i:i + 5000]
            cursor.executemany(sql, chunk)
            conn.commit()
        total += len(batch)
        print(f'  {name} ({code}): {len(batch)} records')

    cursor.close()
    conn.close()
    print(f'Done! Total: {total} records')


if __name__ == '__main__':
    main()
