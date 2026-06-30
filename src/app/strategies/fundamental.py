from ..database import query

FUNDAMENTAL_STRATEGIES = {
    'revenue_growth': {
        'name': '营收增长率',
        'description': '营业收入增长率 > 阈值',
        'params': {
            'threshold': {'type': 'float', 'default': 20.0, 'description': '营收增长率下限(%)'},
        },
    },
    'profit_growth': {
        'name': '净利润增长率',
        'description': '净利润增长率 > 阈值',
        'params': {
            'threshold': {'type': 'float', 'default': 20.0, 'description': '净利润增长率下限(%)'},
        },
    },
    'debt_ratio': {
        'name': '资产负债率',
        'description': '资产负债率 < 阈值',
        'params': {
            'threshold': {'type': 'float', 'default': 50.0, 'description': '资产负债率上限(%)'},
        },
    },
}


def get_latest_report_date():
    row = query("SELECT MAX(report_date) AS d FROM fin_ratios")
    return row[0]['d'] if row else None


def screen_revenue_growth(threshold=20.0):
    rdate = get_latest_report_date()
    if not rdate:
        return []
    # revenue_growth_rate stored as fraction (0.064 = 6.4%)
    th = threshold / 100.0
    sql = """
    SELECT r.stock_code, s.stock_name, r.revenue_growth_rate * 100 AS revenue_growth_rate, r.report_date
    FROM fin_ratios r
    JOIN stocks s ON s.stock_code = r.stock_code
    WHERE r.report_date = %(rdate)s
      AND r.revenue_growth_rate > %(th)s
    ORDER BY r.revenue_growth_rate DESC
    """
    return query(sql, {'rdate': rdate, 'th': th})


def screen_profit_growth(threshold=20.0):
    rdate = get_latest_report_date()
    if not rdate:
        return []
    sql = """
    SELECT r.stock_code, s.stock_name, r.net_profit_growth_rate, r.report_date
    FROM fin_ratios r
    JOIN stocks s ON s.stock_code = r.stock_code
    WHERE r.report_date = %(rdate)s
      AND r.net_profit_growth_rate > %(th)s
    ORDER BY r.net_profit_growth_rate DESC
    """
    return query(sql, {'rdate': rdate, 'th': threshold})


def screen_debt_ratio(threshold=50.0):
    rdate = get_latest_report_date()
    if not rdate:
        return []
    sql = """
    SELECT r.stock_code, s.stock_name, r.debt_ratio, r.report_date
    FROM fin_ratios r
    JOIN stocks s ON s.stock_code = r.stock_code
    WHERE r.report_date = %(rdate)s
      AND r.debt_ratio >= 0 AND r.debt_ratio < %(th)s
    ORDER BY r.debt_ratio ASC
    """
    return query(sql, {'rdate': rdate, 'th': threshold})


def screen_fundamental_all(revenue_threshold=20.0, profit_threshold=20.0, debt_threshold=50.0):
    rdate = get_latest_report_date()
    if not rdate:
        return []
    rev_th = revenue_threshold / 100.0
    sql = """
    SELECT r.stock_code, s.stock_name,
           r.revenue_growth_rate * 100 AS revenue_growth_rate,
           r.net_profit_growth_rate, r.debt_ratio,
           i.operating_revenue, i.net_profit, r.report_date
    FROM fin_ratios r
    JOIN stocks s ON s.stock_code = r.stock_code
    JOIN fin_income i ON i.stock_code = r.stock_code AND i.report_date = r.report_date
    WHERE r.report_date = %(rdate)s
      AND r.revenue_growth_rate > %(rev_th)s
      AND r.net_profit_growth_rate > %(pro_th)s
      AND r.debt_ratio >= 0 AND r.debt_ratio < %(debt_th)s
    ORDER BY r.revenue_growth_rate DESC
    """
    return query(sql, {'rdate': rdate, 'rev_th': rev_th, 'pro_th': profit_threshold, 'debt_th': debt_threshold})
