#!/home/rick/miniconda3/envs/aitrading/bin/python
"""统一分析预计算：生成 ads_stock_annual / ads_stock_latest / ads_sector_annual / ads_sector_latest。

用途：个股六维分析 / 行业俯瞰分析所需的派生指标（核心利润、净现金、ROE、毛利率、
同比增速、市值、PE等）全部在此一次性算好，分析时直接查询 ads_* 表，无需重复计算。

运行: python src/compute_ads.py
"""
import time
from datetime import date
import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')


def _drop_table(cur, name):
    cur.execute(f"DROP TABLE IF EXISTS {name}")


def create_tables(cur):
    cur.execute("""
        CREATE TABLE ads_stock_annual (
          id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
          stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
          report_date DATE NOT NULL COMMENT '年报报告期（仅12-31）',
          operating_revenue DECIMAL(20,2) COMMENT '营业总收入(元)',
          operating_cost DECIMAL(20,2) COMMENT '营业总成本(元)',
          gross_profit DECIMAL(20,2) COMMENT '毛利润(元)=营收-成本',
          gross_margin DECIMAL(10,4) COMMENT '毛利率(%)=(营收-成本)/营收×100',
          selling_expense DECIMAL(20,2) COMMENT '销售费用(元)',
          admin_expense DECIMAL(20,2) COMMENT '管理费用(元)',
          finance_expense DECIMAL(20,2) COMMENT '财务费用(元)',
          core_profit DECIMAL(20,2) COMMENT '核心利润(元)=营收-成本-销售费用-管理费用',
          core_margin DECIMAL(10,4) COMMENT '核心利润率(%)=核心利润/营收×100',
          parent_net_profit DECIMAL(20,2) COMMENT '归母净利润(元)',
          net_margin DECIMAL(10,4) COMMENT '净利率(%)=归母净利/营收×100',
          total_assets DECIMAL(20,2) COMMENT '总资产(元)',
          total_liabilities DECIMAL(20,2) COMMENT '总负债(元)',
          total_equity DECIMAL(20,2) COMMENT '净资产(元)',
          debt_ratio DECIMAL(10,4) COMMENT '资产负债率(%)=总负债/总资产×100',
          cash DECIMAL(20,2) COMMENT '货币资金(元)',
          trading_fa DECIMAL(20,2) COMMENT '交易性金融资产(元)',
          cash_plus_tfa DECIMAL(20,2) COMMENT '现金+交易性金融资产(元)',
          short_borrow DECIMAL(20,2) COMMENT '短期借款(元)',
          long_borrow DECIMAL(20,2) COMMENT '长期借款(元)',
          interest_debt DECIMAL(20,2) COMMENT '有息负债(元)=短借+长借',
          net_cash DECIMAL(20,2) COMMENT '净现金(元)=现金+交易性金融资产-短借-长借',
          accounts_receivable DECIMAL(20,2) COMMENT '应收账款(元)',
          inventory DECIMAL(20,2) COMMENT '存货(元)',
          fixed_assets DECIMAL(20,2) COMMENT '固定资产(元)',
          goodwill DECIMAL(20,2) COMMENT '商誉(元)',
          op_cash_flow DECIMAL(20,2) COMMENT '经营现金流(元)',
          net_cash_ratio DECIMAL(10,4) COMMENT '净现比=经营现金流/归母净利',
          roe DECIMAL(10,4) COMMENT 'ROE(%)=归母净利/净资产×100',
          revenue_yoy DECIMAL(10,4) COMMENT '营收同比(%)',
          profit_yoy DECIMAL(10,4) COMMENT '净利同比(%)',
          UNIQUE KEY uk_stock_date (stock_code, report_date),
          KEY idx_date (report_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个股年度财务（年报口径派生指标，core_profit/net_cash等）'
    """)
    cur.execute("""
        CREATE TABLE ads_stock_latest (
          stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
          stock_name VARCHAR(50) COMMENT '股票名称',
          report_date DATE COMMENT '最新财务报告期',
          annual_report_date DATE COMMENT '最新年报日期',
          latest_price DECIMAL(10,2) COMMENT '最新收盘价(元)',
          total_shares BIGINT COMMENT '总股本(股, 来自stock_shares_dfcf)',
          market_cap DECIMAL(20,2) COMMENT '总市值(亿元)=最新价×总股本/1e8',
          pe_ttm DECIMAL(10,2) COMMENT '市盈率TTM=市值/TTM归母净利',
          dividend_yield DECIMAL(10,4) COMMENT '股息率(%)',
          revenue DECIMAL(20,2) COMMENT '最新报告期营收(元)',
          profit DECIMAL(20,2) COMMENT '最新报告期归母净利(元)',
          revenue_yoy DECIMAL(10,4) COMMENT '营收同比(%)',
          profit_yoy DECIMAL(10,4) COMMENT '净利同比(%)',
          revenue_annual DECIMAL(20,2) COMMENT '最新年报营收(元)',
          profit_annual DECIMAL(20,2) COMMENT '最新年报归母净利(元)',
          gross_margin DECIMAL(10,4) COMMENT '毛利率(%)=年报口径',
          core_margin DECIMAL(10,4) COMMENT '核心利润率(%)=年报口径',
          net_margin DECIMAL(10,4) COMMENT '净利率(%)=年报口径',
          roe DECIMAL(10,4) COMMENT 'ROE(%)=年报口径',
          roe_ttm DECIMAL(10,4) COMMENT 'ROE-TTM(⚠当前实现=roe,见compute_ads.py:426)',
          debt_ratio DECIMAL(10,4) COMMENT '资产负债率(%)=年报口径',
          net_cash DECIMAL(20,2) COMMENT '净现金(元)=年报口径',
          net_cash_ratio DECIMAL(10,4) COMMENT '净现比=年报口径',
          op_cash_flow DECIMAL(20,2) COMMENT '经营现金流(元)=年报口径',
          PRIMARY KEY (stock_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个股最新快照（市值/PE_TTM/股息率/最新财务同比）'
    """)
    cur.execute("""
        CREATE TABLE ads_sector_annual (
          id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
          sector_code VARCHAR(10) NOT NULL COMMENT '板块代码',
          category VARCHAR(20) COMMENT '板块分类(行业/地区/概念/风格)',
          sector_name VARCHAR(50) COMMENT '板块名称',
          report_date DATE NOT NULL COMMENT '年报报告期',
          stock_count INT COMMENT '成分股数',
          total_revenue DECIMAL(20,2) COMMENT '板块总营收(元)',
          total_net_profit DECIMAL(20,2) COMMENT '板块总净利(元)',
          avg_gross_margin DECIMAL(10,4) COMMENT '平均毛利率(%)',
          avg_roe DECIMAL(10,4) COMMENT '平均ROE(%)',
          avg_debt_ratio DECIMAL(10,4) COMMENT '平均资产负债率(%)',
          revenue_yoy DECIMAL(10,4) COMMENT '板块营收同比(%)',
          profit_yoy DECIMAL(10,4) COMMENT '板块净利同比(%)',
          UNIQUE KEY uk_sector_date (sector_code, report_date),
          KEY idx_date (report_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块年度财务汇总（按板块×年报聚合ads_stock_annual）'
    """)
    cur.execute("""
        CREATE TABLE ads_sector_latest (
          sector_code VARCHAR(10) NOT NULL COMMENT '板块代码',
          category VARCHAR(20) COMMENT '板块分类(行业/地区/概念/风格)',
          sector_name VARCHAR(50) COMMENT '板块名称',
          report_date DATE COMMENT '最新年报日期(板块内MAX)',
          stock_count INT COMMENT '成分股数',
          total_market_cap DECIMAL(20,2) COMMENT '板块总市值(亿元)',
          total_revenue DECIMAL(20,2) COMMENT '板块总营收(元)',
          total_net_profit DECIMAL(20,2) COMMENT '板块总净利(元)',
          revenue_yoy DECIMAL(10,4) COMMENT '板块营收同比(%)',
          profit_yoy DECIMAL(10,4) COMMENT '板块净利同比(%)',
          avg_gross_margin DECIMAL(10,4) COMMENT '平均毛利率(%)',
          avg_roe DECIMAL(10,4) COMMENT '平均ROE(%)',
          avg_debt_ratio DECIMAL(10,4) COMMENT '平均资产负债率(%)',
          PRIMARY KEY (sector_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块最新快照（按板块聚合ads_stock_latest）'
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ads_refresh_log (
          id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
          status VARCHAR(20) NOT NULL COMMENT '运行状态: running/done/error',
          total_stocks INT COMMENT '总股票数',
          computed_stocks INT COMMENT '已计算股票数',
          error_stocks INT COMMENT '出错股票数',
          started_at DATETIME COMMENT '开始时间',
          finished_at DATETIME COMMENT '结束时间',
          message VARCHAR(500) COMMENT '运行摘要'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分析预计算刷新日志（每POST /api/data/update-ads一条）'
    """)
    cur.execute("""
        CREATE TABLE ads_stock_fund (
          id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
          stock_code  VARCHAR(10) NOT NULL COMMENT '股票代码(600519)',
          end_date    VARCHAR(8)  NOT NULL COMMENT '报告期(20210331…)',
          quarter     CHAR(6)     COMMENT '季度标签(21Q1…)',
          report_type CHAR(1)     COMMENT '披露口径: F=半年报/年报(全部持仓), Q=季报(前十大)',
          fund_count      INT      COMMENT '持仓基金家数(全部)',
          active_count    INT      COMMENT '主动基金家数',
          passive_count   INT      COMMENT '被动(指数/ETF)基金家数',
          total_amount    DECIMAL(20,4) COMMENT '基金持仓总股数(股)',
          total_mkv       DECIMAL(20,4) COMMENT '基金持仓总市值(元)',
          total_shares    BIGINT   COMMENT '当期总股本(股, 取stock_shares_dfcf, 用于送转识别)',
          close_price     DECIMAL(10,2) COMMENT '季度末收盘价(不复权)',
          intra_high      DECIMAL(10,2) COMMENT '季内盘中最高价(不复权)',
          update_time     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                          ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间(插入/更新自动写入)',
          UNIQUE KEY uk_stock_q (stock_code, end_date),
          KEY idx_date (end_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='个股×季度 基金持仓聚合(基金家数/持股量/市值)+季度股价(预计算, 画像页联动图用)'
    """)
    cur.execute("""
        CREATE TABLE ads_stock_fund_trend (
          stock_code           VARCHAR(10) NOT NULL PRIMARY KEY COMMENT '股票代码',
          d21Q4 TINYINT, d22Q2 TINYINT, d22Q4 TINYINT, d23Q2 TINYINT, d23Q4 TINYINT,
          d24Q2 TINYINT, d24Q4 TINYINT, d25Q2 TINYINT, d25Q4 TINYINT, d26Q2 TINYINT,
          fc21Q2 INT COMMENT '21Q2 持仓基金家数', fc21Q4 INT COMMENT '21Q4 持仓基金家数',
          fc22Q2 INT COMMENT '22Q2 持仓基金家数', fc22Q4 INT COMMENT '22Q4 持仓基金家数',
          fc23Q2 INT COMMENT '23Q2 持仓基金家数', fc23Q4 INT COMMENT '23Q4 持仓基金家数',
          fc24Q2 INT COMMENT '24Q2 持仓基金家数', fc24Q4 INT COMMENT '24Q4 持仓基金家数',
          fc25Q2 INT COMMENT '25Q2 持仓基金家数', fc25Q4 INT COMMENT '25Q4 持仓基金家数',
          fc26Q2 INT COMMENT '26Q2 持仓基金家数',
          recent8_up          INT COMMENT '最近8个两季度增量中+1个数',
          recent8_net         INT COMMENT '最近8个两季度净增数(2×recent8_up-8)',
          recent6_up          INT COMMENT '最近6个两季度增量中+1个数',
          recent4_up          INT COMMENT '最近4个两季度增量中+1个数',
          max_consec_growth   INT COMMENT '最长连续增长(增量=1)季度数, 0=无',
          max_consec_decline  INT COMMENT '最长连续减少(增量=-1)季度数, 0=无',
          recent2q_fund_count INT COMMENT '最近2个完整季度持仓基金家数均值',
          recent4q_fund_count INT COMMENT '最近4个完整季度持仓基金家数均值',
          recent1q_fund_count INT COMMENT '最近1个完整季度(最新Q2/Q4)持仓基金家数',
          prev1q_fund_count  INT COMMENT '上一个完整季度持仓基金家数',
          recent1q_fund_growth DECIMAL(10,2) COMMENT '最近1季度家数同比%=(recent1q_fund_count-prev1q_fund_count)/prev1q_fund_count×100, prev1q=0时NULL',
          recent8q_amount     DECIMAL(20,4) COMMENT '最近8个完整季度持股量均值(股)',
          prev2q_fund_count   INT COMMENT '上一个两季度(最新2完整点之前的再往前2个完整点)家数均值',
          recent2q_fund_growth DECIMAL(10,2) COMMENT '最近两季度家数增长率%=(recent2q_fund_count-prev2q_fund_count)/prev2q_fund_count×100, prev2q=0时NULL',
          update_time         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          KEY idx_r8up (recent8_up),
          KEY idx_r8net (recent8_net),
          KEY idx_r6up (recent6_up),
          KEY idx_r4up (recent4_up),
          KEY idx_mcg (max_consec_growth),
          KEY idx_mcd (max_consec_decline),
          KEY idx_r2g (recent2q_fund_growth)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
          COMMENT='个股基金持仓季度增减序列(列式+1/-1)+派生统计(画像筛选预计算, 源=ads_stock_fund)'
    """)


