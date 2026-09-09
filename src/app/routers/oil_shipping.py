from collections import OrderedDict
from fastapi import APIRouter
from ..database import get_conn

router = APIRouter()

OIL_VARIETIES = {'WTI', 'Brent'}
FREIGHT_TABLES = {
    'BDTI': 'shipping_bdti',
    'BCTI': 'shipping_bcti',
    'BDI': 'shipping_bdi',
    'BCI': 'shipping_bci',
    'BPI': 'shipping_bpi',
}
STOCKS = {
    '600938': '中国海油',
    '601857': '中国石油',
    '601872': '招商轮船',
    '600026': '中远海能',
    '600428': '中远海特',
    '600115': '东方航空',
    '600029': '南方航空',
}


def _monthly_last_day(cur, table, date_col, value_col, where_sql='', params=()):
    """Return monthly last-trading-day {date: 'YYYY-MM-DD', value}` list."""
    sql = f"""
        SELECT a.{date_col} AS d, a.{value_col} AS v
        FROM `{table}` a
        JOIN (
            SELECT DATE_FORMAT({date_col}, '%%Y-%%m') AS ym, MAX({date_col}) AS md
            FROM `{table}` {where_sql}
            GROUP BY ym
        ) b ON a.{date_col} = b.md
        ORDER BY a.{date_col}
    """
    cur.execute(sql, params)
    return [{'date': str(r['d']), 'value': r['v']} for r in cur.fetchall()]


def _stock_monthly_last_day(cur, stock_code):
    sql = """
        SELECT a.trade_date AS d, a.close_price AS v
        FROM daily_kline_qfq a
        JOIN (
            SELECT DATE_FORMAT(trade_date, '%%Y-%%m') AS ym, MAX(trade_date) AS md
            FROM daily_kline_qfq WHERE stock_code=%s
            GROUP BY ym
        ) b ON a.trade_date = b.md
        WHERE a.stock_code=%s
        ORDER BY a.trade_date
    """
    cur.execute(sql, (stock_code, stock_code))
    return [{'date': str(r['d']), 'value': r['v']} for r in cur.fetchall()]


def _single_quarter_profit(cur, stock_code, start='2015-01-01'):
    """fin_quarterly 直接存单季度归母净利润(q_parent_net_profit)，无需差分。
    仅保留 3/6/9/12 月的单季值。
    """
    cur.execute("""
        SELECT report_date, q_parent_net_profit
        FROM fin_quarterly
        WHERE stock_code=%s AND report_date >= %s
          AND MONTH(report_date) IN (3, 6, 9, 12)
        ORDER BY report_date
    """, (stock_code, start))
    rows = cur.fetchall()

    out = []
    for r in rows:
        v = r['q_parent_net_profit']
        if v is None:
            continue
        out.append({'date': str(r['report_date'])[:7], 'value': round(float(v) / 1e8, 2)})
    return out


@router.get('/oil-shipping/data')
def oil_shipping_data():
    conn = get_conn()
    try:
        cur = conn.cursor()

        oil = OrderedDict()
        for variety in sorted(OIL_VARIETIES):
            cur.execute("""SELECT close_price AS v, trade_date AS d FROM crude_oil_daily
                           WHERE variety=%s AND trade_date >= '2015-01-01' ORDER BY trade_date""",
                        (variety,))
            raw = cur.fetchall()
            by_month = OrderedDict()
            for r in raw:
                ym = str(r['d'])[:7]
                by_month[ym] = float(r['v'])
            oil[variety] = [{'date': k, 'value': v} for k, v in by_month.items()]

        freight = OrderedDict()
        for key, table in FREIGHT_TABLES.items():
            raw = _monthly_last_day(cur, table, 'trade_date', 'close_value')
            freight[key] = [{'date': r['date'][:7], 'value': float(r['value'])} for r in raw]

        stocks = OrderedDict()
        for code, name in STOCKS.items():
            price = _stock_monthly_last_day(cur, code)
            profit = _single_quarter_profit(cur, code)
            stocks[code] = {
                'code': code,
                'name': name,
                'price': [{'date': r['date'][:7], 'value': float(r['value'])} for r in price],
                'profit': profit,
            }

        return {'oil': oil, 'freight': freight, 'stocks': stocks}
    finally:
        conn.close()