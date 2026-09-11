#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从 Tushare Pro 下载港股数据（列表/日线行情/利润表/资产负债表/现金流量表/财务指标），
存入 MySQL 对应 hk_* 表。

数据接口:
  hk_basic           港股列表     https://tushare.pro/document/2?doc_id=253
  hk_daily           港股日线行情 https://tushare.pro/document/2?doc_id=192
  hk_income          港股利润表   https://tushare.pro/document/2?doc_id=389
  hk_balancesheet    港股资产负债表 https://tushare.pro/document/2?doc_id=390
  hk_cashflow        港股现金流量表 https://tushare.pro/document/2?doc_id=391
  hk_fina_indicator  港股财务指标 https://tushare.pro/document/2?doc_id=388

同步策略（hk_daily）:
  - 历史数据: 按 ts_code 逐个股票下载（pro.hk_daily(ts_code=...)）
  - 增量数据: 按 trade_date 每日下载全行情（pro.hk_daily(trade_date=...)），
    从 hk_sync_state 表记录的最后日期（断点）开始续传，避免重复拉取。

幂等约束: 所有表均带 UNIQUE KEY，写入用 INSERT ... ON DUPLICATE KEY UPDATE，
重复运行不会产生重复数据。

用法:
  python import_hk_tushare.py --codes 00883.HK            # 仅指定股票
  python import_hk_tushare.py --basic                      # 只同步港股列表
  python import_hk_tushare.py --daily-his                  # 历史行情（按股票）
  python import_hk_tushare.py --daily-inc                  # 增量行情（按日期，断点续传）
  python import_hk_tushare.py --financial                  # 财务（利润表/资产负债表/现金流量/指标）
  python import_hk_tushare.py --all                        # 全部（列表+历史行情+财务）