def _clamp(sql_expr):
    # DECIMAL(10,4) 上界为 999999.9999，数据损坏行会产生极端值，统一截断到 ±99999
    return f"LEAST(GREATEST({sql_expr}, -99999), 99999)"


INSERT_STOCK_ANNUAL = """
INSERT INTO ads_stock_annual
(stock_code, report_date, operating_revenue, operating_cost, gross_profit, gross_margin,
 selling_expense, admin_expense, finance_expense, core_profit, core_margin,
 parent_net_profit, net_margin,
 total_assets, total_liabilities, total_equity, debt_ratio,
 cash, trading_fa, cash_plus_tfa, short_borrow, long_borrow, interest_debt, net_cash,
 accounts_receivable, inventory, fixed_assets, goodwill,
 op_cash_flow, net_cash_ratio, roe)
SELECT i.stock_code, i.report_date,
  i.operating_revenue, i.operating_cost,
  ROUND(i.operating_revenue - i.operating_cost, 2),
  ROUND(""" + _clamp("CASE WHEN i.operating_revenue > 0 THEN (i.operating_revenue - i.operating_cost) / i.operating_revenue * 100 ELSE NULL END") + """, 2),
  i.selling_expense, i.admin_expense, i.finance_expense,
  ROUND(i.operating_revenue - COALESCE(i.operating_cost,0) - COALESCE(i.selling_expense,0) - COALESCE(i.admin_expense,0), 2),
  ROUND(""" + _clamp("CASE WHEN i.operating_revenue > 0 THEN (i.operating_revenue - COALESCE(i.operating_cost,0) - COALESCE(i.selling_expense,0) - COALESCE(i.admin_expense,0)) / i.operating_revenue * 100 ELSE NULL END") + """, 2),
  i.parent_net_profit,
  ROUND(""" + _clamp("CASE WHEN i.operating_revenue > 0 THEN i.parent_net_profit / i.operating_revenue * 100 ELSE NULL END") + """, 2),
  b.total_assets, b.total_liabilities, b.total_equity,
  ROUND(""" + _clamp("CASE WHEN b.total_assets > 0 THEN b.total_liabilities / b.total_assets * 100 ELSE NULL END") + """, 2),
  b.cash, b.trading_fa, ROUND(COALESCE(b.cash,0) + COALESCE(b.trading_fa,0), 2),
  b.short_term_borrow, b.long_term_borrow,
  ROUND(COALESCE(b.short_term_borrow,0) + COALESCE(b.long_term_borrow,0), 2),
  ROUND(COALESCE(b.cash,0) + COALESCE(b.trading_fa,0) - COALESCE(b.short_term_borrow,0) - COALESCE(b.long_term_borrow,0), 2),
  b.accounts_receivable, b.inventory, b.fixed_assets, b.goodwill,
  c.op_cash_flow,
  ROUND(""" + _clamp("CASE WHEN i.parent_net_profit IS NOT NULL AND i.parent_net_profit <> 0 THEN c.op_cash_flow / i.parent_net_profit ELSE NULL END") + """, 2),
  ROUND(""" + _clamp("CASE WHEN b.total_equity > 0 THEN i.parent_net_profit / b.total_equity * 100 ELSE NULL END") + """, 2)
FROM fin_income i
JOIN fin_balance_sheet b ON i.stock_code = b.stock_code AND i.report_date = b.report_date
LEFT JOIN fin_cash_flow c ON i.stock_code = c.stock_code AND i.report_date = c.report_date
WHERE MONTH(i.report_date) = 12 AND DAY(i.report_date) = 31
  AND COALESCE(i.operating_cost,0) >= 0
  AND COALESCE(i.selling_expense,0) >= 0
  AND COALESCE(i.admin_expense,0) >= 0
"""

