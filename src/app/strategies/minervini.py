from ..database import query

MINERVINI_STRATEGIES = {
    'sepa_master': {
        'name': 'Minervini SEPA 全能选股',
        'description': 'Mark Minervini SEPA方法论：EPS增长>25% + 营收增长>25% + ROE>17% + 价格在50日均线上方 + 近期价格紧凑 + 放量确认',
        'params': {
            'eps_threshold': {'type': 'float', 'default': 25.0, 'description': '净利润增长率下限(%)'},
            'rev_threshold': {'type': 'float', 'default': 25.0, 'description': '营收增长率下限(%)'},
            'roe_threshold': {'type': 'float', 'default': 17.0, 'description': 'ROE下限(%)'},
            'tightness_days': {'type': 'int', 'default': 20, 'description': '价格紧凑观察期(天)'},
            'volume_surge': {'type': 'float', 'default': 1.5, 'description': '放量倍数(相对50日均量)'},
        },
    },
    'minervini_eps':
        {
            'name': 'Minervini EPS增长',
            'description': 'EPS(净利润)增长率 > 阈值，从 fin_income 计算 YoY',
            'params': {
                'threshold': {'type': 'float', 'default': 25.0, 'description': '净利润增长率下限(%)'},
            },
        },
    'minervini_roe':
        {
            'name': 'Minervini ROE筛选',
            'description': 'ROE(净资产收益率) > 阈值，从 fin_income+fin_balance_sheet 计算',
            'params': {
                'threshold': {'type': 'float', 'default': 17.0, 'description': 'ROE下限(%)'},
            },
        },
    'minervini_trend_template':
        {
            'name': 'Minervini 趋势模板',
            'description': '价格在MA50/MA150上方，价格逼近52周高点(>75%)，近期量价紧凑',
            'params': {
                'near_high_pct': {'type': 'float', 'default': 75.0, 'description': '距52周最高价的百分比阈值(%)'},
                'tightness_days': {'type': 'int', 'default': 20, 'description': '紧凑度观察期(天)'},
            },
        },
}

def get_latest_report_date():
    row = query("SELECT MAX(report_date) AS d FROM fin_ratios")
    return row[0]['d'] if row else None

def get_latest_trade_date():
    row = query("SELECT MAX(trade_date) AS d FROM daily_kline")
    return row[0]['d'] if row else None

def screen_minervini_eps(threshold=25.0):
    rdate = get_latest_report_date()
    if not rdate:
        return []
    sql = """
    SELECT sub.stock_code, sub.stock_name, sub.net_profit_growth_rate, sub.report_date
    FROM (
        SELECT r.stock_code, s.stock_name,
               (i.net_profit - i2.net_profit) / i2.net_profit * 100 AS net_profit_growth_rate,
               r.report_date
        FROM fin_ratios r
        JOIN stocks s ON s.stock_code = r.stock_code
        JOIN fin_income i ON i.stock_code = r.stock_code AND i.report_date = r.report_date
        JOIN fin_income i2 ON i2.stock_code = r.stock_code
            AND i2.report_date = DATE_SUB(r.report_date, INTERVAL 1 YEAR)
        WHERE r.report_date = %(rdate)s
          AND i2.net_profit IS NOT NULL AND i2.net_profit > 0
    ) sub
    WHERE sub.net_profit_growth_rate > %(th)s
    ORDER BY sub.net_profit_growth_rate DESC
    """
    return query(sql, {'rdate': rdate, 'th': threshold})

def screen_minervini_roe(threshold=17.0):
    rdate = get_latest_report_date()
    if not rdate:
        return []
    sql = """
    SELECT sub.stock_code, sub.stock_name, sub.roe, sub.report_date
    FROM (
        SELECT r.stock_code, s.stock_name,
               i.net_profit / b.total_equity * 100 AS roe,
               r.report_date
        FROM fin_ratios r
        JOIN stocks s ON s.stock_code = r.stock_code
        JOIN fin_income i ON i.stock_code = r.stock_code AND i.report_date = r.report_date
        JOIN fin_balance_sheet b ON b.stock_code = r.stock_code AND b.report_date = r.report_date
        WHERE r.report_date = %(rdate)s
          AND b.total_equity IS NOT NULL AND b.total_equity > 0
          AND i.net_profit IS NOT NULL
    ) sub
    WHERE sub.roe > %(th)s
    ORDER BY sub.roe DESC
    """
    return query(sql, {'rdate': rdate, 'th': threshold})

