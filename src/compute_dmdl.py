#!/home/rick/miniconda3/envs/aitrading/bin/python
"""达摩达兰估值预计算：ads_dmdl_static / ads_dmdl_mkt_daily / ads_dmdl_sector_val + 视图。

设计见 docs/达摩达兰估值模块_设计概要.md
运行: python src/compute_dmdl.py [--static|--mkt|--all]
"""
import sys, time
from datetime import date
import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

RF = 0.02          # 无风险利率
ERP = 0.055        # 股权风险溢价
KD = 0.04          # 税前债务成本
TERMINAL_G = 0.03  # 终值永续增长率

BETA = {
    '880335': 1.0,  # 化工
    '880400': 1.0,  # 医药
    '880984': 1.0,  # TDX可选
    '880983': 0.9,  # TDX消费
    '880987': 1.0,  # TDX制造
    '880988': 0.7,  # TDX公用
    '880992': 1.2,  # TDX信息
    '880993': 1.0,  # TDX综企
}
DEFAULT_BETA = 1.0

FAIR_PE = {  # 一级行业合理PE（默认，会被行业中位数覆盖）
    '880335': 18, '880400': 30, '880984': 18, '880983': 25,
    '880987': 15, '880988': 15, '880992': 35, '880993': 15,
}
DEFAULT_PE = 18
FAIR_PB = {  # 一级行业合理PB
    '880335': 2.0, '880400': 3.5, '880984': 2.0, '880983': 3.0,
    '880987': 2.0, '880988': 1.5, '880992': 4.0, '880993': 2.0,
}
DEFAULT_PB = 2.0

FINANCE_STAGES = ('finance',)

DDL_STATIC = """
CREATE TABLE ads_dmdl_static (
  stock_code       VARCHAR(10) NOT NULL COMMENT '股票代码',
  stock_name       VARCHAR(50) COMMENT '股票名称',
  report_date      DATE COMMENT '财报期（季度末）',
  norm_profit_5y   DECIMAL(20,2) COMMENT '5年正常化利润=过去5年归母净利去极值后取中位数',
  ttm_profit       DECIMAL(20,2) COMMENT 'TTM归母净利',
  invested_capital DECIMAL(20,2) COMMENT '投入资本=净资产+有息负债-现金',
  nopat            DECIMAL(20,2) COMMENT '税后经营利润=核心利润×(1-税率)',
  roic             DECIMAL(10,4) COMMENT '投入资本回报率',
  wacc             DECIMAL(10,4) COMMENT '加权平均资本成本',
  roic_minus_wacc  DECIMAL(10,4) COMMENT 'ROIC-WACC',
  life_stage       VARCHAR(10) COMMENT '生命周期：growth/cycle/finance/turnaround/decline',
  growth_rate      DECIMAL(10,4) COMMENT '未来5年增长率假设',
  net_cash_ratio   DECIMAL(10,4) COMMENT '净现比=经营现金流/归母净利',
  ar_to_revenue    DECIMAL(10,4) COMMENT '应收/营收',
  goodwill_to_equity DECIMAL(10,4) COMMENT '商誉/净资产',
  earnings_quality CHAR(1) COMMENT '盈利质量：A合格/B存疑/C高风险',
  val_eps_normal   DECIMAL(20,2) COMMENT 'E1正常化PE法（元/股）',
  val_dcf          DECIMAL(20,2) COMMENT 'E2简化DCF（元/股）',
  val_bv           DECIMAL(20,2) COMMENT 'E3净资产PB法（元/股）',
  val_low          DECIMAL(20,2) COMMENT '悲观情景价值（元/股）',
  val_high         DECIMAL(20,2) COMMENT '乐观情景价值（元/股）',
  val_final        DECIMAL(20,2) COMMENT '基准情景加权价值（元/股）',
  risk_penalty     DECIMAL(5,2) COMMENT '风险扣分0-30',
  updated_at       DATETIME COMMENT '更新时间',
  PRIMARY KEY (stock_code),
  KEY idx_roic (roic_minus_wacc),
  KEY idx_stage (life_stage),
  KEY idx_val (val_final),
  KEY idx_eq (earnings_quality)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='达摩达兰估值-财务静态层'
"""