UPDATE_STOCK_YOY = """
UPDATE ads_stock_annual cur
JOIN ads_stock_annual prev ON cur.stock_code = prev.stock_code
  AND prev.report_date = DATE_SUB(cur.report_date, INTERVAL 1 YEAR)
SET cur.revenue_yoy = ROUND(LEAST(GREATEST((cur.operating_revenue - prev.operating_revenue) / prev.operating_revenue * 100, -99999), 99999), 2),
    cur.profit_yoy = ROUND(LEAST(GREATEST((cur.parent_net_profit - prev.parent_net_profit) / prev.parent_net_profit * 100, -99999), 99999), 2)
WHERE prev.operating_revenue IS NOT NULL AND prev.operating_revenue > 0
"""

INSERT_SECTOR_ANNUAL = """
INSERT INTO ads_sector_annual
(sector_code, category, sector_name, report_date, stock_count,
 total_revenue, total_net_profit, avg_gross_margin, avg_roe, avg_debt_ratio)
SELECT ss.sector_code, MAX(sec.category), MAX(sec.sector_name), a.report_date, COUNT(DISTINCT ss.stock_code),
  ROUND(SUM(a.operating_revenue), 2),
  ROUND(SUM(a.parent_net_profit), 2),
  ROUND(AVG(a.gross_margin), 2),
  ROUND(AVG(a.roe), 2),
  ROUND(AVG(a.debt_ratio), 2)
FROM stock_sectors ss
JOIN ads_stock_annual a ON ss.stock_code = a.stock_code
LEFT JOIN sectors sec ON ss.sector_code = sec.sector_code
GROUP BY ss.sector_code, a.report_date
"""