"""

import argparse
import math
import os
import time
from datetime import datetime, date, timedelta

import pymysql
import tushare as ts
from pymysql.cursors import DictCursor

from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4', cursorclass=DictCursor)

API_KEY = os.environ.get('TUSHARE_TOKEN', '')
if not API_KEY:
    raise SystemExit('缺少 TUSHARE_TOKEN 环境变量（.env 中配置 TUSHARE_TOKEN=你的tushare token）')

# 要跟踪的港股代码（Tushare 用 5 位补零 + .HK 后缀，用户输入 0883 → 00883.HK）
DEFAULT_CODES = ['00883.HK']

SLEEP = 0.3

HKD_BASIC_FIELDS = ('ts_code,name,fullname,enname,cn_spell,market,list_status,'
                    'list_date,delist_date,trade_unit,isin,curr_type')
HKD_DAILY_FIELDS = ('ts_code,trade_date,open,high,low,close,pre_close,'
                    'change,pct_chg,vol,amount')

# 港股利润表/资产负债表/现金流量表为"科目长表"格式：每行一个财务科目
HK_STMT_COLS = ('ts_code', 'end_date', 'name', 'ind_name', 'ind_value')

HK_FINA_FIELDS = ('ts_code,name,end_date,ind_type,report_type,std_report_date,'
                  'per_netcash_operate,per_oi,bps,basic_eps,diluted_eps,'
                  'operate_income,operate_income_yoy,gross_profit,gross_profit_yoy,'
                  'holder_profit,holder_profit_yoy,gross_profit_ratio,eps_ttm,'
                  'operate_income_qoq,net_profit_ratio,roe_avg,gross_profit_qoq,'
                  'roa,holder_profit_qoq,rocb,roe_yearly,roic_yearly,'
                  'report_date_sq,report_type_sq,start_date,fiscal_year,currency,'
                  'is_cny_code')


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


def create_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hk_basic (
            ts_code     VARCHAR(12)  NOT NULL COMMENT 'TS港股代码（如00883.HK）',
            name        VARCHAR(64)  COMMENT '中文简称',
            fullname    VARCHAR(128) COMMENT '中文全称',
            enname      VARCHAR(128) COMMENT '英文名称',
            cn_spell    VARCHAR(32)  COMMENT '拼音缩写',
            market      VARCHAR(16)  COMMENT '市场（主板/GEM等）',
            list_status VARCHAR(8)   COMMENT '上市状态: L上市 D退市',
            list_date   VARCHAR(8)   COMMENT '上市日期（YYYYMMDD）',
            delist_date VARCHAR(8)   COMMENT '退市日期（YYYYMMDD）',
            trade_unit  DECIMAL(16,2) COMMENT '交易单位（每手股数）',
            isin        VARCHAR(20)  COMMENT 'ISIN代码',
            curr_type   VARCHAR(8)   COMMENT '交易币种（HKD港元等）',
            update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            PRIMARY KEY (ts_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='港股列表（数据来源：Tushare Pro hk_basic 接口）'
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hk_daily (
            id          BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
            ts_code     VARCHAR(12)  NOT NULL COMMENT 'TS港股代码（如00883.HK）',
            trade_date  VARCHAR(8)   NOT NULL COMMENT '交易日期（YYYYMMDD）',
            open        DECIMAL(12,3) COMMENT '开盘价(港元)',
            high        DECIMAL(12,3) COMMENT '最高价(港元)',
            low         DECIMAL(12,3) COMMENT '最低价(港元)',
            close       DECIMAL(12,3) COMMENT '收盘价(港元)',
            pre_close   DECIMAL(12,3) COMMENT '昨收价(港元)',
            `change`    DECIMAL(12,3) COMMENT '涨跌额(港元)',
            pct_chg     DECIMAL(10,3) COMMENT '涨跌幅(%)',
            vol         DECIMAL(20,0) COMMENT '成交量(股)',
            amount      DECIMAL(24,0) COMMENT '成交额(港元)',
            update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_ts_date (ts_code, trade_date),
            KEY idx_trade_date (trade_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='港股日线行情（数据来源：Tushare Pro hk_daily 接口）'
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hk_income (
            id          BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
            ts_code     VARCHAR(12)  NOT NULL COMMENT 'TS港股代码',
            end_date    VARCHAR(8)   NOT NULL COMMENT '报告期（YYYYMMDD）',
            name        VARCHAR(64)  COMMENT '公司名称',
            ind_name    VARCHAR(64)  NOT NULL COMMENT '财务科目名称（如营业额/净利润）',
            ind_value   DECIMAL(24,4) COMMENT '财务科目值（万元）',
            update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_stmt (ts_code, end_date, ind_name),
            KEY idx_end_date (end_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='港股利润表（科目长表，数据来源：Tushare Pro hk_income 接口）'
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hk_balancesheet (
            id          BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
            ts_code     VARCHAR(12)  NOT NULL COMMENT 'TS港股代码',
            end_date    VARCHAR(8)   NOT NULL COMMENT '报告期（YYYYMMDD）',
            name        VARCHAR(64)  COMMENT '公司名称',
            ind_name    VARCHAR(64)  NOT NULL COMMENT '财务科目名称（如总资产/总负债）',
            ind_value   DECIMAL(24,4) COMMENT '财务科目值（万元）',
            update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_stmt (ts_code, end_date, ind_name),
            KEY idx_end_date (end_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='港股资产负债表（科目长表，数据来源：Tushare Pro hk_balancesheet 接口）'
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hk_cashflow (
            id          BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
            ts_code     VARCHAR(12)  NOT NULL COMMENT 'TS港股代码',
            end_date    VARCHAR(8)   NOT NULL COMMENT '报告期（YYYYMMDD）',
            name        VARCHAR(64)  COMMENT '公司名称',
            ind_name    VARCHAR(64)  NOT NULL COMMENT '财务科目名称（如经营现金流量净额）',
            ind_value   DECIMAL(24,4) COMMENT '财务科目值（万元）',
            update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_stmt (ts_code, end_date, ind_name),
            KEY idx_end_date (end_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='港股现金流量表（科目长表，数据来源：Tushare Pro hk_cashflow 接口）'
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hk_fina_indicator (
            id                  BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
            ts_code             VARCHAR(12)  NOT NULL COMMENT 'TS港股代码',
            name                VARCHAR(64)  COMMENT '公司名称',
            end_date            VARCHAR(8)   NOT NULL COMMENT '报告期（YYYYMMDD）',
            ind_type            VARCHAR(8)   COMMENT '报告类型: Q季度 Y年度',
            report_type         VARCHAR(8)   COMMENT '报告期类型（Q1一季报 Q2半年报 Q3三季报 Q4年报）',
            std_report_date     VARCHAR(8)   COMMENT '标准报告期',
            per_netcash_operate DECIMAL(12,4) COMMENT '每股经营现金流(元)',
            per_oi              DECIMAL(12,4) COMMENT '每股营业收入(元)',
            bps                 DECIMAL(12,4) COMMENT '每股净资产(元)',
            basic_eps           DECIMAL(12,4) COMMENT '基本每股收益(元)',
            diluted_eps         DECIMAL(12,4) COMMENT '稀释每股收益(元)',
            operate_income      DECIMAL(24,4) COMMENT '营业总收入(元)',
            operate_income_yoy  DECIMAL(12,4) COMMENT '营业总收入同比增长(%)',
            gross_profit        DECIMAL(24,4) COMMENT '毛利润(元)',
            gross_profit_yoy    DECIMAL(12,4) COMMENT '毛利润同比增长(%)',
            holder_profit       DECIMAL(24,4) COMMENT '归母净利润(元)',
            holder_profit_yoy   DECIMAL(12,4) COMMENT '归母净利润同比增长(%)',
            gross_profit_ratio  DECIMAL(12,4) COMMENT '毛利率(%)',
            eps_ttm             DECIMAL(12,4) COMMENT 'ttm每股收益(元)',
            operate_income_qoq  DECIMAL(12,4) COMMENT '营业总收入滚动环比增长(%)',
            net_profit_ratio    DECIMAL(12,4) COMMENT '净利率(%)',
            roe_avg             DECIMAL(12,4) COMMENT '平均净资产收益率(%)',
            gross_profit_qoq    DECIMAL(12,4) COMMENT '毛利润滚动环比增长(%)',
            roa                 DECIMAL(12,4) COMMENT '总资产净利率(%)',
            holder_profit_qoq   DECIMAL(12,4) COMMENT '归母净利润滚动环比增长(%)',
            rocb                DECIMAL(12,4) COMMENT '投入资本回报率(%)',
            roe_yearly          DECIMAL(12,4) COMMENT '年化净资产收益率(%)',
            roic_yearly         DECIMAL(12,4) COMMENT '年化投资回报率(%)',
            report_date_sq      VARCHAR(8)   COMMENT '季报日期',
            report_type_sq      VARCHAR(8)   COMMENT '报告类型',
            start_date          DECIMAL(16,0) COMMENT '会计年度起始日',
            fiscal_year         DECIMAL(16,0) COMMENT '会计年度截止日',
            currency            VARCHAR(8)   COMMENT '币种 港元(hkd)',
            is_cny_code         DECIMAL(4,0) COMMENT '是否人民币代码',
            update_time         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
            UNIQUE KEY uk_ind (ts_code, end_date, report_type),
            KEY idx_end_date (end_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='港股财务指标（数据来源：Tushare Pro hk_fina_indicator 接口）'
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hk_sync_state (
            k           VARCHAR(64)  PRIMARY KEY COMMENT '状态键（如 hk_daily_last_date）',
            v           VARCHAR(32)  COMMENT '状态值（如最后成功同步的交易日 YYYYMMDD）',
            update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='港股同步断点状态（记录增量续传位置）'
    """)


