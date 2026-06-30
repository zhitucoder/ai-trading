from ..database import query

TECHNICAL_STRATEGIES = {
    'ma_bullish': {
        'name': '均线多头排列',
        'description': 'MA5 > MA10 > MA20 > MA60，短中期均线多头向上发散',
        'params': {
            'ma_periods': {'type': 'list', 'default': [5, 10, 20, 60], 'description': '均线周期列表'},
        },
    },
}


def screen_ma_bullish(ma_periods=None):
    if ma_periods is None:
        ma_periods = [5, 10, 20, 60]
    periods = sorted(ma_periods)
    max_period = max(periods)

    # Build window expressions for each MA period
    ma_selects = []
    conditions = []
    for p in periods:
        alias = f'ma{p}'
        ma_selects.append(
            f'AVG(close_price) OVER (PARTITION BY recent.stock_code ORDER BY recent.trade_date ROWS BETWEEN {p-1} PRECEDING AND CURRENT ROW) AS {alias}'
        )

    # Build condition: ma_p1 > ma_p2 > ... (each period's MA > next period's MA)
    for i in range(len(periods) - 1):
        conditions.append(f'ma{periods[i]} > ma{periods[i + 1]}')

    cond_sql = ' AND '.join(conditions)

    sql = f"""
    WITH recent AS (
        SELECT stock_code, trade_date, close_price
        FROM daily_kline
        WHERE trade_date >= DATE_SUB((SELECT MAX(trade_date) FROM daily_kline), INTERVAL {max_period + 10} DAY)
    ),
    ma_calc AS (
        SELECT stock_code, trade_date, close_price,
               {', '.join(ma_selects)},
               ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
        FROM recent
    )
    SELECT m.stock_code, s.stock_name, m.close_price,
           {', '.join(f'm.ma{p}' for p in periods)}
    FROM ma_calc m
    JOIN stocks s ON s.stock_code = m.stock_code
    WHERE m.rn = 1 AND {cond_sql}
    ORDER BY m.ma{max(periods)} DESC
    """
    return query(sql)
