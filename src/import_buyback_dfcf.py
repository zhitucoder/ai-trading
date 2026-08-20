#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从东方财富数据中心下载全市场上市公司股份回购（回购方案/预案）数据，存入 stock_buyback_dfcf 表。

数据来源：东方财富数据中心·股票回购
  页面: https://data.eastmoney.com/gphg/
  接口: https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_GETHGLIST_NEW

说明：本脚本只下载「回购方案（预案）」汇总记录，不下载逐日「回购明细」
（回购明细对应接口为 RPTA_WEB_GPHG，本脚本不抓取）。

字段含义（东方财富股票回购方案列表）：
  REPURCODE          回购方案编码（唯一）
  DIM_SCODE          股票代码
  SECURITYSHORTNAME  股票简称
  SECUCODE           带市场后缀的代码(如 603517.SH)
  REPUROBJECTIVE     回购目的（公告原文）
  SHARETYPE          回购股份类型(流通A股等)
  REPURPROGRESS      回购进度代码(001=董事会预案/002=股东大会通过/003=回购实施/004=回购完成...)
  REPURNUM           已回购数量(股)
  REPURNUMLOWER      回购数量下限(股)
  REPURNUMCAP        回购数量上限(股)
  REPURAMOUNT        已回购金额(元)
  REPURAMOUNTLOWER   回购金额下限(元)
  REPURAMOUNTLIMIT   回购金额上限(元)
  REPURPRICELOWER    回购价格下限(元)
  REPURPRICECAP      回购价格上限(元)
  REPURSTARTDATE     回购起始日期
  REPURENDDATE       回购截止日期
  NOTICEDATE         首次公告日期
  FINISHDATE         回购完成日期
  REMARK             备注