# ── 写入（幂等 upsert） ────────────────────────────────────────────────

def save_basic(rows):
    if not rows:
        return 0
    sql = """
        INSERT INTO hk_basic
            (ts_code, name, fullname, enname, cn_spell, market, list_status,
             list_date, delist_date, trade_unit, isin, curr_type)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            name=VALUES(name), fullname=VALUES(fullname), enname=VALUES(enname),
            cn_spell=VALUES(cn_spell), market=VALUES(market),
            list_status=VALUES(list_status), list_date=VALUES(list_date),
            delist_date=VALUES(delist_date), trade_unit=VALUES(trade_unit),
            isin=VALUES(isin), curr_type=VALUES(curr_type),
            update_time=CURRENT_TIMESTAMP
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def save_daily(rows):
    if not rows:
        return 0
    sql = """
        INSERT INTO hk_daily
            (ts_code, trade_date, open, high, low, close, pre_close,
             `change`, pct_chg, vol, amount)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            open=VALUES(open), high=VALUES(high), low=VALUES(low),
            close=VALUES(close), pre_close=VALUES(pre_close),
            `change`=VALUES(`change`), pct_chg=VALUES(pct_chg),
            vol=VALUES(vol), amount=VALUES(amount),
            update_time=CURRENT_TIMESTAMP
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def save_stmt(table, rows):
    """保存港股利润表/资产负债表/现金流量表（科目长表）"""
    if not rows:
        return 0
    sql = f"""
        INSERT INTO {table} (ts_code, end_date, name, ind_name, ind_value)
        VALUES (%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            name=VALUES(name), ind_value=VALUES(ind_value),
            update_time=CURRENT_TIMESTAMP
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def save_fina_indicator(rows):
    if not rows:
        return 0
    cols = HK_FINA_FIELDS.split(',')
    sql = f"""
        INSERT INTO hk_fina_indicator ({', '.join(cols)})
        VALUES ({','.join(['%s'] * len(cols))})
        ON DUPLICATE KEY UPDATE
            name=VALUES(name), ind_type=VALUES(ind_type),
            std_report_date=VALUES(std_report_date),
            per_netcash_operate=VALUES(per_netcash_operate),
            per_oi=VALUES(per_oi), bps=VALUES(bps),
            basic_eps=VALUES(basic_eps), diluted_eps=VALUES(diluted_eps),
            operate_income=VALUES(operate_income),
            operate_income_yoy=VALUES(operate_income_yoy),
            gross_profit=VALUES(gross_profit),
            gross_profit_yoy=VALUES(gross_profit_yoy),
            holder_profit=VALUES(holder_profit),
            holder_profit_yoy=VALUES(holder_profit_yoy),
            gross_profit_ratio=VALUES(gross_profit_ratio),
            eps_ttm=VALUES(eps_ttm),
            operate_income_qoq=VALUES(operate_income_qoq),
            net_profit_ratio=VALUES(net_profit_ratio),
            roe_avg=VALUES(roe_avg),
            gross_profit_qoq=VALUES(gross_profit_qoq),
            roa=VALUES(roa), holder_profit_qoq=VALUES(holder_profit_qoq),
            rocb=VALUES(rocb), roe_yearly=VALUES(roe_yearly),
            roic_yearly=VALUES(roic_yearly),
            report_date_sq=VALUES(report_date_sq),
            report_type_sq=VALUES(report_type_sq),
            start_date=VALUES(start_date), fiscal_year=VALUES(fiscal_year),
            currency=VALUES(currency), is_cny_code=VALUES(is_cny_code),
            update_time=CURRENT_TIMESTAMP
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


