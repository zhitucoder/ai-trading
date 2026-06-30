import re
from datetime import timedelta
from src.database import get_conn


STOCK_NAMES: dict[str, str] = {}
STOCK_CODES: set[str] = set()


def _load_stocks():
    global STOCK_NAMES, STOCK_CODES
    if STOCK_NAMES:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT stock_code, stock_name FROM stocks WHERE security_type = 'stock'"
            )
            rows = cur.fetchall()
            STOCK_NAMES = {r['stock_code']: r['stock_name'] for r in rows}
            STOCK_CODES = set(STOCK_NAMES.keys())
    except Exception:
        STOCK_NAMES = {}
        STOCK_CODES = set()
    finally:
        conn.close()


def valid_stock(code: str) -> bool:
    _load_stocks()
    if STOCK_CODES:
        return code in STOCK_CODES
    return code.startswith(('00', '30', '60', '68'))


def _attach_names(results: list[dict]):
    _load_stocks()
    for r in results:
        r['stock_name'] = STOCK_NAMES.get(r['stock_code'], '')


def get_latest_date():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(trade_date) AS max_d FROM daily_kline")
            return cur.fetchone()['max_d']
    finally:
        conn.close()


def get_ma_prices(ma_periods: list[int]):
    max_period = max(ma_periods)
    lookback = max(int(max_period * 1.5), 120)
    latest = get_latest_date()
    cutoff = latest - timedelta(days=lookback)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT stock_code, close_price FROM daily_kline WHERE trade_date >= %s ORDER BY stock_code, trade_date DESC",
                (cutoff,),
            )
            rows = cur.fetchall()

        result = {}
        for row in rows:
            code = row['stock_code']
            if not valid_stock(code):
                continue
            if code not in result:
                result[code] = []
            if len(result[code]) < max_period:
                result[code].append(float(row['close_price']))
        return result
    finally:
        conn.close()


def check_bullish_alignment(prices: list[float], ma_periods: list[int]) -> bool:
    if len(prices) < max(ma_periods):
        return False
    mas = []
    for p in ma_periods:
        ma = sum(prices[:p]) / p
        mas.append(ma)
    return all(mas[i] > mas[i + 1] for i in range(len(mas) - 1))


def _attach_names(results: list[dict]):
    _load_stocks()
    for r in results:
        r['stock_name'] = STOCK_NAMES.get(r['stock_code'], '')


def screen_technical(ma_periods: list[int], bullish: bool = True) -> list[dict]:
    prices_map = get_ma_prices(ma_periods)
    results = []
    for code, prices in prices_map.items():
        if len(prices) < max(ma_periods):
            continue
        if bullish and check_bullish_alignment(prices, ma_periods):
            mas = {str(p): round(sum(prices[:p]) / p, 2) for p in ma_periods}
            results.append({
                'stock_code': code,
                'latest_price': prices[0],
                'mas': mas,
            })
    _attach_names(results)
    return results


def get_latest_prices() -> dict[str, float]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT k.stock_code, k.close_price
                FROM daily_kline k
                INNER JOIN (
                    SELECT stock_code, MAX(trade_date) AS max_d
                    FROM daily_kline
                    GROUP BY stock_code
                ) latest ON k.stock_code = latest.stock_code
                    AND k.trade_date = latest.max_d
            """)
            return {r['stock_code']: float(r['close_price']) for r in cur.fetchall()}
    finally:
        conn.close()


def get_latest_shares() -> dict[str, float]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.stock_code, s.total_shares
                FROM fin_shareholder s
                INNER JOIN (
                    SELECT stock_code, MAX(report_date) AS max_d
                    FROM fin_shareholder
                    GROUP BY stock_code
                ) latest ON s.stock_code = latest.stock_code
                    AND s.report_date = latest.max_d
                WHERE s.total_shares IS NOT NULL AND s.total_shares > 0
            """)
            return {r['stock_code']: float(r['total_shares']) for r in cur.fetchall()}
    finally:
        conn.close()


def _annualize_eps(eps, report_date):
    month = report_date.month
    if month == 3:
        return eps * 4
    if month == 6:
        return eps * 2
    if month == 9:
        return eps * 4 / 3
    return eps