UPDATE_SECTOR_YOY = """
UPDATE ads_sector_annual cur
JOIN ads_sector_annual prev ON cur.sector_code = prev.sector_code
  AND prev.report_date = DATE_SUB(cur.report_date, INTERVAL 1 YEAR)
SET cur.revenue_yoy = ROUND(LEAST(GREATEST((cur.total_revenue - prev.total_revenue) / prev.total_revenue * 100, -99999), 99999), 2),
    cur.profit_yoy = ROUND(LEAST(GREATEST((cur.total_net_profit - prev.total_net_profit) / prev.total_net_profit * 100, -99999), 99999), 2)
WHERE prev.total_revenue IS NOT NULL AND prev.total_revenue > 0
"""

INSERT_SECTOR_LATEST = """
INSERT INTO ads_sector_latest
(sector_code, category, sector_name, report_date, stock_count,
 total_market_cap, total_revenue, total_net_profit,
 revenue_yoy, profit_yoy, avg_gross_margin, avg_roe, avg_debt_ratio)
SELECT ss.sector_code, MAX(sec.category), MAX(sec.sector_name), MAX(l.annual_report_date), COUNT(DISTINCT l.stock_code),
  ROUND(SUM(l.market_cap), 2),
  ROUND(SUM(l.revenue_annual), 2),
  ROUND(SUM(l.profit_annual), 2),
  MAX(a.revenue_yoy), MAX(a.profit_yoy),
  ROUND(AVG(l.gross_margin), 2),
  ROUND(AVG(l.roe), 2),
  ROUND(AVG(l.debt_ratio), 2)
FROM ads_stock_latest l
JOIN stock_sectors ss ON l.stock_code = ss.stock_code
LEFT JOIN sectors sec ON ss.sector_code = sec.sector_code
LEFT JOIN ads_sector_annual a ON a.sector_code = ss.sector_code
  AND a.report_date = (SELECT MAX(report_date) FROM ads_sector_annual WHERE sector_code = ss.sector_code)
GROUP BY ss.sector_code
"""