# ── 断点状态 ─────────────────────────────────────────────────────────

def set_state(key, val):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO hk_sync_state (k, v) VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE v=%s, update_time=CURRENT_TIMESTAMP
            """, (key, val, val))
        conn.commit()
    finally:
        conn.close()


def get_state(key, default=''):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT v FROM hk_sync_state WHERE k=%s", (key,))
            row = cur.fetchone()
        return row['v'] if row else default
    finally:
        conn.close()


# ── 各接口下载 ────────────────────────────────────────────────────────

def update_hk_basic(pro, codes=None):
    """港股列表：按 ts_code 逐个下载并幂等写入。"""
    codes = codes or DEFAULT_CODES
    detail = []
    total = 0
    for ts_code in codes:
        df = pro.hk_basic(ts_code=ts_code, fields=HKD_BASIC_FIELDS)
        if df is None or df.empty:
            detail.append({'ts_code': ts_code, 'rows': 0, 'message': '无数据'})
            continue
        rows = [tuple(to_db(r[c]) for c in HKD_BASIC_FIELDS.split(','))
                for _, r in df.iterrows()]
        n = save_basic(rows)
        total += n
        detail.append({'ts_code': ts_code, 'rows': n,
                       'name': rows[0][1] if rows else ''})
        time.sleep(SLEEP)
    return {'status': 'ok', 'total': total, 'detail': detail}


def update_hk_daily_his(pro, codes=None, start_date='19900101', end_date=None,
                        wait_on_limit=True):
    """历史行情：按 ts_code 逐个下载全量历史（可指定起止日期）。

    单次接口最多返回 5000 行，按 15 年时间窗分页（25 年历史仅需 2 窗）。
    每个窗口完成后把窗口末日期写入 hk_sync_state（hk_daily_his_{ts_code}），
    实现断点续传——中途中断后重跑自动跳过已完成窗口。
    接口限频（1次/小时）时等待 1 小时后重试当前窗口，不中断整体进度。
    """
    codes = codes or DEFAULT_CODES
    end_date = end_date or datetime.now().strftime('%Y%m%d')
    WINDOW_YEARS = 15
    RETRY_WAIT = 3600
    detail = []
    total = 0
    for ts_code in codes:
        prog = get_state(f'hk_daily_his_{ts_code}', '')
        begin = datetime.strptime(prog if prog else start_date, '%Y%m%d')
        if prog:
            begin += timedelta(days=1)
        end = datetime.strptime(end_date, '%Y%m%d')
        n_stock = 0
        date_from = date_to = ''
        message = ''
        while begin <= end:
            win_end = min(begin.replace(year=begin.year + WINDOW_YEARS) - timedelta(days=1), end)
            s = begin.strftime('%Y%m%d')
            e = win_end.strftime('%Y%m%d')
            try:
                df = pro.hk_daily(ts_code=ts_code, start_date=s, end_date=e,
                                  fields=HKD_DAILY_FIELDS)
            except Exception as ex:
                if wait_on_limit and '频率' in str(ex):
                    time.sleep(RETRY_WAIT)
                    continue
                message = f'接口异常: {str(ex)[:100]}'
                break
            if df is not None and not df.empty:
                df = df.sort_values('trade_date')
                rows = [tuple(to_db(r[c]) for c in HKD_DAILY_FIELDS.split(','))
                        for _, r in df.iterrows()]
                n = save_daily(rows)
                n_stock += n
                if not date_from or rows[0][1] < date_from:
                    date_from = rows[0][1]
                if not date_to or rows[-1][1] > date_to:
                    date_to = rows[-1][1]
            set_state(f'hk_daily_his_{ts_code}', e)
            begin = win_end + timedelta(days=1)
            time.sleep(SLEEP)
        total += n_stock
        item = {'ts_code': ts_code, 'rows': n_stock, 'date_from': date_from, 'date_to': date_to}
        if message:
            item['message'] = message
        detail.append(item)
    return {'status': 'ok', 'total': total, 'detail': detail}


def update_hk_daily_inc(pro, codes=None):
    """增量行情：从断点日期起，按 trade_date 逐日下载全港股行情（不含周休/节假日）。

    每成功写入一个交易日后将最后日期写入 hk_sync_state（hk_daily_last_date），
    实现断点续传。只保留 codes 中跟踪股票的行情行。
    """
    codes = set(codes or DEFAULT_CODES)
    today = datetime.now().strftime('%Y%m%d')
    last = get_state('hk_daily_last_date', '')
    start_day = (datetime.strptime(last, '%Y%m%d') + timedelta(days=1)) if last else datetime(2019, 1, 1)
    cur_day = start_day

    detail = []
    total = 0
    last_ok = last
    while cur_day.strftime('%Y%m%d') <= today:
        day_str = cur_day.strftime('%Y%m%d')
        df = pro.hk_daily(trade_date=day_str, fields=HKD_DAILY_FIELDS)
        if df is not None and not df.empty:
            df = df[df['ts_code'].isin(codes)]
            if not df.empty:
                rows = [tuple(to_db(r[c]) for c in HKD_DAILY_FIELDS.split(','))
                        for _, r in df.iterrows()]
                n = save_daily(rows)
                if n:
                    total += n
                    last_ok = day_str
        set_state('hk_daily_last_date', day_str)
        cur_day += timedelta(days=1)
        time.sleep(SLEEP)
        if cur_day.day == 1:
            detail.append({'progress': str(cur_day.date()), 'inserted': total})

    detail.append({'last_date': last_ok, 'total_inserted': total})
    return {'status': 'ok', 'start': start_day.strftime('%Y%m%d'),
            'end': today, 'total': total, 'detail': detail}


def update_hk_financial(pro, codes=None, end_date=None):
    """财务报表：按 ts_code 下载利润表/资产负债表/现金流量表 + 财务指标。

    注意：hk_income / hk_balancesheet / hk_cashflow / hk_fina_indicator
    为 Tushare 单独开通权限接口，当前账号若无对应权限会抛出权限错误，
    此处逐接口捕获并放入 detail 记录错误信息，不影响其它接口写入。
    """
    codes = codes or DEFAULT_CODES
    stmt_tables = [('hk_income', pro.hk_income),
                   ('hk_balancesheet', pro.hk_balancesheet),
                   ('hk_cashflow', pro.hk_cashflow)]
    detail = []

    for ts_code in codes:
        code_detail = {'ts_code': ts_code}
        # 三张科目长表
        for table, fn in stmt_tables:
            try:
                df = fn(ts_code=ts_code, end_date=end_date)
                if df is None or df.empty:
                    code_detail[table] = {'rows': 0}
                    continue
                cols = ['ts_code', 'end_date', 'name', 'ind_name', 'ind_value']
                rows = [tuple(to_db(r.get(c)) for c in cols)
                        for _, r in df.iterrows()]
                n = save_stmt(table, rows)
                code_detail[table] = {'rows': n}
            except Exception as e:
                code_detail[table] = {'error': str(e)[:120]}
            time.sleep(SLEEP)
        # 财务指标
        try:
            df = pro.hk_fina_indicator(ts_code=ts_code, fields=HK_FINA_FIELDS)
            if df is None or df.empty:
                code_detail['hk_fina_indicator'] = {'rows': 0}
            else:
                rows = [tuple(to_db(r[c]) for c in HK_FINA_FIELDS.split(','))
                        for _, r in df.iterrows()]
                n = save_fina_indicator(rows)
                code_detail['hk_fina_indicator'] = {'rows': n}
        except Exception as e:
            code_detail['hk_fina_indicator'] = {'error': str(e)[:120]}
        time.sleep(SLEEP)
        detail.append(code_detail)

    return {'status': 'ok', 'detail': detail}


def get_hk_status():
    """查询港股各表状态，返回 dict 供 API 使用。"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        tables = [
            ('hk_basic', '港股列表', 'list_date'),
            ('hk_daily', '港股日线行情', 'trade_date'),
            ('hk_income', '港股利润表', 'end_date'),
            ('hk_balancesheet', '港股资产负债表', 'end_date'),
            ('hk_cashflow', '港股现金流量表', 'end_date'),
            ('hk_fina_indicator', '港股财务指标', 'end_date'),
        ]
        detail = []
        for t, name, datecol in tables:
            cur.execute(
                f"SELECT COUNT(*) c, "
                f"(SELECT ts_code FROM `{t}` ORDER BY update_time DESC LIMIT 1) last_code, "
                f"MAX(update_time) ut, "
                f"(SELECT MAX(`{datecol}`) FROM `{t}`) mx "
                f"FROM `{t}`")
            r = cur.fetchone()
            detail.append({
                'table': t,
                'name': name,
                'rows': r['c'],
                'last_code': r['last_code'] or '',
                'max_date': str(r['mx'] or ''),
                'last_update': str(r['ut'] or ''),
            })
        cur.execute("SELECT v FROM hk_sync_state WHERE k='hk_daily_last_date'")
        r = cur.fetchone()
        detail.append({'table': 'hk_sync_state', 'name': '增量断点',
                       'resume_date': r['v'] if r else ''})
        cur.close()
        return {'status': 'ok', 'detail': detail}
    finally:
        conn.close()