DDL_MKT = """
CREATE TABLE ads_dmdl_mkt_daily (
  stock_code     VARCHAR(10) NOT NULL COMMENT '股票代码',
  trade_date     DATE        NOT NULL COMMENT '交易日期',
  close_price    DECIMAL(10,2) COMMENT '当日收盘价',
  total_shares   BIGINT COMMENT '总股本',
  market_cap     DECIMAL(20,2) COMMENT '总市值=收盘价×总股本',
  pe_ttm         DECIMAL(10,2) COMMENT '市盈率TTM',
  pb             DECIMAL(10,2) COMMENT '市净率=市值/净资产',
  dividend_yield DECIMAL(10,4) COMMENT '股息率',
  PRIMARY KEY (stock_code, trade_date),
  KEY idx_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='达摩达兰估值-市场动态层'
"""

DDL_SECTOR = """
CREATE TABLE ads_dmdl_sector_val (
  sector_code    VARCHAR(10) NOT NULL COMMENT '行业代码',
  sector_name    VARCHAR(50) COMMENT '行业名称',
  trade_date     DATE NOT NULL COMMENT '估值日期',
  stock_count    INT COMMENT '行业内股票数',
  sector_pe      DECIMAL(10,2) COMMENT '行业PE=行业总市值/行业总净利',
  sector_pb      DECIMAL(10,2) COMMENT '行业PB',
  pe_median      DECIMAL(10,2) COMMENT '行业内PE中位数',
  pe_pctl_low    DECIMAL(10,2) COMMENT '行业内PE 25分位',
  pe_pctl_high   DECIMAL(10,2) COMMENT '行业内PE 75分位',
  pb_median      DECIMAL(10,2) COMMENT '行业内PB中位数',
  pb_pctl_low    DECIMAL(10,2) COMMENT '行业内PB 25分位',
  pb_pctl_high   DECIMAL(10,2) COMMENT '行业内PB 75分位',
  fair_pe        DECIMAL(10,2) COMMENT '行业合理PE基准',
  fair_pb        DECIMAL(10,2) COMMENT '行业合理PB基准',
  PRIMARY KEY (sector_code, trade_date),
  KEY idx_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='达摩达兰估值-行业基准'
"""

VIEW_SQL = """
CREATE OR REPLACE VIEW v_dmdl_valuation AS
SELECT
  s.stock_code, s.stock_name, s.report_date,
  s.life_stage, s.roic, s.wacc, s.roic_minus_wacc,
  s.earnings_quality, s.risk_penalty,
  s.val_eps_normal, s.val_dcf, s.val_bv, s.val_low, s.val_high, s.val_final,
  m.trade_date, m.close_price, m.market_cap,
  m.pe_ttm, m.pb,
  sv.sector_name, sv.sector_pe, sv.sector_pb,
  sv.pe_median, sv.pb_median,
  ROUND(s.val_low  / 1e8, 2) AS intrinsic_low,
  ROUND(s.val_high / 1e8, 2) AS intrinsic_high,
  ROUND(s.val_final / 1e8, 2) AS intrinsic_value,
  ROUND((s.val_final / 1e8 / NULLIF(m.market_cap,0) - 1) * 100, 2) AS margin_of_safety,
  ROUND((s.val_final / 1e8 / NULLIF(m.market_cap,0) - 1) * 100, 2) AS discount_pct,
  GREATEST(0, ROUND(
      (CASE WHEN s.val_final / 1e8 > m.market_cap THEN 50 ELSE 0 END)
    + (CASE WHEN s.roic_minus_wacc > 0 THEN 20 ELSE 0 END)
    + (CASE WHEN s.roic > 0.10 THEN 15 ELSE 0 END)
    + (CASE WHEN s.roic_minus_wacc > 0.05 THEN 15 ELSE 0 END)
    - COALESCE(s.risk_penalty, 0), 0)) AS score
FROM ads_dmdl_static s
JOIN ads_dmdl_mkt_daily m ON s.stock_code = m.stock_code
LEFT JOIN ads_dmdl_sector_val sv
  ON sv.sector_code = (SELECT ss.sector_code FROM stock_sectors ss
                        JOIN sectors s ON ss.sector_code = s.sector_code
                        WHERE ss.stock_code = s.stock_code AND s.category='industry'
                          AND s.level <= 1 AND s.sector_name NOT LIKE 'TDX %'
                        LIMIT 1)
  AND sv.trade_date = m.trade_date
WHERE m.trade_date = (SELECT MAX(trade_date) FROM ads_dmdl_mkt_daily)
  AND s.earnings_quality IN ('A','B')
"""


