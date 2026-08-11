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
          id INT AUTO_INCREMENT PRIMARY KEY,
          stock_code VARCHAR(10) NOT NULL,
          report_date DATE NOT NULL,
          operating_revenue DECIMAL(20,2),
          operating_cost DECIMAL(20,2),
          gross_profit DECIMAL(20,2),
          gross_margin DECIMAL(10,4),
          selling_expense DECIMAL(20,2),
          admin_expense DECIMAL(20,2),
          finance_expense DECIMAL(20,2),
          core_profit DECIMAL(20,2),
          core_margin DECIMAL(10,4),
          parent_net_profit DECIMAL(20,2),
          net_margin DECIMAL(10,4),
          total_assets DECIMAL(20,2),
          total_liabilities DECIMAL(20,2),
          total_equity DECIMAL(20,2),
          debt_ratio DECIMAL(10,4),
          cash DECIMAL(20,2),
          trading_fa DECIMAL(20,2),
          cash_plus_tfa DECIMAL(20,2),
          short_borrow DECIMAL(20,2),
          long_borrow DECIMAL(20,2),
          interest_debt DECIMAL(20,2),
          net_cash DECIMAL(20,2),
          accounts_receivable DECIMAL(20,2),
          inventory DECIMAL(20,2),
          fixed_assets DECIMAL(20,2),
          goodwill DECIMAL(20,2),
          op_cash_flow DECIMAL(20,2),
          net_cash_ratio DECIMAL(10,4),
          roe DECIMAL(10,4),
          revenue_yoy DECIMAL(10,4),
          profit_yoy DECIMAL(10,4),
          UNIQUE KEY uk_stock_date (stock_code, report_date),
          KEY idx_date (report_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE ads_stock_latest (
          stock_code VARCHAR(10) NOT NULL,
          stock_name VARCHAR(50),
          report_date DATE,
          annual_report_date DATE,
          latest_price DECIMAL(10,2),
          total_shares BIGINT,
          market_cap DECIMAL(20,2),
          pe_ttm DECIMAL(10,2),
          dividend_yield DECIMAL(10,4),
          revenue DECIMAL(20,2),
          profit DECIMAL(20,2),
          revenue_yoy DECIMAL(10,4),
          profit_yoy DECIMAL(10,4),
          revenue_annual DECIMAL(20,2),
          profit_annual DECIMAL(20,2),
          gross_margin DECIMAL(10,4),
          core_margin DECIMAL(10,4),
          net_margin DECIMAL(10,4),
          roe DECIMAL(10,4),
          roe_ttm DECIMAL(10,4),
          debt_ratio DECIMAL(10,4),
          net_cash DECIMAL(20,2),
          net_cash_ratio DECIMAL(10,4),
          op_cash_flow DECIMAL(20,2),
          PRIMARY KEY (stock_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE ads_sector_annual (
          id INT AUTO_INCREMENT PRIMARY KEY,
          sector_code VARCHAR(10) NOT NULL,
          category VARCHAR(20),
          sector_name VARCHAR(50),
          report_date DATE NOT NULL,
          stock_count INT,
          total_revenue DECIMAL(20,2),
          total_net_profit DECIMAL(20,2),
          avg_gross_margin DECIMAL(10,4),
          avg_roe DECIMAL(10,4),
          avg_debt_ratio DECIMAL(10,4),
          revenue_yoy DECIMAL(10,4),
          profit_yoy DECIMAL(10,4),
          UNIQUE KEY uk_sector_date (sector_code, report_date),
          KEY idx_date (report_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE ads_sector_latest (
          sector_code VARCHAR(10) NOT NULL,
          category VARCHAR(20),
          sector_name VARCHAR(50),
          report_date DATE,
          stock_count INT,
          total_market_cap DECIMAL(20,2),
          total_revenue DECIMAL(20,2),
          total_net_profit DECIMAL(20,2),
          revenue_yoy DECIMAL(10,4),
          profit_yoy DECIMAL(10,4),
          avg_gross_margin DECIMAL(10,4),
          avg_roe DECIMAL(10,4),
          avg_debt_ratio DECIMAL(10,4),
          PRIMARY KEY (sector_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ads_refresh_log (
          id INT AUTO_INCREMENT PRIMARY KEY,
          status VARCHAR(20) NOT NULL,
          total_stocks INT,
          computed_stocks INT,
          error_stocks INT,
          started_at DATETIME,
          finished_at DATETIME,
          message VARCHAR(500)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
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
    for t in ['ads_stock_annual', 'ads_stock_latest', 'ads_sector_annual', 'ads_sector_latest']:
        _drop_table(cur, t)
    create_tables(cur)
    conn.commit()

    log('Step 1/4: ads_stock_annual (个股年度财务)...')
    cur.execute(INSERT_STOCK_ANNUAL)
    conn.commit()
    cur.execute("SELECT COUNT(*) c FROM ads_stock_annual")
    n_annual = cur.fetchone()['c']
    log(f'  annual rows: {n_annual}')

    log('  computing stock YoY...')
    cur.execute(UPDATE_STOCK_YOY)
    conn.commit()

    log('Step 2/4: ads_sector_annual (行业年度汇总)...')
    cur.execute(INSERT_SECTOR_ANNUAL)
    conn.commit()
    cur.execute("SELECT COUNT(*) c FROM ads_sector_annual")
    n_sec_annual = cur.fetchone()['c']
    log(f'  sector annual rows: {n_sec_annual}')
    cur.execute(UPDATE_SECTOR_YOY)
    conn.commit()

    log('Step 3/4: ads_stock_latest (个股最新快照)...')
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

    log('Step 4/4: ads_sector_latest (行业最新快照)...')
    cur.execute(INSERT_SECTOR_LATEST)
    conn.commit()
    cur.execute("SELECT COUNT(*) c FROM ads_sector_latest")
    n_sec_latest = cur.fetchone()['c']
    log(f'  sector latest rows: {n_sec_latest}')

    elapsed = int(time.time() - t0)
    log(f'Done in {elapsed}s')
    conn.close()
    return {
        'stock_annual': n_annual,
        'sector_annual': n_sec_annual,
        'stock_latest': len(rows_latest),
        'sector_latest': n_sec_latest,
        'elapsed_seconds': elapsed,
    }


if __name__ == '__main__':
    print(compute())