def parse_codes(s):
    """把用户给的 0883 / 00883 / 00883.HK 统一转成 Tushare 5 位带后缀代码。"""
    out = []
    for tok in s.split(','):
        tok = tok.strip().upper()
        if not tok:
            continue
        if tok.endswith('.HK'):
            out.append(tok)
        else:
            out.append(tok.zfill(5) + '.HK')
    return out


def main():
    parser = argparse.ArgumentParser(description='下载 Tushare 港股数据')
    parser.add_argument('--codes', type=str, default=None,
                        help='股票代码，逗号分隔（支持 0883 / 00883 / 00883.HK 格式），默认 00883.HK')
    parser.add_argument('--basic', action='store_true', help='同步港股列表')
    parser.add_argument('--daily-his', action='store_true', help='历史行情（按股票）')
    parser.add_argument('--daily-inc', action='store_true', help='增量行情（按日期，断点续传）')
    parser.add_argument('--financial', action='store_true', help='财务报表（利润表/资产负债/现金流/指标）')
    parser.add_argument('--all', action='store_true', help='全部（列表+历史行情+财务）')
    parser.add_argument('--start', type=str, default='19900101', help='历史行情开始日期')
    parser.add_argument('--end', type=str, default=None, help='历史行情结束日期')
    args = parser.parse_args()

    codes = parse_codes(args.codes) if args.codes else DEFAULT_CODES
    pro = ts.pro_api(API_KEY)

    conn = get_conn()
    try:
        cur = conn.cursor()
        create_tables(cur)
        conn.commit()
        cur.close()
    finally:
        conn.close()

    if args.all:
        args.basic = args.daily_his = args.financial = True

    if args.basic:
        print('[basic] 开始...', flush=True)
        r = update_hk_basic(pro, codes)
        for d in r['detail']:
            print(f"[basic] {d['ts_code']}: rows={d['rows']} {(d.get('name') or d.get('message') or '')}", flush=True)

    if args.daily_his:
        print('[daily-his] 开始...', flush=True)
        r = update_hk_daily_his(pro, codes, start_date=args.start, end_date=args.end)
        for d in r['detail']:
            print(f"[daily-his] {d['ts_code']}: rows={d['rows']}",
                  f"{d.get('date_from','')}~{d.get('date_to','') if 'date_to' in d else ''}",
                  flush=True)

    if args.daily_inc:
        print('[daily-inc] 开始（断点续传）...', flush=True)
        r = update_hk_daily_inc(pro, codes)
        print(f"[daily-inc] {r['start']} ~ {r['end']} 共写入 {r['total']} 条，断点 {r['detail'][-1]['last_date']}", flush=True)

    if args.financial:
        print('[financial] 开始...', flush=True)
        r = update_hk_financial(pro, codes, end_date=args.end)
        for d in r['detail']:
            print(f"[financial] {d['ts_code']}:", flush=True)
            for k, v in d.items():
                if k == 'ts_code':
                    continue
                if isinstance(v, dict):
                    if 'error' in v:
                        print(f"     {k}: 无权限/失败 -> {v['error']}", flush=True)
                    else:
                        print(f"     {k}: {v.get('rows', 0)} 行", flush=True)

    print('\n[DONE]', flush=True)


if __name__ == '__main__':
    main()