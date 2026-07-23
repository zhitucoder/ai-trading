#!/home/rick/miniconda3/envs/aitrading/bin/python
"""导入通达信日K线数据到 MySQL

分类规则:
  - daily_kline: 股票/ETF/债券等可交易品种
  - sector_kline: 通达信板块指数(880xxx/881xxx)
  - 排除: 上证指数(sh000xxx)、深证指数(sz399xxx)、B股指数(sh900xxx)
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


def classify_file(exchange, code):
    """返回 'stock' / 'sector' / 'skip'"""
    if exchange == 'sh':
        if code.startswith('880') or code.startswith('881'):
            return 'sector'
        if code.startswith('000') or code.startswith('900'):
            return 'skip'
        return 'stock'
    elif exchange == 'sz':
        if code.startswith('399'):
            return 'skip'
        return 'stock'
    elif exchange == 'bj':
        return 'stock'
    return 'skip'


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

    cursor.execute("DROP TABLE IF EXISTS daily_kline")
    cursor.execute("DROP TABLE IF EXISTS sector_kline")
    cursor.execute("""
        CREATE TABLE daily_kline (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            stock_code VARCHAR(10) NOT NULL COMMENT '股票代码（纯数字，无sh/sz前缀）',
            trade_date DATE NOT NULL COMMENT '交易日期',
            open_price DECIMAL(10,2) NOT NULL COMMENT '开盘价',
            high_price DECIMAL(10,2) NOT NULL COMMENT '最高价',
            low_price DECIMAL(10,2) NOT NULL COMMENT '最低价',
            close_price DECIMAL(10,2) NOT NULL COMMENT '收盘价',
            volume BIGINT NOT NULL COMMENT '成交量(股)',
            amount DECIMAL(16,2) NOT NULL COMMENT '成交额(元)',
            UNIQUE KEY uk_stock_date (stock_code, trade_date),
            KEY idx_date (trade_date),
            KEY idx_code (stock_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
          COMMENT='A股日K线数据（仅股票/ETF/债券，不含指数和板块）'
    """)
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

    stock_sql = """INSERT IGNORE INTO daily_kline
                   (stock_code, trade_date, open_price, high_price, low_price, close_price, volume, amount)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""

    for exchange in ['sh', 'sz', 'bj']:
        day_dir = os.path.join(DATA_DIR, exchange, 'lday')
        if not os.path.isdir(day_dir):
            continue
        files = sorted([f for f in os.listdir(day_dir) if f.endswith('.day')])
        print(f'{exchange}: {len(files)} files')

        stock_batch = []
        sector_batch = []
        skipped = 0

        for fname in files:
            code = fname[2:-4]
            cat = classify_file(exchange, code)
            if cat == 'skip':
                skipped += 1
                continue
            records = parse_day_file(os.path.join(day_dir, fname))
            if cat == 'sector':
                sector_batch.extend(records)
            else:
                stock_batch.extend(records)

        print(f'  stock: {len(stock_batch)} records, sector: {len(sector_batch)} records, skipped: {skipped}')

        if stock_batch:
            for i in range(0, len(stock_batch), 5000):
                chunk = stock_batch[i:i + 5000]
                cursor.executemany(stock_sql, chunk)
                conn.commit()
                print(f'  daily_kline: {min(i + 5000, len(stock_batch))}/{len(stock_batch)}')

        if sector_batch:
            sector_sql = """INSERT IGNORE INTO sector_kline
                            (sector_code, trade_date, open_price, high_price, low_price, close_price, volume, amount)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
            for i in range(0, len(sector_batch), 5000):
                chunk = sector_batch[i:i + 5000]
                cursor.executemany(sector_sql, chunk)
                conn.commit()
                print(f'  sector_kline: {min(i + 5000, len(sector_batch))}/{len(sector_batch)}')

    cursor.close()
    conn.close()
    print('Done!')


if __name__ == '__main__':
    main()