# 报告期常量：22个季度（2021Q1-2026Q2）
FUND_ENDS = ['20210331','20210630','20210930','20211231','20220331','20220630',
             '20220930','20221231','20230331','20230630','20230930','20231231',
             '20240331','20240630','20240930','20241231','20250331','20250630',
             '20250930','20251231','20260331','20260630']
FUND_LABELS = ['21Q1','21Q2','21Q3','21Q4','22Q1','22Q2','22Q3','22Q4',
               '23Q1','23Q2','23Q3','23Q4','24Q1','24Q2','24Q3','24Q4',
               '25Q1','25Q2','25Q3','25Q4','26Q1','26Q2']

INSERT_STOCK_FUND = """
INSERT INTO ads_stock_fund
(stock_code, end_date, quarter, report_type, fund_count, active_count,
 passive_count, total_amount, total_mkv)
SELECT
  SUBSTRING_INDEX(d.symbol, '.', 1) AS stock_code,
  d.end_date,
  CONCAT(SUBSTRING(d.end_date, 3, 2), 'Q',
         CEIL(SUBSTRING(d.end_date, 5, 2) / 3)),
  CASE WHEN RIGHT(d.end_date, 4) IN ('0331','0930') THEN 'Q' ELSE 'F' END,
  COUNT(*),
  SUM(CASE WHEN COALESCE(f.passive, 0) = 0 THEN 1 ELSE 0 END),
  SUM(COALESCE(f.passive, 0)),
  ROUND(SUM(d.amount), 2),
  ROUND(SUM(d.mkv), 2)
FROM (
  SELECT ts_code, symbol, end_date, amount, mkv,
         ROW_NUMBER() OVER (PARTITION BY ts_code, symbol, end_date
                            ORDER BY ann_date DESC) rn
  FROM fund_portfolio
  WHERE end_date = %(end_date)s
) d
LEFT JOIN (
  SELECT ts_code,
         CASE WHEN name LIKE '%%ETF%%' OR name LIKE '%%指数%%' OR name LIKE '%%沪深300%%'
              OR name LIKE '%%上证50%%' OR name LIKE '%%中证500%%' OR name LIKE '%%MSCI%%'
              OR name LIKE '%%增强%%' OR name LIKE '%%联接%%' OR name LIKE '%%LOF%%'
              OR name LIKE '%%300%%' THEN 1 ELSE 0 END AS passive
  FROM fund_basic
) f ON f.ts_code = d.ts_code
WHERE d.rn = 1
GROUP BY SUBSTRING_INDEX(d.symbol, '.', 1), d.end_date
"""


def _quarter_label(end_date):
    """20210331 -> 21Q1"""
    yy = end_date[2:4]
    m = int(end_date[4:6])
    q = (m - 1) // 3 + 1
    return f'{yy}Q{q}'


def compute_stock_fund(conn, cur, log):
    """Step5: 计算 ads_stock_fund（基金持仓聚合+去重+股价回填）。每季度提交一次。"""
    cur.execute("SELECT stock_code, total_shares FROM stock_shares_dfcf")
    shares_map = {r['stock_code']: int(r['total_shares']) if r['total_shares'] else 0
                  for r in cur.fetchall()}
    total_rows = 0
    for i, end in enumerate(FUND_ENDS):
        cur.execute(INSERT_STOCK_FUND, {'end_date': end})
        cur.execute("SELECT DISTINCT stock_code FROM ads_stock_fund WHERE end_date=%s", (end,))
        codes = [r['stock_code'] for r in cur.fetchall()]
        if not codes:
            continue
        placeholders = ','.join(['%s'] * len(codes))
        prev_end = FUND_ENDS[i - 1] if i > 0 else '20201231'
        cur.execute(f"""
            SELECT k.stock_code, k.close_price
            FROM daily_kline k
            JOIN (
              SELECT stock_code, MAX(trade_date) md FROM daily_kline
              WHERE stock_code IN ({placeholders}) AND trade_date <= %s
              GROUP BY stock_code
            ) m ON k.stock_code = m.stock_code AND k.trade_date = m.md
        """, codes + [end])
        close_map = {r['stock_code']: float(r['close_price']) for r in cur.fetchall()}
        cur.execute(f"""
            SELECT stock_code, MAX(high_price) hi FROM daily_kline
            WHERE stock_code IN ({placeholders})
              AND trade_date > %s AND trade_date <= %s
            GROUP BY stock_code
        """, codes + [prev_end, end])
        intra_map = {r['stock_code']: float(r['hi']) for r in cur.fetchall()}
        updates = [
            (shares_map.get(c), close_map.get(c), intra_map.get(c), c, end)
            for c in codes
        ]
        cur.executemany("""
            UPDATE ads_stock_fund SET total_shares=%s, close_price=%s, intra_high=%s
            WHERE stock_code=%s AND end_date=%s
        """, updates)
        conn.commit()
        total_rows += len(codes)
        log(f'  fund {_quarter_label(end)} ({end}): {len(codes)} stocks')
    return total_rows


