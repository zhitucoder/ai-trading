from ..database import query

TURNAROUND_STRATEGIES = {
    'turnaround': {
        'name': '困境反转',
        'description': '营收从下滑转为增长(prev_rev_growth<-10% → cur_rev_growth>15%) 或 亏损转盈利, 且股价偏离MA200不超过20%',
        'params': {
            'max_ma200_deviation': {'type': 'float', 'default': 20.0, 'description': '股价偏离200日均线的最大百分比(%)'},
            'min_rev_growth': {'type': 'float', 'default': 15.0, 'description': '当前营收增长率下限(%)'},
            'min_prev_decline': {'type': 'float', 'default': -10.0, 'description': '前期营收增长率上限(低于此值视为下滑)'},
            'min_profit': {'type': 'float', 'default': 10.0, 'description': '净利润下限(百万元)'},
        },
    },
}

REPORT_DATE = None


def get_latest_report_date():
    global REPORT_DATE
    if REPORT_DATE is None:
        row = query("SELECT MAX(report_date) AS d FROM fin_ratios")
        REPORT_DATE = row[0]['d'] if row else None
    return REPORT_DATE


def screen_turnaround(max_ma200_deviation=None, min_rev_growth=None,
                      min_prev_decline=None, min_profit=None):
    rdate = get_latest_report_date()
    if not rdate:
        return []
    if max_ma200_deviation is None:
        max_ma200_deviation = 20.0
    if min_rev_growth is None:
        min_rev_growth = 15.0
    if min_prev_decline is None:
        min_prev_decline = -10.0
    if min_profit is None:
        min_profit = 10_000_000

    return query("""
        SELECT sub2.stock_code, sub2.stock_name,
               sub2.cur_rev_growth, sub2.prev_rev_growth,
               sub2.cur_profit_growth, sub2.cur_profit, sub2.prev_profit,
               sub2.operating_revenue, sub2.close_price,
               ROUND(sub2.ma200, 2) AS ma200,
               ROUND(sub2.ma200_deviation, 2) AS ma200_deviation_pct,
               sub2.report_date
        FROM (
            SELECT fin.*, s.stock_name,
                   ma.close_price, ma.ma200, ma.ma200_deviation
            FROM (
                SELECT i_cur.stock_code,
                       ROUND((i_cur.operating_revenue - i_prev.operating_revenue)
                             / i_prev.operating_revenue * 100, 2) AS cur_rev_growth,
                       ROUND((i_prev.operating_revenue - i_prev2.operating_revenue)
                             / i_prev2.operating_revenue * 100, 2) AS prev_rev_growth,
                       ROUND((i_cur.net_profit - i_prev.net_profit)
                             / NULLIF(i_prev.net_profit, 0) * 100, 2) AS cur_profit_growth,
                       i_cur.net_profit AS cur_profit,
                       i_prev.net_profit AS prev_profit,
                       i_cur.operating_revenue,
                       i_cur.report_date
                FROM fin_income i_cur
                JOIN fin_income i_prev
                    ON i_prev.stock_code = i_cur.stock_code
                    AND i_prev.report_date = DATE_SUB(i_cur.report_date, INTERVAL 1 YEAR)
                JOIN fin_income i_prev2
                    ON i_prev2.stock_code = i_cur.stock_code
                    AND i_prev2.report_date = DATE_SUB(i_cur.report_date, INTERVAL 2 YEAR)
                WHERE i_cur.report_date = %(rdate)s
                  AND i_prev.operating_revenue > 0
                  AND i_prev2.operating_revenue > 0
            ) fin
            JOIN stocks s ON s.stock_code = fin.stock_code
            JOIN (
                SELECT md.stock_code, md.close_price,
                       md.ma200,
                       ABS(md.close_price / md.ma200 - 1) * 100 AS ma200_deviation
                FROM (
                    SELECT stock_code, trade_date, close_price,
                           AVG(close_price) OVER (
                               PARTITION BY stock_code ORDER BY trade_date
                               ROWS BETWEEN 199 PRECEDING AND CURRENT ROW
                           ) AS ma200,
                           ROW_NUMBER() OVER (
                               PARTITION BY stock_code ORDER BY trade_date DESC
                           ) AS rn
                    FROM daily_kline
                    WHERE trade_date >= DATE_SUB(
                        (SELECT MAX(trade_date) FROM daily_kline), INTERVAL 210 DAY
                    )
                ) md
                WHERE md.rn = 1
                  AND md.ma200 IS NOT NULL
                  AND ABS(md.close_price / md.ma200 - 1) * 100 <= %(max_200_dev)s
            ) ma ON ma.stock_code = fin.stock_code
            WHERE s.stock_name NOT LIKE '%%ST%%'
              AND s.stock_name NOT LIKE '%%退市%%'
              AND (
                  (fin.prev_rev_growth < %(prev_decline)s AND fin.cur_rev_growth > %(rev_th)s AND fin.cur_profit > 0)
                  OR
                  (fin.prev_profit < 0 AND fin.cur_profit > %(min_profit)s AND fin.cur_rev_growth > 10)
              )
        ) sub2
        ORDER BY sub2.cur_rev_growth DESC
    """, {
        'rdate': rdate,
        'max_200_dev': max_ma200_deviation,
        'rev_th': min_rev_growth,
        'prev_decline': min_prev_decline,
        'min_profit': min_profit,
    })
