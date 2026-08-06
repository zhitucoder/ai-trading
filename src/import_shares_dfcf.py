#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从东方财富实时行情 API 批量下载全市场股本数据，存入 stock_shares_dfcf 表。

数据来源：东方财富 push2 实时行情接口（https://push2.eastmoney.com）
字段映射：
  f12 = 股票代码
  f14 = 股票名称
  f84 = 总股本(股)
  f85 = 流通股本(股)
  f116 = 总市值(元)（仅 A 股有效，北交所为 -）

用法:
  python import_shares_dfcf.py            # 全量下载并入库
"""

import json
import subprocess
import time
import urllib.parse

import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4', cursorclass=DictCursor)

HOSTS = ['https://82.push2.eastmoney.com', 'https://push2delay.eastmoney.com',
         'https://push2.eastmoney.com']
PAGE_SIZE = 200
MAX_RETRY = 3
SLEEP_BETWEEN_PAGES = 2.0
SLEEP_ON_RETRY = 10.0

FS_ALL = 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048'
FIELDS = 'f12,f14,f84,f85,f116'


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def create_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_shares_dfcf (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
            stock_name VARCHAR(50) COMMENT '股票名称',
            total_shares BIGINT COMMENT '总股本(股)',
            float_shares BIGINT COMMENT '流通股本(股)',
            total_mv DECIMAL(20,2) COMMENT '总市值(元)',
            source VARCHAR(20) NOT NULL DEFAULT 'dfcf' COMMENT '数据来源: 东方财富实时行情API',
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_stock (stock_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股本结构（数据来源：东方财富实时行情API push2）'
    """)


def fetch_page(pn):
    params = urllib.parse.urlencode({
        'pn': pn, 'pz': PAGE_SIZE, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2,
        'fid': 'f12', 'fs': FS_ALL, 'fields': FIELDS,
    })
    for host in HOSTS:
        url = f'{host}/api/qt/clist/get?{params}'
        for attempt in range(MAX_RETRY):
            try:
                r = subprocess.run(
                    ['curl', '-s', '--max-time', '20', url,
                     '-H', 'Referer: https://quote.eastmoney.com/',
                     '-H', 'User-Agent: Mozilla/5.0'],
                    capture_output=True, text=True, timeout=25)
                data = json.loads(r.stdout)
                if data.get('data'):
                    return data['data']
            except Exception:
                pass
            time.sleep(SLEEP_ON_RETRY * (attempt + 1))
    return None


def main():
    conn = get_conn()
    cursor = conn.cursor()
    create_table(cursor)
    conn.commit()

    first = fetch_page(1)
    if not first:
        print('[dfcf] 无法获取首页数据，请检查网络')
        return
    total = first['total']
    rows = list(first.get('diff', []))
    print(f'[dfcf] 市场总股票数: {total}')

    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    for pn in range(2, pages + 1):
        time.sleep(SLEEP_BETWEEN_PAGES)
        data = fetch_page(pn)
        if data and data.get('diff'):
            rows.extend(data['diff'])
        if pn % 5 == 0 or pn == pages:
            print(f'[dfcf] 进度: {len(rows)}/{total} (页 {pn}/{pages})')

    print(f'[dfcf] 下载完成，共 {len(rows)} 条')

    insert_sql = """
        INSERT INTO stock_shares_dfcf
            (stock_code, stock_name, total_shares, float_shares, total_mv, source)
        VALUES (%s, %s, %s, %s, %s, 'dfcf')
        ON DUPLICATE KEY UPDATE
            stock_name=VALUES(stock_name),
            total_shares=VALUES(total_shares),
            float_shares=VALUES(float_shares),
            total_mv=VALUES(total_mv),
            source=VALUES(source),
            update_time=CURRENT_TIMESTAMP
    """
    n = 0
    for item in rows:
        code = str(item.get('f12', '')).strip()
        if not code:
            continue
        name = str(item.get('f14', '')).strip()
        ts = item.get('f84')
        fs = item.get('f85')
        mv = item.get('f116')
        # 东方财富部分字段可能返回 '-' 或异常负值，统一转 None
        ts = int(ts) if isinstance(ts, (int, float)) and ts > 0 else None
        fs = int(fs) if isinstance(fs, (int, float)) and fs > 0 else None
        mv = float(mv) if isinstance(mv, (int, float)) and mv > 0 else None
        try:
            cursor.execute(insert_sql, (code, name, ts, fs, mv))
            n += 1
        except Exception as e:
            print(f'[dfcf] 写入失败 {code}: {e}')
    conn.commit()
    cursor.close()
    conn.close()
    print(f'[dfcf] 入库完成，写入 {n} 条')


if __name__ == '__main__':
    main()