def screen_minervini_trend_template(near_high_pct=75.0, tightness_days=20):
    tdate = get_latest_trade_date()
    if not tdate:
        return []

    rows = query("""
    SELECT sub.stock_code, sub.stock_name, sub.latest_price,
           ROUND(sub.ma50, 2) AS ma50, ROUND(sub.ma150, 2) AS ma150,
           ROUND(sub.pct_52w_high, 1) AS pct_52w_high,
           sub.latest_date
    FROM (
        SELECT d.stock_code, s.stock_name, d.close_price AS latest_price, d.trade_date AS latest_date,
               AVG(d.close_price) OVER (PARTITION BY d.stock_code ORDER BY d.trade_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS ma50,
               AVG(d.close_price) OVER (PARTITION BY d.stock_code ORDER BY d.trade_date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS ma150,
               d.close_price / h.max_52w * 100 AS pct_52w_high,
               ROW_NUMBER() OVER (PARTITION BY d.stock_code ORDER BY d.trade_date DESC) AS rn
        FROM daily_kline d
        JOIN stocks s ON s.stock_code = d.stock_code
        JOIN (
            SELECT stock_code, MAX(close_price) AS max_52w
            FROM daily_kline
            WHERE trade_date >= DATE_SUB(%s, INTERVAL 260 DAY)
              AND trade_date <= %s
            GROUP BY stock_code
        ) h ON h.stock_code = d.stock_code
        WHERE d.trade_date >= DATE_SUB(%s, INTERVAL 200 DAY)
          AND d.trade_date <= %s
    ) sub
    WHERE sub.rn = 1
      AND sub.ma50 IS NOT NULL AND sub.ma150 IS NOT NULL
      AND sub.latest_price > sub.ma50 AND sub.latest_price > sub.ma150
      AND sub.pct_52w_high >= %s
    ORDER BY sub.pct_52w_high DESC
    """, [tdate, tdate, tdate, tdate, near_high_pct])

    if not rows:
        return []

    codes = [r['stock_code'] for r in rows]
    ph = ','.join(['%s'] * len(codes))

    tech_rows = query(f"""
    SELECT sub.stock_code,
           ROUND(sub.tightness, 3) AS tightness,
           ROUND(sub.volume_ratio, 2) AS volume_ratio
    FROM (
        SELECT t.stock_code,
               STDDEV(t.close_price) OVER (PARTITION BY t.stock_code ORDER BY t.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
               / NULLIF(AVG(t.close_price) OVER (PARTITION BY t.stock_code ORDER BY t.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 0) * 100 AS tightness,
               t.volume / NULLIF(AVG(t.volume) OVER (PARTITION BY t.stock_code ORDER BY t.trade_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW), 0) AS volume_ratio,
               ROW_NUMBER() OVER (PARTITION BY t.stock_code ORDER BY t.trade_date DESC) AS rn
        FROM daily_kline t
        WHERE t.stock_code IN ({ph})
          AND t.trade_date >= DATE_SUB(%s, INTERVAL 200 DAY)
    ) sub
    WHERE sub.rn = 1
    """, codes + [tdate])

    tech_map = {r['stock_code']: r for r in (tech_rows or [])}
    return [{**r, **tech_map.get(r['stock_code'], {})} for r in rows]

