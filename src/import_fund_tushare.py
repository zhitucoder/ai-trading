#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从 Tushare Pro 下载公募基金列表与公募基金持仓数据，存入 MySQL。

数据接口:
  fund_basic      公募基金列表   https://tushare.pro/document/2?doc_id=19
  fund_portfolio  公募基金持仓   https://tushare.pro/document/2?doc_id=121

用法:
  python import_fund_tushare.py
  python import_fund_tushare.py --quarters 8      # 持仓下载最近N个季度
  python import_fund_tushare.py --quarters 20     # 最近20个季度
"""

import argparse
import math
import time

import pymysql
import tushare as ts
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4', cursorclass=DictCursor)

API_KEY = 'YOUR_TUSHARE_TOKEN'

PAGE_SIZE_BASIC = 15000   # fund_basic 单次最大15000条
PAGE_SIZE_PF = 8000       # fund_portfolio 实测单次约8000条
SLEEP = 0.3               # 两次请求间隔（秒），5000积分约200次/分钟


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
        CREATE TABLE IF NOT EXISTS fund_basic (
            ts_code         VARCHAR(12)  NOT NULL COMMENT 'TS基金代码（如512850.SH / 001753.OF）',
            name            VARCHAR(64)  COMMENT '基金简称',
            management      VARCHAR(64)  COMMENT '基金管理人',
            custodian       VARCHAR(64)  COMMENT '基金托管人',
            fund_type       VARCHAR(32)  COMMENT '投资类型（股票型/混合型/债券型/货币型等）',
            found_date      VARCHAR(8)   COMMENT '基金成立日期（YYYYMMDD）',
            due_date        VARCHAR(8)   COMMENT '基金到期日期（YYYYMMDD）',
            list_date       VARCHAR(8)   COMMENT '上市时间（YYYYMMDD）',
            issue_date      VARCHAR(8)   COMMENT '发行日期（YYYYMMDD）',
            delist_date     VARCHAR(8)   COMMENT '退市日期（YYYYMMDD）',
            issue_amount    DECIMAL(18,4) COMMENT '发行份额(亿)',
            m_fee           DECIMAL(10,4) COMMENT '管理费',
            c_fee           DECIMAL(10,4) COMMENT '托管费',
            duration_year   DECIMAL(10,4) COMMENT '存续期(年)',
            p_value         DECIMAL(10,4) COMMENT '面值',
            min_amount      DECIMAL(10,4) COMMENT '起点金额(万元)',
            exp_return      DECIMAL(10,4) COMMENT '预期收益率',
            benchmark       VARCHAR(256) COMMENT '业绩比较基准',
            status          VARCHAR(4)   COMMENT '存续状态: D摘牌 I发行 L已上市',
            invest_type     VARCHAR(32)  COMMENT '投资风格',
            type            VARCHAR(32)  COMMENT '基金类型',
            trustee         VARCHAR(64)  COMMENT '受托人',
            purc_startdate  VARCHAR(8)   COMMENT '日常申购起始日（YYYYMMDD）',
            redm_startdate  VARCHAR(8)   COMMENT '日常赎回起始日（YYYYMMDD）',
            market          VARCHAR(4)   COMMENT '交易市场: E场内 O场外',
            update_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            PRIMARY KEY (ts_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='公募基金列表（数据来源：Tushare Pro fund_basic 接口）'
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fund_portfolio (
            id              BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
            ts_code         VARCHAR(12)  NOT NULL COMMENT 'TS基金代码',
            ann_date        VARCHAR(8)   NOT NULL COMMENT '公告日期（YYYYMMDD）',
            end_date        VARCHAR(8)   NOT NULL COMMENT '报告期截止日期（YYYYMMDD，季度末）',
            symbol          VARCHAR(12)  NOT NULL COMMENT '股票代码（如600519.SH）',
            mkv             DECIMAL(20,4) COMMENT '持有股票市值(元)',
            amount          DECIMAL(20,4) COMMENT '持有股票数量(股)',
            stk_mkv_ratio   DECIMAL(10,4) COMMENT '占股票市值比(%)',
            stk_float_ratio DECIMAL(10,4) COMMENT '占流通股本比例(%)',
            update_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_fund_holding (ts_code, end_date, symbol, ann_date),
            KEY idx_end_date (end_date),
            KEY idx_symbol (symbol)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='公募基金持仓（季报，数据来源：Tushare Pro fund_portfolio 接口）'
    """)


def quarters_from(start_ymd):
    """返回 start_ymd 至最近已结束季度的所有季度末日期（YYYYMMDD），升序。"""
    end_day = {3: 31, 6: 30, 9: 30, 12: 31}
    qs = []
    y, m = int(start_ymd[:4]), int(start_ymd[4:6])
    while True:
        q = (m - 1) // 3
        end_m = q * 3 + 3
        qs.append(f'{y:04d}{end_m:02d}{end_day[end_m]:02d}')
        m += 3
        if m > 12:
            m = 3
            y += 1
        if (y, m) > (time.localtime()[0], time.localtime()[1]):
            break
    return qs