def screen_fundamental(
    revenue_growth_min: float | None = 20.0,
    net_profit_growth_min: float | None = 20.0,
    debt_asset_ratio_max: float | None = 50.0,
) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            conditions = [
                "r.stock_code REGEXP '^(00|30|60|68|8)'",
                'r.debt_ratio > 0',
                'r.basic_eps IS NOT NULL',
                'r.basic_eps > 0',
            ]
            params = []
            if revenue_growth_min is not None:
                conditions.append("r.revenue_growth_rate >= %s")
                params.append(revenue_growth_min / 100.0)
            if net_profit_growth_min is not None:
                conditions.append("r.net_profit_growth_rate >= %s")
                params.append(net_profit_growth_min)
            if debt_asset_ratio_max is not None:
                conditions.append("r.debt_ratio <= %s")
                params.append(debt_asset_ratio_max)

            where = " AND ".join(conditions)
            sql = f"""
                SELECT r.stock_code, r.report_date,
                       r.revenue_growth_rate, r.net_profit_growth_rate,
                       r.debt_ratio, r.roe, r.net_margin, r.basic_eps
                FROM fin_ratios r
                INNER JOIN (
                    SELECT stock_code, MAX(report_date) AS max_date
                    FROM fin_ratios
                    GROUP BY stock_code
                ) latest ON r.stock_code = latest.stock_code
                    AND r.report_date = latest.max_date
                WHERE {where}
                ORDER BY r.revenue_growth_rate DESC
                LIMIT 200
            """
            cur.execute(sql, params)
            rows = cur.fetchall()
            for r in rows:
                r['revenue_growth_rate'] = round(r['revenue_growth_rate'] * 100, 2) if r.get('revenue_growth_rate') else 0
                for k in ('net_profit_growth_rate', 'debt_ratio'):
                    if r.get(k) is not None:
                        r[k] = round(r[k], 2)
                r['market_cap'] = None
                r['pe_ttm'] = None

        latest_prices = get_latest_prices()
        latest_shares = get_latest_shares()

        for r in rows:
            code = r['stock_code']
            price = latest_prices.get(code)
            shares = latest_shares.get(code)
            eps = r.get('basic_eps')
            rdate = r.get('report_date')

            if price and shares and price > 0 and shares > 0:
                r['market_cap'] = round(shares * price / 10000, 2)

            if price and eps and eps > 0 and rdate:
                annual_eps = _annualize_eps(float(eps), rdate)
                if annual_eps > 0:
                    pe = price / annual_eps
                    if 0 < pe < 500:
                        r['pe_ttm'] = round(pe, 2)

        _attach_names(rows)
        return rows
    finally:
        conn.close()


def screen_combined(
    ma_periods: list[int],
    revenue_growth_min: float = 20.0,
    net_profit_growth_min: float = 20.0,
    debt_asset_ratio_max: float = 50.0,
) -> list[dict]:
    conn = get_conn()
    try:
        fundamental_map = {}
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.stock_code,
                       r.revenue_growth_rate, r.net_profit_growth_rate, r.debt_ratio
                FROM fin_ratios r
                INNER JOIN (
                    SELECT stock_code, MAX(report_date) AS max_date
                    FROM fin_ratios
                    GROUP BY stock_code
                ) latest ON r.stock_code = latest.stock_code
                    AND r.report_date = latest.max_date
                WHERE r.stock_code REGEXP '^(00|30|60|68|8)'
                  AND r.revenue_growth_rate >= %s
                  AND r.net_profit_growth_rate >= %s
                  AND r.debt_ratio > 0
                  AND r.debt_ratio <= %s
                  AND r.basic_eps IS NOT NULL
                  AND r.basic_eps > 0
            """, (revenue_growth_min / 100.0, net_profit_growth_min, debt_asset_ratio_max))
            for row in cur.fetchall():
                fundamental_map[row['stock_code']] = row

        if not fundamental_map:
            return []

        prices_map = get_ma_prices(ma_periods)

        results = []
        for code, fin in fundamental_map.items():
            prices = prices_map.get(code, [])
            if len(prices) < max(ma_periods):
                continue
            if check_bullish_alignment(prices, ma_periods):
                mas = {str(p): round(sum(prices[:p]) / p, 2) for p in ma_periods}
                results.append({
                    'stock_code': code,
                    'latest_price': prices[0],
                    'mas': mas,
                    'revenue_growth_rate': round(fin['revenue_growth_rate'] * 100, 2) if fin.get('revenue_growth_rate') else 0,
                    'net_profit_growth_rate': round(fin['net_profit_growth_rate'], 2) if fin.get('net_profit_growth_rate') else 0,
                    'debt_ratio': round(fin['debt_ratio'], 2) if fin.get('debt_ratio') else 0,
                })
        _attach_names(results)
        return results
    finally:
        conn.close()