用法:
  python import_buyback_dfcf.py [起始页] [结束页]
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
SLEEP_BETWEEN = 0.5
MAX_RETRY = 3
SLEEP_ON_RETRY = 5.0


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def create_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_buyback_dfcf (
            id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
            repur_code VARCHAR(32) NOT NULL COMMENT '东方财富回购方案唯一编码(源字段REPURCODE)',
            stock_code VARCHAR(10) NOT NULL COMMENT '股票代码(6位,无市场后缀;对应源字段DIM_SCODE)',
            stock_name VARCHAR(50) COMMENT '股票简称(源字段SECURITYSHORTNAME)',
            secucode VARCHAR(20) COMMENT '带市场后缀代码,如 600519.SH(源字段SECUCODE)',
            repur_objective TEXT COMMENT '回购目的(公告原文;源字段REPUROBJECTIVE)',
            share_type VARCHAR(30) COMMENT '回购股份类型,如 流通A股(源字段SHARETYPE)',
            repur_progress VARCHAR(10) COMMENT '回购进度代码(源字段REPURPROGRESS):001预案/002股东会通过/003,007实施中/004,006,008完成/005终止',
            repur_num BIGINT COMMENT '实际已回购数量(股);源字段REPURNUM,回购完成后有值,未完成为NULL',
            repur_num_lower BIGINT COMMENT '预案回购数量下限(股);源字段REPURNUMLOWER(计划区间)',
            repur_num_cap BIGINT COMMENT '预案回购数量上限(股);源字段REPURNUMCAP(计划区间)',
            repur_amount DECIMAL(20,2) COMMENT '实际已回购金额(元);源字段REPURAMOUNT,回购完成后有值,未完成为NULL',
            repur_amount_lower DECIMAL(20,2) COMMENT '预案回购金额下限(元);源字段REPURAMOUNTLOWER(计划区间)',
            repur_amount_limit DECIMAL(20,2) COMMENT '预案回购金额上限(元);源字段REPURAMOUNTLIMIT(计划区间)',
            repur_price_lower DECIMAL(12,4) COMMENT '预案回购价格下限(元);源字段REPURPRICELOWER',
            repur_price_cap DECIMAL(12,4) COMMENT '预案回购价格上限(元);源字段REPURPRICECAP',
            repur_start_date DATE COMMENT '回购起始日期(源字段REPURSTARTDATE)',
            repur_end_date DATE COMMENT '回购截止日期(源字段REPURENDDATE)',
            notice_date DATE COMMENT '首次公告日期(源字段NOTICEDATE)',
            finish_date DATE COMMENT '回购完成日期(源字段FINISHDATE)',
            remark TEXT COMMENT '备注(源字段REMARK)',
            source VARCHAR(20) NOT NULL DEFAULT 'dfcf' COMMENT '数据来源,固定 dfcf(东方财富)',
            update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
            UNIQUE KEY uk_repur (repur_code),
            KEY idx_stock (stock_code),
            KEY idx_notice (notice_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上市公司股份回购方案（数据来源：东方财富数据中心 datacenter-web.eastmoney.com；repur_num/repur_amount为实际回购值，*_lower/*_cap/*_limit为预案计划区间）'
    """)


def _date(v):
    if not v:
        return None
    return str(v)[:10]


def fetch_page(page):
    params = (
        f'reportName=RPTA_WEB_GETHGLIST_NEW&columns=ALL&pageNumber={page}'
        f'&pageSize={PAGE_SIZE}&sortColumns=REPURSTARTDATE&sortTypes=-1&source=WEB&client=WEB'
    )
    url = f'{API}?{params}'
    for attempt in range(MAX_RETRY):
        try:
            r = subprocess.run(
                ['curl', '-s', '--max-time', '25', url,
                 '-H', 'Referer: https://data.eastmoney.com/gphg/',
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

    cursor.execute('SELECT repur_code FROM stock_buyback_dfcf')
    have = {r['repur_code'] for r in cursor.fetchall()}
    print(f'[buyback] 已入库 {len(have)} 条', flush=True)

    insert_sql = """
        INSERT INTO stock_buyback_dfcf
            (repur_code, stock_code, stock_name, secucode, repur_objective,
             share_type, repur_progress, repur_num, repur_num_lower, repur_num_cap,
             repur_amount, repur_amount_lower, repur_amount_limit,
             repur_price_lower, repur_price_cap,
             repur_start_date, repur_end_date, notice_date, finish_date,
             remark, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'dfcf')
        ON DUPLICATE KEY UPDATE
            stock_code=VALUES(stock_code),
            stock_name=VALUES(stock_name),
            secucode=VALUES(secucode),
            repur_objective=VALUES(repur_objective),
            share_type=VALUES(share_type),
            repur_progress=VALUES(repur_progress),
            repur_num=VALUES(repur_num),
            repur_num_lower=VALUES(repur_num_lower),
            repur_num_cap=VALUES(repur_num_cap),
            repur_amount=VALUES(repur_amount),
            repur_amount_lower=VALUES(repur_amount_lower),
            repur_amount_limit=VALUES(repur_amount_limit),
            repur_price_lower=VALUES(repur_price_lower),
            repur_price_cap=VALUES(repur_price_cap),
            repur_start_date=VALUES(repur_start_date),
            repur_end_date=VALUES(repur_end_date),
            notice_date=VALUES(notice_date),
            finish_date=VALUES(finish_date),
            remark=VALUES(remark),
            update_time=CURRENT_TIMESTAMP
    """

    first, total = fetch_page(1)
    if first is None:
        print('[buyback] 接口获取失败，退出')
        sys.exit(1)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    print(f'[buyback] 总记录 {total}，共 {total_pages} 页（每页{PAGE_SIZE}），本次区间 {start}-{min(end, total_pages)}', flush=True)

    ok = fail = 0
    for page in range(start, min(end, total_pages) + 1):
        if page == 1:
            data = first
        else:
            data, _ = fetch_page(page)
        if data is None:
            print(f'[buyback] 第{page}页获取失败，跳过', flush=True)
            fail += PAGE_SIZE
            continue
        rows = []
        for it in data:
            code = it.get('REPURCODE')
            if not code or code in have:
                continue
            have.add(code)
            rows.append((
                code,
                it.get('DIM_SCODE'),
                it.get('SECURITYSHORTNAME'),
                it.get('SECUCODE'),
                it.get('REPUROBJECTIVE'),
                it.get('SHARETYPE'),
                it.get('REPURPROGRESS'),
                it.get('REPURNUM'),
                it.get('REPURNUMLOWER'),
                it.get('REPURNUMCAP'),
                it.get('REPURAMOUNT'),
                it.get('REPURAMOUNTLOWER'),
                it.get('REPURAMOUNTLIMIT'),
                it.get('REPURPRICELOWER'),
                it.get('REPURPRICECAP'),
                _date(it.get('REPURSTARTDATE')),
                _date(it.get('REPURENDDATE')),
                _date(it.get('NOTICEDATE')),
                _date(it.get('FINISHDATE')),
                it.get('REMARK'),
            ))
        if rows:
            try:
                cursor.executemany(insert_sql, rows)
                ok += len(rows)
            except Exception as e:
                print(f'[buyback] 第{page}页写入失败: {e}', flush=True)
                fail += len(rows)
        if page % 5 == 0:
            conn.commit()
            print(f'[buyback] 页 {page}/{total_pages} 新增{ok} 失败{fail}', flush=True)
        time.sleep(SLEEP_BETWEEN)

    conn.commit()
    cursor.close()
    conn.close()
    print(f'[buyback] 完成: 新增 {ok}，失败 {fail}')


if __name__ == '__main__':
    main()