def recent_quarters(n):
    """返回最近 n 个季度末日期（YYYYMMDD），从最近一个已结束的季度往前推。"""
    y, m = time.localtime()[:2]
    end_day = {3: 31, 6: 30, 9: 30, 12: 31}
    # 当前季度还未结束，从上一个季度末开始
    m -= 3
    if m <= 0:
        m += 12
        y -= 1
    quarters = []
    while len(quarters) < n:
        q = (m - 1) // 3          # 0,1,2,3
        end_m = q * 3 + 3         # 3,6,9,12
        quarters.append(f'{y:04d}{end_m:02d}{end_day[end_m]:02d}')
        m -= 3
        if m <= 0:
            m += 12
            y -= 1
    return quarters


def download_basic(pro):
    """下载 fund_basic：场内E + 场外O，存续状态L（上市中）。"""
    total = 0
    for market in ('E', 'O'):
        offset = 0
        while True:
            df = pro.fund_basic(market=market, status='L',
                                limit=PAGE_SIZE_BASIC, offset=offset)
            n = len(df)
            if n == 0:
                break
            save_basic(df)
            total += n
            print(f'[basic] market={market} 已下载 {total} 条 (offset={offset})', flush=True)
            if n < PAGE_SIZE_BASIC:
                break
            offset += n
            time.sleep(SLEEP)
    print(f'[basic] 完成，共 {total} 条')
    return total


def download_portfolio(pro, quarters):
    """下载 fund_portfolio：按报告期逐个下载，支持 limit/offset 分页。"""
    total = 0
    for period in quarters:
        offset = 0
        p_total = 0
        while True:
            df = pro.fund_portfolio(period=period, limit=PAGE_SIZE_PF, offset=offset)
            n = len(df)
            if n == 0:
                break
            save_portfolio(df)
            p_total += n
            if n < PAGE_SIZE_PF:
                break
            offset += n
            time.sleep(SLEEP)
        total += p_total
        print(f'[portfolio] 报告期 {period} 下载 {p_total} 条，累计 {total}', flush=True)
    print(f'[portfolio] 完成，共 {total} 条')
    return total


def save_basic(df):
    sql = """
        INSERT INTO fund_basic
            (ts_code, name, management, custodian, fund_type, found_date, due_date,
             list_date, issue_date, delist_date, issue_amount, m_fee, c_fee,
             duration_year, p_value, min_amount, exp_return, benchmark, status,
             invest_type, type, trustee, purc_startdate, redm_startdate, market)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            name=VALUES(name), management=VALUES(management), custodian=VALUES(custodian),
            fund_type=VALUES(fund_type), found_date=VALUES(found_date),
            due_date=VALUES(due_date), list_date=VALUES(list_date),
            issue_date=VALUES(issue_date), delist_date=VALUES(delist_date),
            issue_amount=VALUES(issue_amount), m_fee=VALUES(m_fee), c_fee=VALUES(c_fee),
            duration_year=VALUES(duration_year), p_value=VALUES(p_value),
            min_amount=VALUES(min_amount), exp_return=VALUES(exp_return),
            benchmark=VALUES(benchmark), status=VALUES(status), invest_type=VALUES(invest_type),
            type=VALUES(type), trustee=VALUES(trustee), purc_startdate=VALUES(purc_startdate),
            redm_startdate=VALUES(redm_startdate), market=VALUES(market),
            update_time=CURRENT_TIMESTAMP
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            rows = [tuple(to_db(r[c]) for c in (
                'ts_code', 'name', 'management', 'custodian', 'fund_type', 'found_date',
                'due_date', 'list_date', 'issue_date', 'delist_date', 'issue_amount',
                'm_fee', 'c_fee', 'duration_year', 'p_value', 'min_amount',
                'exp_return', 'benchmark', 'status', 'invest_type', 'type',
                'trustee', 'purc_startdate', 'redm_startdate', 'market'))
                for _, r in df.iterrows()]
            cur.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()


def save_portfolio(df):
    sql = """
        INSERT INTO fund_portfolio
            (ts_code, ann_date, end_date, symbol, mkv, amount, stk_mkv_ratio, stk_float_ratio)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            mkv=VALUES(mkv), amount=VALUES(amount),
            stk_mkv_ratio=VALUES(stk_mkv_ratio), stk_float_ratio=VALUES(stk_float_ratio),
            update_time=CURRENT_TIMESTAMP
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            rows = [tuple(to_db(r[c]) for c in (
                'ts_code', 'ann_date', 'end_date', 'symbol', 'mkv', 'amount',
                'stk_mkv_ratio', 'stk_float_ratio'))
                for _, r in df.iterrows()]
            cur.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quarters', type=int, default=8,
                        help='持仓数据下载最近N个季度（默认8）')
    parser.add_argument('--start', type=str, default=None,
                        help='从指定报告期（YYYYMMDD）开始下载到最近季度，覆盖--quarters')
    args = parser.parse_args()

    pro = ts.pro_api(API_KEY)

    conn = get_conn()
    try:
        cur = conn.cursor()
        create_tables(cur)
        conn.commit()
    finally:
        conn.close()

    download_basic(pro)
    if args.start:
        download_portfolio(pro, quarters_from(args.start))
    else:
        download_portfolio(pro, recent_quarters(args.quarters))


if __name__ == '__main__':
    main()
