from ..database import query

FUNDAMENTAL_STRATEGIES = {
    'revenue_growth': {
        'name': '营收增长率',
        'description': '营业收入增长率 > 阈值（从 fin_income 计算 YoY）',
        'params': {
            'threshold': {'type': 'float', 'default': 20.0, 'description': '营收增长率下限(%)'},
        },
    },
    'profit_growth': {
        'name': '净利润增长率',
        'description': '净利润增长率 > 阈值（从 fin_income 计算 YoY）',
        'params': {
            'threshold': {'type': 'float', 'default': 20.0, 'description': '净利润增长率下限(%)'},
        },
    },
    'debt_ratio': {
        'name': '资产负债率',
        'description': '资产负债率 < 阈值（从 fin_balance_sheet 计算）',
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
    sql = """
    SELECT sub.stock_code, sub.stock_name, sub.revenue_growth_rate, sub.report_date
    FROM (
        SELECT r.stock_code, s.stock_name,
               (i.operating_revenue - i2.operating_revenue) / i2.operating_revenue * 100 AS revenue_growth_rate,
               r.report_date
        FROM fin_ratios r
        JOIN stocks s ON s.stock_code = r.stock_code
        JOIN fin_income i ON i.stock_code = r.stock_code AND i.report_date = r.report_date
        JOIN fin_income i2 ON i2.stock_code = r.stock_code
            AND i2.report_date = DATE_SUB(r.report_date, INTERVAL 1 YEAR)
        WHERE r.report_date = %(rdate)s
          AND i2.operating_revenue IS NOT NULL AND i2.operating_revenue > 0
    ) sub
    WHERE sub.revenue_growth_rate > %(th)s
    ORDER BY sub.revenue_growth_rate DESC
    """
    return query(sql, {'rdate': rdate, 'th': threshold})


def screen_profit_growth(threshold=20.0):
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


def screen_debt_ratio(threshold=50.0):
    rdate = get_latest_report_date()
    if not rdate:
        return []
    sql = """
    SELECT r.stock_code, s.stock_name,
           b.total_liabilities / b.total_assets * 100 AS debt_ratio,
           r.report_date
    FROM fin_ratios r
    JOIN stocks s ON s.stock_code = r.stock_code
    JOIN fin_balance_sheet b ON b.stock_code = r.stock_code AND b.report_date = r.report_date
    WHERE r.report_date = %(rdate)s
      AND b.total_assets IS NOT NULL AND b.total_assets > 0
      AND b.total_liabilities / b.total_assets * 100 >= 0
      AND b.total_liabilities / b.total_assets * 100 < %(th)s
    ORDER BY debt_ratio ASC
    """
    return query(sql, {'rdate': rdate, 'th': threshold})


def screen_fundamental_all(revenue_threshold=20.0, profit_threshold=20.0, debt_threshold=50.0):
    rdate = get_latest_report_date()
    if not rdate:
        return []
    sql = """
    SELECT sub.stock_code, sub.stock_name,
           sub.revenue_growth_rate, sub.net_profit_growth_rate,
           sub.debt_ratio, sub.operating_revenue, sub.net_profit,
           sub.report_date
    FROM (
        SELECT r.stock_code, s.stock_name,
               (i.operating_revenue - i2.operating_revenue) / i2.operating_revenue * 100 AS revenue_growth_rate,
               (i.net_profit - i2.net_profit) / i2.net_profit * 100 AS net_profit_growth_rate,
               b.total_liabilities / b.total_assets * 100 AS debt_ratio,
               i.operating_revenue, i.net_profit,
               r.report_date
        FROM fin_ratios r
        JOIN stocks s ON s.stock_code = r.stock_code
        JOIN fin_income i ON i.stock_code = r.stock_code AND i.report_date = r.report_date
        JOIN fin_income i2 ON i2.stock_code = r.stock_code
            AND i2.report_date = DATE_SUB(r.report_date, INTERVAL 1 YEAR)
        JOIN fin_balance_sheet b ON b.stock_code = r.stock_code AND b.report_date = r.report_date
        WHERE r.report_date = %(rdate)s
          AND i2.operating_revenue IS NOT NULL AND i2.operating_revenue > 0
          AND i2.net_profit IS NOT NULL AND i2.net_profit > 0
          AND b.total_assets IS NOT NULL AND b.total_assets > 0
    ) sub
    WHERE sub.revenue_growth_rate > %(rev_th)s
      AND sub.net_profit_growth_rate > %(pro_th)s
      AND sub.debt_ratio >= 0 AND sub.debt_ratio < %(debt_th)s
    ORDER BY sub.revenue_growth_rate DESC
    """
    return query(sql, {
        'rdate': rdate, 'rev_th': revenue_threshold,
        'pro_th': profit_threshold, 'debt_th': debt_threshold,
    })