# 完整披露季度(Q2/Q4)增量列：列名 = 区间终点季度
TREND_D_COLS = ['d21Q4', 'd22Q2', 'd22Q4', 'd23Q2', 'd23Q4',
                'd24Q2', 'd24Q4', 'd25Q2', 'd25Q4', 'd26Q2']
# 各完整披露季度持仓基金家数列：列名 = 季度标签
TREND_FC_COLS = ['fc21Q2', 'fc21Q4', 'fc22Q2', 'fc22Q4', 'fc23Q2',
                 'fc23Q4', 'fc24Q2', 'fc24Q4', 'fc25Q2', 'fc25Q4', 'fc26Q2']
# 完整披露季度(全局固定报告期，与 FC_COLS 一一对应，缺失即按 0 家处理)
TREND_FC_QUARTERS = ['21Q2', '21Q4', '22Q2', '22Q4', '23Q2',
                     '23Q4', '24Q2', '24Q4', '25Q2', '25Q4', '26Q2']


def _max_consec(deltas, target):
    best = 0
    cur_run = 0
    for _, v in deltas:
        if v == target:
            cur_run += 1
            best = max(best, cur_run)
        else:
            cur_run = 0
    return best


def compute_stock_fund_trend(conn, cur, log):
    """Step6: 计算 ads_stock_fund_trend（每股一行，季度增减±1列 + 派生统计）。"""
    cur.execute("""
        SELECT stock_code, end_date, quarter, fund_count, total_amount
        FROM ads_stock_fund WHERE report_type='F'
        ORDER BY stock_code, end_date
    """)
    groups = {}
    for r in cur.fetchall():
        groups.setdefault(r['stock_code'], []).append(r)

    rows_out = []
    for code, pts in groups.items():
        fc_map = {r['quarter']: (float(r['fund_count'] or 0), float(r['total_amount'] or 0)) for r in pts}
        aligned = [(q, *(fc_map.get(q, (0.0, 0.0)))) for q in TREND_FC_QUARTERS]

        deltas = []
        for i in range(1, len(aligned)):
            prev_fc, prev_amt = aligned[i - 1][1], aligned[i - 1][2]
            cur_fc, cur_amt = aligned[i][1], aligned[i][2]
            diff = cur_amt - prev_amt
            deltas.append(('d' + aligned[i][0], 1 if diff >= 0 else -1))
        delta_map = dict(deltas)
        d_vals = [delta_map.get(c) for c in TREND_D_COLS]
        fc_vals = [round(v[1]) for v in aligned]

        recent8 = deltas[-8:]
        recent8_up = sum(1 for _, v in recent8 if v == 1)
        recent8_net = 2 * recent8_up - len(recent8)
        recent6_up = sum(1 for _, v in deltas[-6:] if v == 1)
        recent4_up = sum(1 for _, v in deltas[-4:] if v == 1)
        max_cg = _max_consec(deltas, 1)
        max_cd = _max_consec(deltas, -1)

        recent_pts = aligned[-8:]
        recent1q_count = round(aligned[-1][1])
        prev1q_count = round(aligned[-2][1])
        r1q_growth = round((recent1q_count - prev1q_count) / prev1q_count * 100, 2) if prev1q_count > 0 else None
        recent2q_count = round(sum(v[1] for v in recent_pts[-2:]) / 2)
        recent4q_count = round(sum(v[1] for v in recent_pts[-4:]) / 4)
        recent8q_amt = sum(v[2] for v in recent_pts) / len(recent_pts) if recent_pts else 0
        prev2q_count = round(sum(v[1] for v in recent_pts[-4:-2]) / 2) if len(recent_pts) >= 4 else 0
        growth = round((recent2q_count - prev2q_count) / prev2q_count * 100, 2) if prev2q_count > 0 else None

        rows_out.append((code, *d_vals, *fc_vals, recent8_up, recent8_net, recent6_up, recent4_up,
                         max_cg, max_cd, recent2q_count, recent4q_count,
                         recent1q_count, prev1q_count, r1q_growth,
                         round(recent8q_amt, 2), prev2q_count, growth))

    if rows_out:
        placeholders = ','.join(['%s'] * (15 + len(TREND_D_COLS) + len(TREND_FC_COLS)))
        cur.executemany(f"""
            INSERT INTO ads_stock_fund_trend
            (stock_code, {','.join(TREND_D_COLS)}, {','.join(TREND_FC_COLS)},
             recent8_up, recent8_net, recent6_up,
             recent4_up, max_consec_growth, max_consec_decline,
             recent2q_fund_count, recent4q_fund_count, recent1q_fund_count,
             prev1q_fund_count, recent1q_fund_growth,
             recent8q_amount, prev2q_fund_count, recent2q_fund_growth)
            VALUES ({placeholders})
        """, rows_out)
        conn.commit()
    log(f'  fund trend rows: {len(rows_out)}')
    return len(rows_out)