def percentile(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    k = (len(vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    return round(vals[f] + (vals[c] - vals[f]) * (k - f), 2)


def compute_static(conn, log):
    cur = conn.cursor(DictCursor)

    # 1. 全市场股票
    cur.execute("SELECT stock_code, stock_name FROM stocks ORDER BY stock_code")
    stocks = cur.fetchall()

    # 2. 年度财务（5年正常化利润 + 最新年报指标）
    cur.execute("""
        SELECT a.*, i.income_tax, i.total_profit
        FROM ads_stock_annual a
        LEFT JOIN fin_income i ON a.stock_code=i.stock_code AND a.report_date=i.report_date
        ORDER BY a.stock_code, a.report_date
    """)
    annual_by_stock = {}
    for r in cur.fetchall():
        annual_by_stock.setdefault(r['stock_code'], []).append(r)

    # 3. TTM净利（最新报告期）
    cur.execute("""
        SELECT fi.stock_code, fi.report_date, fi.parent_net_profit
        FROM fin_income fi
        JOIN (SELECT stock_code, MAX(report_date) rd FROM fin_income GROUP BY stock_code) m
          ON fi.stock_code=m.stock_code AND fi.report_date=m.rd
    """)
    ttm_map = {}
    for r in cur.fetchall():
        rd = r['report_date']
        if rd.month == 12 and rd.day == 31:
            ttm_map[r['stock_code']] = float(r['parent_net_profit'] or 0)
        else:
            prev = date(rd.year-1, rd.month, rd.day)
            cur.execute("SELECT parent_net_profit FROM fin_income WHERE stock_code=%s AND report_date=%s",
                        (r['stock_code'], prev))
            prow = cur.fetchone()
            prev_same = float(prow['parent_net_profit']) if prow and prow['parent_net_profit'] else 0
            cur.execute("SELECT parent_net_profit FROM fin_income WHERE stock_code=%s AND report_date=%s",
                        (r['stock_code'], date(rd.year-1, 12, 31)))
            yrow = cur.fetchone()
            yend = float(yrow['parent_net_profit']) if yrow and yrow['parent_net_profit'] else 0
            ttm_map[r['stock_code']] = float(r['parent_net_profit'] or 0) + yend - prev_same

    # 4. 一级行业映射
    cur.execute("""
        SELECT ss.stock_code, ss.sector_code, s.sector_name
        FROM stock_sectors ss JOIN sectors s ON ss.sector_code=s.sector_code
        WHERE s.category='industry' AND s.level=0
    """)
    stock_sector = {}
    sector_names = {}
    for r in cur.fetchall():
        if r['stock_code'] not in stock_sector:
            stock_sector[r['stock_code']] = r['sector_code']
            sector_names[r['sector_code']] = r['sector_name']

    # 4b. 金融股识别：一级行业=TDX金融，或属于银行/证券/保险/多元金融板块
    cur.execute("""
        SELECT DISTINCT ss.stock_code FROM stock_sectors ss
        JOIN sectors s ON ss.sector_code=s.sector_code
        WHERE ss.sector_code IN ('880471','880472','880473','880474','880990')
    """)
    finance_codes = set(r['stock_code'] for r in cur.fetchall())
    for code, sc in stock_sector.items():
        if sc == '880990':
            finance_codes.add(code)

    # 5. ST标记
    st_codes = set()
    for s in stocks:
        if 'ST' in (s['stock_name'] or ''):
            st_codes.add(s['stock_code'])

    rows = []
    for s in stocks:
        code = s['stock_code']
        annual_rows = annual_by_stock.get(code, [])
        annual = annual_rows[-1] if annual_rows else None
        if not annual:
            continue
        sector = stock_sector.get(code, '880987')

        # 正常化利润：5年年报归母净利去极值取中位数
        profits = sorted([float(a['parent_net_profit'] or 0) for a in annual_rows[-5:]])
        if len(profits) >= 3:
            norm = sorted(profits[1:-1])[len(profits[1:-1])//2] if len(profits) > 3 else profits[len(profits)//2]
            # 用中间3年的中位数
            mid3 = profits[1:-1] if len(profits) >= 4 else profits
            norm = mid3[len(mid3)//2] if mid3 else 0
        else:
            norm = ttm_map.get(code, 0)
        norm = float(norm)

        # 核心利润（最新年报）
        core_profit = float(annual['core_profit'] or 0)
        # 有效税率
        tax = float(annual['income_tax'] or 0) if annual.get('income_tax') else 0
        tp = float(annual['total_profit'] or 0) if annual.get('total_profit') else 0
        eff_tax = tax/tp if tp else 0.25
        nopat = core_profit * (1 - eff_tax)

        # 投入资本
        equity = float(annual['total_equity'] or 0)
        idebt = float(annual['interest_debt'] or 0)
        cash = float(annual['cash_plus_tfa'] or 0)
        invcap = equity + idebt - cash

        # WACC
        beta = BETA.get(sector, DEFAULT_BETA)
        ke = RF + beta * ERP
        kd = KD * (1 - eff_tax)
        if invcap > 0:
            e_w = equity / (equity + idebt)
        else:
            e_w = 0.8
        wacc = ke * e_w + kd * (1 - e_w)

        # ROIC
        roic = (nopat / invcap) if invcap and invcap > 0 else 0
        roic_mw = round(roic - wacc, 4)

        # 生命周期
        rev_yoy = float(annual['revenue_yoy'] or 0)
        roe = float(annual['roe'] or 0)
        if code in finance_codes:
            stage = 'finance'
        elif rev_yoy > 15 and roic > 0.10:
            stage = 'growth'
        elif -3 < rev_yoy <= 15 and roe > 8:
            stage = 'cycle'
        elif rev_yoy <= -3 and float(annual['parent_net_profit'] or 0) > 0:
            stage = 'turnaround'
        else:
            stage = 'decline'

        # 增长率假设
        if stage == 'growth':
            growth_rate = min(max(rev_yoy/100, 0.05), 0.25)
        elif stage == 'cycle':
            growth_rate = 0.05
        elif stage == 'turnaround':
            growth_rate = 0.08
        else:
            growth_rate = 0.02

        # 盈利质量
        ncr = float(annual['net_cash_ratio'] or 0)
        ar = float(annual['accounts_receivable'] or 0)
        rev = float(annual['operating_revenue'] or 0)
        ar_r = ar/rev if rev else 0
        gw = float(annual['goodwill'] or 0)
        gw_e = gw/equity if equity else 0
        if code in st_codes or ncr < 0.3 or ar_r > 0.5 or gw_e > 0.4:
            eq = 'C'
        elif ncr >= 0.5 and ar_r <= 0.3 and gw_e <= 0.2:
            eq = 'A'
        else:
            eq = 'B'

        # 风险扣分
        penalty = 0
        if code in st_codes:
            penalty += 15
        if gw_e > 0.3:
            penalty += 5
        if ncr < 0 and float(annual['op_cash_flow'] or 0) < 0:
            penalty += 4
        if rev_yoy < 0 and float(annual['profit_yoy'] or 0) < 0:
            penalty += 3
        penalty = min(penalty, 30)

        # 每股价格基准：用行业PE/PB基准（先从sector_val取，此处用默认）
        fair_pe = FAIR_PE.get(sector, DEFAULT_PE)
        fair_pb = FAIR_PB.get(sector, DEFAULT_PB)
        # 金融股用更贴近实际的PB/PE基准（银行PB≈0.7、证券1.5、保险1.0，PE≈6-10）
        if stage == 'finance':
            if code.startswith('601398') or code.startswith('601939') or code.startswith('601288') or code.startswith('601988') or code.startswith('601328') or code.startswith('600036') or code.startswith('601166'):
                fair_pb, fair_pe = 0.8, 6.0
            elif code.startswith('600030') or code.startswith('601688') or code.startswith('600837') or code.startswith('601211') or code.startswith('600999'):
                fair_pb, fair_pe = 1.5, 15.0
            elif code.startswith('601318') or code.startswith('601628') or code.startswith('601601') or code.startswith('601336'):
                fair_pb, fair_pe = 1.0, 8.0

        # 三引擎（总额，亿元）—— 统一以总额存储，视图直接与 market_cap(亿) 比较
        val_e1 = norm * fair_pe
        val_e3 = equity * fair_pb
        # DCF
        if norm > 0 and wacc > TERMINAL_G:
            cf = 0
            for yr in range(1, 6):
                cf += norm * (1+growth_rate)**yr / (1+wacc)**yr
            tv = norm * (1+growth_rate)**5 / (wacc - TERMINAL_G)
            val_dcf_v = cf + tv / (1+wacc)**5
        else:
            val_dcf_v = 0

        # 加权
        if stage == 'finance':
            w1, w2, w3 = 0.30, 0.10, 0.60
        elif stage == 'growth':
            w1, w2, w3 = 0.30, 0.50, 0.20
        else:
            w1, w2, w3 = 0.60, 0.30, 0.10
        val_final = w1*val_e1 + w2*val_dcf_v + w3*val_e3
        # 悲观/乐观
        val_low = w1*val_e1*0.8 + w2*val_dcf_v*0.7 + w3*val_e3*0.9
        val_high = w1*val_e1*1.2 + w2*val_dcf_v*1.3 + w3*val_e3*1.1

        rows.append((
            code, s['stock_name'], annual['report_date'], round(norm,2), round(ttm_map.get(code,0),2),
            round(invcap,2), round(nopat,2), round(roic,4), round(wacc,4), roic_mw,
            stage, round(growth_rate,4), round(ncr,4), round(ar_r,4), round(gw_e,4), eq,
            round(val_e1,2), round(val_dcf_v,2), round(val_e3,2),
            round(val_low,2), round(val_high,2), round(val_final,2), penalty
        ))
        if len(rows) % 2000 == 0:
            log(f"  static: {len(rows)}")

    w = conn.cursor()
    w.executemany("""
        INSERT INTO ads_dmdl_static
        (stock_code, stock_name, report_date, norm_profit_5y, ttm_profit,
         invested_capital, nopat, roic, wacc, roic_minus_wacc,
         life_stage, growth_rate, net_cash_ratio, ar_to_revenue, goodwill_to_equity, earnings_quality,
         val_eps_normal, val_dcf, val_bv, val_low, val_high, val_final, risk_penalty, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
    """, rows)
    conn.commit()
    log(f"  ads_dmdl_static: {len(rows)} rows")
    return len(rows)


def compute_mkt(conn, log):
    cur = conn.cursor(DictCursor)
    # 最新交易日
    cur.execute("SELECT MAX(trade_date) d FROM daily_kline")
    td = cur.fetchone()['d']
    cur.execute("SELECT MAX(trade_date) d FROM ads_dmdl_mkt_daily")
    existing = cur.fetchone()['d']
    if existing and existing >= td:
        log(f"  mkt 已是最新 ({td})")
        return td

    # 最新收盘价
    cur.execute("""
        SELECT k.stock_code, k.close_price, k.trade_date
        FROM daily_kline k
        JOIN (SELECT stock_code, MAX(trade_date) md FROM daily_kline WHERE close_price>0 GROUP BY stock_code) m
          ON k.stock_code=m.stock_code AND k.trade_date=m.md
    """)
    prices = {r['stock_code']: (r['close_price'], r['trade_date']) for r in cur.fetchall()}
    # 股本
    cur.execute("SELECT stock_code, total_shares FROM stock_shares_dfcf")
    shares = {r['stock_code']: int(r['total_shares']) if r['total_shares'] else 0 for r in cur.fetchall()}
    # TTM净利
    cur.execute("SELECT stock_code, ttm_profit FROM ads_dmdl_static")
    ttm = {r['stock_code']: float(r['ttm_profit'] or 0) for r in cur.fetchall()}
    # 净资产
    cur.execute("SELECT stock_code, total_equity FROM ads_stock_annual a WHERE report_date=(SELECT MAX(report_date) FROM ads_stock_annual WHERE stock_code=a.stock_code)")
    equity_map = {r['stock_code']: float(r['total_equity'] or 0) for r in cur.fetchall()}
    # 股息率
    cur.execute("""
        SELECT d.stock_code, d.cash_per_10, d.dividend_yield
        FROM stock_dividend d
        JOIN (SELECT stock_code, MAX(report_date) rd FROM stock_dividend WHERE assign_progress='实施分配' GROUP BY stock_code) m
          ON d.stock_code=m.stock_code AND d.report_date=m.rd
    """)
    div_map = {r['stock_code']: (float(r['dividend_yield']) if r['dividend_yield'] else 0.0) for r in cur.fetchall()}

    rows = []
    for code, (px, tdate) in prices.items():
        sh = shares.get(code, 0)
        if not sh or not px:
            continue
        mcap = round(float(px)*sh/1e8, 2)
        t = ttm.get(code, 0)
        pe = round(mcap*1e8/t, 2) if t and t > 0 else None
        eq = equity_map.get(code, 0)
        pb = round(mcap*1e8/eq, 2) if eq and eq > 0 else None
        rows.append((code, td, round(float(px),2), sh, mcap, pe, pb, div_map.get(code)))
        if len(rows) % 3000 == 0:
            log(f"  mkt: {len(rows)}")

    w = conn.cursor()
    w.executemany("""
        INSERT INTO ads_dmdl_mkt_daily
        (stock_code, trade_date, close_price, total_shares, market_cap, pe_ttm, pb, dividend_yield)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE close_price=VALUES(close_price), total_shares=VALUES(total_shares),
          market_cap=VALUES(market_cap), pe_ttm=VALUES(pe_ttm), pb=VALUES(pb), dividend_yield=VALUES(dividend_yield)
    """, rows)
    conn.commit()
    log(f"  ads_dmdl_mkt_daily: {len(rows)} rows @ {td}")
    return td


def compute_sector_val(conn, log, trade_date):
    cur = conn.cursor(DictCursor)
    cur.execute("DELETE FROM ads_dmdl_sector_val WHERE trade_date=%s", (trade_date,))
    conn.commit()
    cur.execute("SELECT stock_code, trade_date, pe_ttm, pb, market_cap FROM ads_dmdl_mkt_daily WHERE trade_date=%s", (trade_date,))
    mkt = cur.fetchall()
    cur.execute("""
        SELECT ss.stock_code, ss.sector_code, s.sector_name
        FROM stock_sectors ss JOIN sectors s ON ss.sector_code=s.sector_code
        WHERE s.category='industry' AND s.level <= 1
          AND s.sector_name NOT LIKE 'TDX%'
    """)
    sec_map = {}
    for r in cur.fetchall():
        sec_map.setdefault(r['sector_code'], {'name': r['sector_name'], 'stocks': []})
        sec_map[r['sector_code']]['stocks'].append(r['stock_code'])

    cur.execute("SELECT stock_code, ttm_profit FROM ads_dmdl_static")
    ttm = {r['stock_code']: float(r['ttm_profit'] or 0) for r in cur.fetchall()}
    cur.execute("SELECT stock_code, total_equity FROM ads_stock_annual a WHERE report_date=(SELECT MAX(report_date) FROM ads_stock_annual WHERE stock_code=a.stock_code)")
    eq_map = {r['stock_code']: float(r['total_equity'] or 0) for r in cur.fetchall()}

    by_stock = {r['stock_code']: r for r in mkt}
    rows = []
    for sc, info in sec_map.items():
        pes, pbs, tot_mcap, tot_profit, tot_eq = [], [], 0, 0, 0
        for code in info['stocks']:
            r = by_stock.get(code)
            if not r:
                continue
            if r['pe_ttm'] and r['pe_ttm'] > 0:
                pes.append(float(r['pe_ttm']))
            if r['pb'] and r['pb'] > 0:
                pbs.append(float(r['pb']))
            tot_mcap += float(r['market_cap'] or 0)
            tot_profit += ttm.get(code, 0)
            tot_eq += eq_map.get(code, 0)
        pe = round(tot_mcap*1e8/tot_profit, 2) if tot_profit > 0 else None
        pb = round(tot_mcap*1e8/tot_eq, 2) if tot_eq > 0 else None
        rows.append((
            sc, info['name'], trade_date, len(pes),
            pe, pb,
            percentile(pes, 0.5), percentile(pes, 0.25), percentile(pes, 0.75),
            percentile(pbs, 0.5), percentile(pbs, 0.25), percentile(pbs, 0.75),
            percentile(pes, 0.5) or FAIR_PE.get(sc, DEFAULT_PE),
            percentile(pbs, 0.5) or FAIR_PB.get(sc, DEFAULT_PB),
        ))
    w = conn.cursor()
    w.executemany("""
        INSERT INTO ads_dmdl_sector_val
        (sector_code, sector_name, trade_date, stock_count, sector_pe, sector_pb,
         pe_median, pe_pctl_low, pe_pctl_high, pb_median, pb_pctl_low, pb_pctl_high,
         fair_pe, fair_pb)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE sector_name=VALUES(sector_name), stock_count=VALUES(stock_count),
          sector_pe=VALUES(sector_pe), sector_pb=VALUES(sector_pb),
          pe_median=VALUES(pe_median), pe_pctl_low=VALUES(pe_pctl_low), pe_pctl_high=VALUES(pe_pctl_high),
          pb_median=VALUES(pb_median), pb_pctl_low=VALUES(pb_pctl_low), pb_pctl_high=VALUES(pb_pctl_high),
          fair_pe=VALUES(fair_pe), fair_pb=VALUES(fair_pb)
    """, rows)
    conn.commit()
    log(f"  ads_dmdl_sector_val: {len(rows)} sectors @ {trade_date}")


def main():
    mode = 'all'
    if len(sys.argv) > 1:
        mode = sys.argv[1].lstrip('-')
    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    t0 = time.time()
    def log(msg):
        print(msg, flush=True)

    if mode in ('all', 'create'):
        log('创建表...')
        cur = conn.cursor()
        for t, ddl in [('ads_dmdl_static', DDL_STATIC), ('ads_dmdl_mkt_daily', DDL_MKT), ('ads_dmdl_sector_val', DDL_SECTOR)]:
            cur.execute(f"DROP TABLE IF EXISTS {t}")
            cur.execute(ddl)
        conn.commit()
        if mode == 'create':
            conn.close()
            return

    if mode in ('all', 'static'):
        log('Step 1/3: ads_dmdl_static (静态估值)...')
        compute_static(conn, log)

    if mode in ('all', 'mkt'):
        log('Step 2/3: ads_dmdl_mkt_daily (市值快照)...')
        td = compute_mkt(conn, log)

    if mode in ('all', 'sector'):
        log('Step 3/3: ads_dmdl_sector_val (行业基准)...')
        cur = conn.cursor()
        cur.execute("SELECT MAX(trade_date) d FROM ads_dmdl_mkt_daily")
        td = cur.fetchone()['d']
        compute_sector_val(conn, log, td)

    log('刷新视图...')
    cur = conn.cursor()
    cur.execute(VIEW_SQL)
    conn.commit()
    log(f"Done in {int(time.time()-t0)}s")
    conn.close()


if __name__ == '__main__':
    main()
