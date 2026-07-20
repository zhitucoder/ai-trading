#!/home/rick/miniconda3/envs/aitrading/bin/python
"""导入通达信板块指数日K线到 sector_kline 表

数据源: sh/lday/ 下 880xxx + 881xxx 文件（通达信行业/概念/风格/地区板块指数）
"""

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


def parse_day_file(filepath):
    code = os.path.splitext(os.path.basename(filepath))[0][2:]
    records = []
    with open(filepath, 'rb') as f:
        while True:
            data = f.read(RECORD_SIZE)
            if len(data) < RECORD_SIZE:
                break
            date, o, h, l, c, amt, vol, _ = struct.unpack(RECORD_FMT, data)
            records.append((
                code, datetime.strptime(str(date), '%Y%m%d').date(),
                round(o / 100, 2), round(h / 100, 2),
                round(l / 100, 2), round(c / 100, 2),
                vol, round(amt, 2),
            ))
    return records


def main():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS sector_kline")
    cursor.execute("""
        CREATE TABLE sector_kline (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            sector_code VARCHAR(10) NOT NULL COMMENT '板块指数代码(880xxx/881xxx)',
            trade_date DATE NOT NULL COMMENT '交易日期',
            open_price DECIMAL(10,2) NOT NULL COMMENT '开盘价',
            high_price DECIMAL(10,2) NOT NULL COMMENT '最高价',
            low_price DECIMAL(10,2) NOT NULL COMMENT '最低价',
            close_price DECIMAL(10,2) NOT NULL COMMENT '收盘价',
            volume BIGINT NOT NULL COMMENT '成交量(股)',
            amount DECIMAL(16,2) NOT NULL COMMENT '成交额(元)',
            UNIQUE KEY uk_sector_date (sector_code, trade_date),
            KEY idx_date (trade_date),
            KEY idx_code (sector_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
          COMMENT='通达信板块指数日K线(880xxx行业/概念 + 881xxx风格/地区)'
    """)
    conn.commit()

    sh_dir = os.path.join(DATA_DIR, 'sh', 'lday')
    if not os.path.isdir(sh_dir):
        print(f'Directory not found: {sh_dir}')
        return

    files = sorted([
        f for f in os.listdir(sh_dir)
        if f.endswith('.day') and (f.startswith('sh880') or f.startswith('sh881'))
    ])
    print(f'sh sector index files: {len(files)}')

    batch = []
    for fname in files:
        records = parse_day_file(os.path.join(sh_dir, fname))
        batch.extend(records)

    print(f'  total records: {len(batch)}')

    if not batch:
        print('No data to insert')
        return

    sql = """INSERT IGNORE INTO sector_kline
             (sector_code, trade_date, open_price, high_price, low_price, close_price, volume, amount)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""

    CHUNK = 5000
    for i in range(0, len(batch), CHUNK):
        chunk = batch[i:i + CHUNK]
        cursor.executemany(sql, chunk)
        conn.commit()
        print(f'  inserted {min(i + CHUNK, len(batch))}/{len(batch)}')

    cursor.close()
    conn.close()
    print('Done!')


if __name__ == '__main__':
    main()
