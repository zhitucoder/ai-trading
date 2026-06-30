#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从通达信本地文件导入股票代码和名称到 stocks 表"""

import os
import pymysql
from pymysql.cursors import DictCursor

CODE_FILE = '/mnt/d/programs/stock/T0002/hq_cache/infoharbor_ex.code'
DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')


def classify(code: str) -> tuple[str, str]:
    if code.startswith('399'):
        return 'sz', 'index'
    if code.startswith(('60', '68')):
        return 'sh', 'stock'
    if code.startswith(('00', '30', '001', '002', '003')):
        return 'sz', 'stock'
    if code.startswith(('4', '8')):
        return 'bj', 'stock'
    if code.startswith('5'):
        return 'sh', 'fund'
    if code.startswith(('1', '2')):
        return 'sh', 'bond'
    if code.startswith('9'):
        return 'sh', 'b_share'
    return 'ot', 'other'


def main():
    if not os.path.isfile(CODE_FILE):
        print(f"ERROR: {CODE_FILE} not found")
        return

    stocks: dict[str, dict] = {}
    with open(CODE_FILE, 'rb') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.decode('gbk').split('|', 2)
            if len(parts) >= 2:
                code = parts[0].strip()
                name = parts[1].strip()
                if code and name:
                    exchange, sec_type = classify(code)
                    stocks[code] = dict(code=code, name=name,
                                        exchange=exchange, type=sec_type)

    print(f"Read {len(stocks)} stocks from code file")

    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS stocks")
    cursor.execute("""
        CREATE TABLE stocks (
            stock_code VARCHAR(10) NOT NULL PRIMARY KEY COMMENT '股票代码',
            stock_name VARCHAR(50) NOT NULL COMMENT '股票名称',
            exchange VARCHAR(4) DEFAULT '' COMMENT '交易所: sh/sz/bj',
            security_type VARCHAR(20) DEFAULT '' COMMENT '类型: stock/index/fund/bond/b_share'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票基本信息'
    """)
    conn.commit()

    insert_sql = "INSERT INTO stocks (stock_code, stock_name, exchange, security_type) VALUES (%s, %s, %s, %s)"
    batch = []
    for s in stocks.values():
        batch.append((s['code'], s['name'], s['exchange'], s['type']))

    BATCH = 1000
    for i in range(0, len(batch), BATCH):
        chunk = batch[i:i + BATCH]
        cursor.executemany(insert_sql, chunk)
        conn.commit()

    # Stats
    cursor.execute("""
        SELECT security_type, COUNT(*) as cnt FROM stocks GROUP BY security_type ORDER BY cnt DESC
    """)
    print("\nDistribution:")
    for r in cursor.fetchall():
        print(f"  {r['security_type']:10s} {r['cnt']}")

    cursor.execute("SELECT COUNT(*) as cnt FROM stocks")
    print(f"\nTotal: {cursor.fetchone()['cnt']}")

    cursor.close()
    conn.close()
    print("Done!")


if __name__ == '__main__':
    main()
