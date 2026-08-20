#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从东方财富数据中心下载全市场并购重组明细数据，存入 reorganize_dfcf 表。

数据来源：东方财富数据中心·并购重组
  页面: https://data.eastmoney.com/bgcz/
  接口: https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_BGCZMX

字段含义（东方财富并购重组明细）：
  SCODE            股票代码
  SNAME            股票简称
  H_COMNAME        交易标的（被收购/投资标的公司）
  G_GOMNAME        买方
  S_COMNAME        卖方
  JYJE             交易金额(元)
  BZNAME           币种名称
  TJEBZH           币种代码(CNY/USD...)
  ZRBL             股权转让比例(%)
  ZRFS             并购方式/转让方式(对外投资/资产收购/股权转让/吸收合并...)
  OBJTYPE          对象类型(股权/资产)
  JD               阶段(董事会预案/股东大会通过/实施完成/失败...)
  SCGGRQ           最新公告日期
  ANNOUNDATE       首次披露日期
  MKT              市场(沪A/深A/创业板/北证)
  REORGANIZECODE   重组编码
  MXID             明细唯一ID

用法:
  python import_reorganize_dfcf.py [起始页] [结束页]
  每页500条，默认从第1页下载到全部完成；可传页码区间断点续传。
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

API = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
PAGE_SIZE = 500
SLEEP_BETWEEN = 0.8
MAX_RETRY = 3
SLEEP_ON_RETRY = 5.0


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def create_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reorganize_dfcf (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            mxid VARCHAR(64) NOT NULL COMMENT '东方财富明细ID',
            stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
            stock_name VARCHAR(50) COMMENT '股票简称',
            target_company VARCHAR(500) COMMENT '交易标的',
            buyer VARCHAR(500) COMMENT '买方',
            seller VARCHAR(500) COMMENT '卖方',
            deal_amount DECIMAL(20,2) COMMENT '交易金额(元)',
            currency VARCHAR(20) COMMENT '币种',
            transfer_ratio DECIMAL(10,4) COMMENT '股权转让比例(%)',
            method VARCHAR(50) COMMENT '并购方式(转让方式)',
            object_type VARCHAR(20) COMMENT '对象类型(股权/资产)',
            stage VARCHAR(50) COMMENT '阶段(董事会预案/实施完成等)',
            announce_date DATE COMMENT '最新公告日期',
            notice_date DATE COMMENT '首次披露日期',
            market VARCHAR(20) COMMENT '市场',
            reorganize_code VARCHAR(20) COMMENT '重组编码',
            source VARCHAR(20) NOT NULL DEFAULT 'dfcf' COMMENT '数据来源',
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_mxid (mxid),
            KEY idx_stock (stock_code),
            KEY idx_reorg (reorganize_code),
            KEY idx_notice (notice_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='并购重组明细（数据来源：东方财富数据中心 datacenter-web.eastmoney.com）'
    """)


def fetch_page(page):
    params = (
        f'reportName=RPTA_WEB_BGCZMX&columns=ALL&pageNumber={page}'
        f'&pageSize={PAGE_SIZE}&sortColumns=SCGGRQ&sortTypes=-1&source=WEB&client=WEB'
    )
    url = f'{API}?{params}'
    for attempt in range(MAX_RETRY):
        try:
            r = subprocess.run(
                ['curl', '-s', '--max-time', '25', url,
                 '-H', 'Referer: https://data.eastmoney.com/bgcz/',
                 '-H', 'User-Agent: Mozilla/5.0'],
                capture_output=True, text=True, timeout=30)
            d = json.loads(r.stdout)
            if d.get('success'):
                res = d.get('result') or {}
                return res.get('data') or [], res.get('count') or 0
        except Exception:
            pass
        time.sleep(SLEEP_ON_RETRY * (attempt + 1))
    return None, 0


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 10**9

    conn = get_conn()
    cursor = conn.cursor()
    create_table(cursor)
    conn.commit()

    # 已入库的 mxid，用于跳过
    cursor.execute('SELECT mxid FROM reorganize_dfcf')
    have = {r['mxid'] for r in cursor.fetchall()}
    print(f'[reorg] 已入库 {len(have)} 条', flush=True)

    insert_sql = """
        INSERT INTO reorganize_dfcf
            (mxid, stock_code, stock_name, target_company, buyer, seller,
             deal_amount, currency, transfer_ratio, method, object_type,
             stage, announce_date, notice_date, market, reorganize_code, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'dfcf')
        ON DUPLICATE KEY UPDATE
            stock_code=VALUES(stock_code),
            stock_name=VALUES(stock_name),
            target_company=VALUES(target_company),
            buyer=VALUES(buyer),
            seller=VALUES(seller),
            deal_amount=VALUES(deal_amount),
            currency=VALUES(currency),
            transfer_ratio=VALUES(transfer_ratio),
            method=VALUES(method),
            object_type=VALUES(object_type),
            stage=VALUES(stage),
            announce_date=VALUES(announce_date),
            notice_date=VALUES(notice_date),
            market=VALUES(market),
            reorganize_code=VALUES(reorganize_code),
            update_time=CURRENT_TIMESTAMP
    """

    # 先取第1页确认总量
    first, total = fetch_page(1)
    if first is None:
        print('[reorg] 接口获取失败，退出')
        sys.exit(1)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    print(f'[reorg] 总记录 {total}，共 {total_pages} 页（每页{PAGE_SIZE}），本次区间 {start}-{min(end, total_pages)}', flush=True)

    ok = fail = 0
    for page in range(start, min(end, total_pages) + 1):
        if page == 1:
            data = first
        else:
            data, _ = fetch_page(page)
        if data is None:
            print(f'[reorg] 第{page}页获取失败，跳过', flush=True)
            fail += PAGE_SIZE
            continue
        rows = []
        for it in data:
            mxid = it.get('MXID')
            if not mxid or mxid in have:
                continue
            have.add(mxid)
            rows.append((
                mxid,
                it.get('SCODE'),
                it.get('SNAME'),
                it.get('H_COMNAME'),
                it.get('G_GOMNAME'),
                it.get('S_COMNAME'),
                it.get('JYJE'),
                it.get('BZNAME'),
                it.get('ZRBL'),
                it.get('ZRFS'),
                it.get('OBJTYPE'),
                it.get('JD'),
                (it.get('SCGGRQ') or '')[:10],
                (it.get('ANNOUNDATE') or '')[:10],
                it.get('MKT'),
                it.get('REORGANIZECODE'),
            ))
        if rows:
            try:
                cursor.executemany(insert_sql, rows)
                ok += len(rows)
            except Exception as e:
                print(f'[reorg] 第{page}页写入失败: {e}', flush=True)
                fail += len(rows)
        if page % 5 == 0:
            conn.commit()
            print(f'[reorg] 页 {page}/{total_pages} 新增{ok} 失败{fail}', flush=True)
        time.sleep(SLEEP_BETWEEN)

    conn.commit()
    cursor.close()
    conn.close()
    print(f'[reorg] 完成: 新增 {ok}，失败 {fail}')


if __name__ == '__main__':
    main()