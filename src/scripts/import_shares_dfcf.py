#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从东方财富 F10 股本结构接口批量下载全市场股本数据，存入 stock_shares_dfcf 表。

数据来源：东方财富 PC_HSF10 CapitalStockStructure 接口
  https://emweb.securities.eastmoney.com/PC_HSF10/CapitalStockStructure/PageAjax?code=SH600938

字段含义（东方财富 F10 股本结构）：
  TOTAL_SHARES       总股本(股)
  UNLIMITED_SHARES   无限售流通股(股)
  LISTED_A_SHARES    流通A股(股)
  H_FREE_SHARE       流通H股(股)
  LIMITED_SHARES     限售股(股)
  NON_FREE_SHARES    非流通股(股)

用法:
  python import_shares_dfcf.py [起始序号] [结束序号]
"""

import json
import subprocess
import sys
import time

import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4', cursorclass=DictCursor)

SLEEP_BETWEEN = 1.5
MAX_RETRY = 3
SLEEP_ON_RETRY = 8.0


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def create_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_shares_dfcf (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
            stock_name VARCHAR(50) COMMENT '股票名称',
            total_shares BIGINT COMMENT '总股本(股)',
            float_shares BIGINT COMMENT '无限售流通股本(股)',
            float_a_shares BIGINT COMMENT '流通A股(股)',
            float_h_shares BIGINT COMMENT '流通H股(股)',
            limited_shares BIGINT COMMENT '限售股(股)',
            source VARCHAR(20) NOT NULL DEFAULT 'dfcf' COMMENT '数据来源: 东方财富F10股本结构接口',
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_stock (stock_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股本结构（数据来源：东方财富F10接口 emweb.securities.eastmoney.com）'
    """)


def fetch_capital(code):
    prefix = 'SH' if code.startswith('6') else ('SZ' if code.startswith(('0', '3')) else 'BJ')
    url = f'https://emweb.securities.eastmoney.com/PC_HSF10/CapitalStockStructure/PageAjax?code={prefix}{code}'
    for attempt in range(MAX_RETRY):
        try:
            r = subprocess.run(
                ['curl', '-s', '--max-time', '15', url,
                 '-H', 'Referer: https://emweb.securities.eastmoney.com/',
                 '-H', 'User-Agent: Mozilla/5.0'],
                capture_output=True, text=True, timeout=20)
            d = json.loads(r.stdout)
            gb = d.get('gbjg', [])
            if gb:
                it = gb[0]
                return {
                    'total': it.get('TOTAL_SHARES'),
                    'float': it.get('UNLIMITED_SHARES'),
                    'float_a': it.get('LISTED_A_SHARES'),
                    'float_h': it.get('H_FREE_SHARE'),
                    'limited': it.get('LIMITED_SHARES'),
                }
        except Exception:
            pass
        time.sleep(SLEEP_ON_RETRY * (attempt + 1))
    return None


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 10**6

    conn = get_conn()
    cursor = conn.cursor()
    create_table(cursor)
    conn.commit()

    cursor.execute("""
        SELECT s.stock_code, s.stock_name, t.id
        FROM stocks s LEFT JOIN stock_shares_dfcf t ON s.stock_code = t.stock_code
        ORDER BY s.stock_code
    """)
    all_stocks = cursor.fetchall()
    todo = [r for r in all_stocks[start:end] if r['id'] is None]
    print(f'[dfcf] 股票总数 {len(all_stocks)}，本次需下载 {len(todo)} 只（区间 {start}-{end}）')

    insert_sql = """
        INSERT INTO stock_shares_dfcf
            (stock_code, stock_name, total_shares, float_shares,
             float_a_shares, float_h_shares, limited_shares, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'dfcf')
        ON DUPLICATE KEY UPDATE
            stock_name=VALUES(stock_name),
            total_shares=VALUES(total_shares),
            float_shares=VALUES(float_shares),
            float_a_shares=VALUES(float_a_shares),
            float_h_shares=VALUES(float_h_shares),
            limited_shares=VALUES(limited_shares),
            update_time=CURRENT_TIMESTAMP
    """

    ok = fail = 0
    for i, row in enumerate(todo):
        code = row['stock_code']
        name = row['stock_name']
        d = fetch_capital(code)
        if d and d['total']:
            try:
                cursor.execute(insert_sql, (code, name, d['total'], d['float'],
                                            d['float_a'], d['float_h'], d['limited']))
                ok += 1
            except Exception as e:
                print(f'[dfcf] 写入失败 {code}: {e}')
                fail += 1
        else:
            fail += 1
            print(f'[dfcf] 获取失败 {code} {name}', flush=True)
        if (i + 1) % 20 == 0:
            conn.commit()
            print(f'[dfcf] 进度 {i+1}/{len(todo)} (成功{ok} 失败{fail})', flush=True)
        time.sleep(SLEEP_BETWEEN)

    conn.commit()
    cursor.close()
    conn.close()
    print(f'[dfcf] 完成: 成功 {ok}，失败 {fail}')


if __name__ == '__main__':
    main()