def screen_sepa_master(eps_threshold=25.0, rev_threshold=25.0, roe_threshold=17.0, tightness_days=20, volume_surge=1.5):
    rdate = get_latest_report_date()
    tdate = get_latest_trade_date()
    if not rdate or not tdate:
        return []

    fund_rows = query("""
    SELECT f.stock_code, s.stock_name,
           ROUND((i.operating_revenue - i2.operating_revenue) / i2.operating_revenue * 100, 2) AS revenue_growth_rate,
           ROUND((i.net_profit - i2.net_profit) / i2.net_profit * 100, 2) AS net_profit_growth_rate,
           ROUND(i.net_profit / b.total_equity * 100, 2) AS roe,
           ROUND(b.total_liabilities / b.total_assets * 100, 2) AS debt_ratio,
           f.report_date
    FROM fin_ratios f
    JOIN stocks s ON s.stock_code = f.stock_code
    JOIN fin_income i ON i.stock_code = f.stock_code AND i.report_date = f.report_date
    JOIN fin_income i2 ON i2.stock_code = f.stock_code
        AND i2.report_date = DATE_SUB(f.report_date, INTERVAL 1 YEAR)
    JOIN fin_balance_sheet b ON b.stock_code = f.stock_code AND b.report_date = f.report_date
    WHERE f.report_date = %(rdate)s
      AND i2.operating_revenue IS NOT NULL AND i2.operating_revenue > 0
      AND i2.net_profit IS NOT NULL AND i2.net_profit > 0
      AND b.total_equity IS NOT NULL AND b.total_equity > 0
      AND b.total_assets IS NOT NULL AND b.total_assets > 0
      AND (i.operating_revenue - i2.operating_revenue) / i2.operating_revenue * 100 > %(rev_th)s
      AND (i.net_profit - i2.net_profit) / i2.net_profit * 100 > %(eps_th)s
      AND i.net_profit / b.total_equity * 100 > %(roe_th)s
    """, {'rdate': rdate, 'rev_th': rev_threshold, 'eps_th': eps_threshold, 'roe_th': roe_threshold})
    if not fund_rows:
        return []

    codes = [r['stock_code'] for r in fund_rows]
    code_placeholders = ','.join(['%s'] * len(codes))

    tech_rows = query(f"""
    SELECT tm.stock_code,
           tm.close_price AS latest_price,
           ROUND(tm.close_price / NULLIF(h.max_52w, 0) * 100, 1) AS pct_52w_high,
           ROUND(tm.ma50, 2) AS ma50,
           ROUND(tm.ma150, 2) AS ma150,
           ROUND(tm.tightness, 3) AS tightness,
           ROUND(tm.volume / NULLIF(tm.avg_vol_50, 0), 2) AS volume_ratio,
           tm.trade_date AS latest_date
    FROM (
        SELECT t.stock_code, t.trade_date, t.close_price, t.volume,
               AVG(t.close_price) OVER (PARTITION BY t.stock_code ORDER BY t.trade_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS ma50,
               AVG(t.close_price) OVER (PARTITION BY t.stock_code ORDER BY t.trade_date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS ma150,
               STDDEV(t.close_price) OVER (PARTITION BY t.stock_code ORDER BY t.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
               / NULLIF(AVG(t.close_price) OVER (PARTITION BY t.stock_code ORDER BY t.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 0) * 100 AS tightness,
               AVG(t.volume) OVER (PARTITION BY t.stock_code ORDER BY t.trade_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS avg_vol_50,
               ROW_NUMBER() OVER (PARTITION BY t.stock_code ORDER BY t.trade_date DESC) AS rn
        FROM daily_kline t
        WHERE t.stock_code IN ({code_placeholders})
          AND t.trade_date >= DATE_SUB(%s, INTERVAL 260 DAY)
    ) tm
    JOIN (
        SELECT stock_code, MAX(close_price) AS max_52w
        FROM daily_kline
        WHERE stock_code IN ({code_placeholders})
          AND trade_date >= DATE_SUB(%s, INTERVAL 260 DAY)
          AND trade_date <= %s
        GROUP BY stock_code
    ) h ON h.stock_code = tm.stock_code
    WHERE tm.rn = 1
      AND tm.ma50 IS NOT NULL AND tm.ma150 IS NOT NULL
      AND tm.close_price > tm.ma50 AND tm.close_price > tm.ma150
    """, codes + [tdate] + codes + [tdate, tdate])

    if not tech_rows:
        return []

    tech_map = {r['stock_code']: r for r in tech_rows}
    rows = []
    for fr in fund_rows:
        sc = fr['stock_code']
        tr = tech_map.get(sc)
        if not tr:
            continue
        rows.append({**fr, **tr})

    return rows
    return query(sql, {
        'rdate': rdate,
        'tdate': tdate,
        'td': tightness_days,
        'eps_th': eps_threshold,
        'rev_th': rev_threshold,
        'roe_th': roe_threshold,
    })