def _latest_price_map(cur):
    cur.execute("""
        SELECT k.stock_code, k.close_price
        FROM daily_kline k
        JOIN (SELECT stock_code, MAX(trade_date) md FROM daily_kline WHERE close_price>0 GROUP BY stock_code) m
          ON k.stock_code=m.stock_code AND k.trade_date=m.md
    """)
    return {r['stock_code']: float(r['close_price']) for r in cur.fetchall()}


def _shares_map(cur):
    cur.execute("SELECT stock_code, total_shares FROM stock_shares_dfcf")
    return {r['stock_code']: int(r['total_shares']) if r['total_shares'] else 0 for r in cur.fetchall()}


def _name_map(cur):
    cur.execute("SELECT stock_code, stock_name FROM stocks")
    return {r['stock_code']: r['stock_name'] for r in cur.fetchall()}


def _latest_dividend_map(cur):
    cur.execute("""
        SELECT d.stock_code, d.cash_per_10, d.dividend_yield
        FROM stock_dividend d
        JOIN (SELECT stock_code, MAX(report_date) rd FROM stock_dividend
              WHERE assign_progress = '实施分配' GROUP BY stock_code) m
          ON d.stock_code = m.stock_code AND d.report_date = m.rd
    """)
    out = {}
    for r in cur.fetchall():
        cash10 = float(r['cash_per_10']) if r['cash_per_10'] else 0.0
        dy = float(r['dividend_yield']) if r['dividend_yield'] else None
        out[r['stock_code']] = (cash10, dy)
    return out


def _ttm_map(cur):
    """TTM归母净利：最新报告期累计 + 上年年报 - 上年同期累计"""
    cur.execute("""
        SELECT fi.stock_code, fi.report_date, fi.parent_net_profit
        FROM fin_income fi
        JOIN (SELECT stock_code, MAX(report_date) rd FROM fin_income GROUP BY stock_code) m
          ON fi.stock_code = m.stock_code AND fi.report_date = m.rd
    """)
    latest = {}
    for r in cur.fetchall():
        latest[r['stock_code']] = (r['report_date'],
                                   float(r['parent_net_profit']) if r['parent_net_profit'] else 0.0)
    cur.execute("""
        SELECT stock_code, report_date, parent_net_profit FROM fin_income
        WHERE (MONTH(report_date) = 12 AND DAY(report_date) = 31)
    """)
    year_end = {}
    for r in cur.fetchall():
        year_end[r['stock_code']] = float(r['parent_net_profit']) if r['parent_net_profit'] else 0.0
    ttm = {}
    for code, (rd, pnp) in latest.items():
        if rd.month == 12 and rd.day == 31:
            ttm[code] = pnp
            continue
        prev_date = date(rd.year - 1, rd.month, rd.day)
        cur.execute("SELECT parent_net_profit FROM fin_income WHERE stock_code=%s AND report_date=%s",
                    (code, prev_date))
        prow = cur.fetchone()
        same = float(prow['parent_net_profit']) if prow and prow['parent_net_profit'] else 0.0
        ttm[code] = pnp + year_end.get(code, 0.0) - same
    return ttm


def compute(progress_cb=None):
    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    cur = conn.cursor()
    t0 = time.time()

    def log(msg):
        if progress_cb:
            progress_cb(msg)
        else:
            print(msg, flush=True)

    log('Dropping old ads tables...')
    for t in ['ads_stock_annual', 'ads_stock_latest', 'ads_sector_annual',
              'ads_sector_latest', 'ads_stock_fund', 'ads_stock_fund_trend']:
        _drop_table(cur, t)
    create_tables(cur)
    conn.commit()

    log('Step 1/6: ads_stock_annual (个股年度财务)...')
    cur.execute(INSERT_STOCK_ANNUAL)
    conn.commit()
    cur.execute("SELECT COUNT(*) c FROM ads_stock_annual")
    n_annual = cur.fetchone()['c']
    log(f'  annual rows: {n_annual}')

    log('  computing stock YoY...')
    cur.execute(UPDATE_STOCK_YOY)
    conn.commit()

    log('Step 2/6: ads_sector_annual (行业年度汇总)...')
    cur.execute(INSERT_SECTOR_ANNUAL)
    conn.commit()
    cur.execute("SELECT COUNT(*) c FROM ads_sector_annual")
    n_sec_annual = cur.fetchone()['c']
    log(f'  sector annual rows: {n_sec_annual}')
    cur.execute(UPDATE_SECTOR_YOY)
    conn.commit()

    log('Step 3/6: ads_stock_latest (个股最新快照)...')
    log('  loading latest price (全表扫描 ~30s)...')
    prices = _latest_price_map(cur)
    log(f'  prices: {len(prices)}')
    shares = _shares_map(cur)
    names = _name_map(cur)
    dividends = _latest_dividend_map(cur)
    ttm = _ttm_map(cur)

    cur.execute("""
        SELECT stock_code, report_date FROM (
          SELECT stock_code, report_date,
                 ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY report_date DESC) rn
          FROM fin_income
        ) t WHERE rn=1
    """)
    latest_report = {r['stock_code']: r['report_date'] for r in cur.fetchall()}

    cur.execute("SELECT * FROM ads_stock_annual ORDER BY stock_code, report_date")
    annual_by_stock = {}
    for r in cur.fetchall():
        annual_by_stock.setdefault(r['stock_code'], []).append(r)

    cur.execute("""
        SELECT fi.stock_code, fi.operating_revenue, fi.parent_net_profit, fi.report_date
        FROM fin_income fi
        JOIN (SELECT stock_code, MAX(report_date) rd FROM fin_income GROUP BY stock_code) m
          ON fi.stock_code = m.stock_code AND fi.report_date = m.rd
    """)
    fin_latest = {r['stock_code']: r for r in cur.fetchall()}

    rows_latest = []
    for code, rd in latest_report.items():
        price = prices.get(code)
        sh = shares.get(code) or 0
        mktcap = pe = None
        if price and sh:
            mktcap = round(price * sh / 1e8, 2)
            ttm_p = ttm.get(code)
            if ttm_p:
                pe = round(mktcap * 1e8 / ttm_p, 2)

        annual_rows = annual_by_stock.get(code, [])
        annual = annual_rows[-1] if annual_rows else None
        annual_date = annual['report_date'] if annual else None

        div_info = dividends.get(code)
        div_yield = div_info[1] if div_info else None
        if div_yield is None and div_info and div_info[0] and price:
            div_yield = round(div_info[0] / 10 / price * 100, 4)

        f = fin_latest.get(code)
        rev_yoy = profit_yoy = None
        if f:
            prev_date = date(rd.year - 1, rd.month, rd.day)
            cur.execute(
                "SELECT operating_revenue, parent_net_profit FROM fin_income WHERE stock_code=%s AND report_date=%s",
                (code, prev_date))
            prow = cur.fetchone()
            if prow and prow['operating_revenue'] and float(prow['operating_revenue']) > 0:
                rev_yoy = round((float(f['operating_revenue'] or 0) - float(prow['operating_revenue']))
                                / float(prow['operating_revenue']) * 100, 2)
            if prow and prow['parent_net_profit'] and abs(float(prow['parent_net_profit'])) > 0:
                profit_yoy = round((float(f['parent_net_profit'] or 0) - float(prow['parent_net_profit']))
                                   / abs(float(prow['parent_net_profit'])) * 100, 2)

        rows_latest.append((
            code, names.get(code), rd, annual_date, price,
            sh, mktcap, pe, div_yield,
            f['operating_revenue'] if f else None,
            f['parent_net_profit'] if f else None,
            rev_yoy, profit_yoy,
            annual['operating_revenue'] if annual else None,
            annual['parent_net_profit'] if annual else None,
            annual['gross_margin'] if annual else None,
            annual['core_margin'] if annual else None,
            annual['net_margin'] if annual else None,
            annual['roe'] if annual else None,
            annual['roe'] if annual else None,
            annual['debt_ratio'] if annual else None,
            annual['net_cash'] if annual else None,
            annual['net_cash_ratio'] if annual else None,
            annual['op_cash_flow'] if annual else None,
        ))
        if progress_cb and len(rows_latest) % 5000 == 0:
            log(f'  latest: {len(rows_latest)}')

    cur.executemany("""
        INSERT INTO ads_stock_latest
        (stock_code, stock_name, report_date, annual_report_date, latest_price,
         total_shares, market_cap, pe_ttm, dividend_yield,
         revenue, profit, revenue_yoy, profit_yoy,
         revenue_annual, profit_annual, gross_margin, core_margin, net_margin,
         roe, roe_ttm, debt_ratio, net_cash, net_cash_ratio, op_cash_flow)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, rows_latest)
    conn.commit()
    log(f'  ads_stock_latest rows: {len(rows_latest)}')

    log('Step 4/6: ads_sector_latest (行业最新快照)...')
    cur.execute(INSERT_SECTOR_LATEST)
    conn.commit()
    cur.execute("SELECT COUNT(*) c FROM ads_sector_latest")
    n_sec_latest = cur.fetchone()['c']
    log(f'  sector latest rows: {n_sec_latest}')

    log('Step 5/6: ads_stock_fund (基金持仓聚合)...')
    n_stock_fund = compute_stock_fund(conn, cur, log)
    log(f'  stock fund rows: {n_stock_fund}')

    log('Step 6/6: ads_stock_fund_trend (基金持仓增减序列+派生统计)...')
    n_stock_fund_trend = compute_stock_fund_trend(conn, cur, log)

    elapsed = int(time.time() - t0)
    log(f'Done in {elapsed}s')
    conn.close()
    return {
        'stock_annual': n_annual,
        'sector_annual': n_sec_annual,
        'stock_latest': len(rows_latest),
        'sector_latest': n_sec_latest,
        'stock_fund': n_stock_fund,
        'stock_fund_trend': n_stock_fund_trend,
        'elapsed_seconds': elapsed,
    }


if __name__ == '__main__':
    print(compute())
