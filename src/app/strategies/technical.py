from ..database import query

TECHNICAL_STRATEGIES = {
    'ma_bullish': {
        'name': '均线多头排列',
        'description': 'MA5 > MA10 > MA20 > MA60，短中期均线多头向上发散',
        'params': {
            'ma_periods': {'type': 'list', 'default': [5, 10, 20, 60], 'description': '均线周期列表'},
        },
    },
    'quantitative_breakout': {
        'name': '量化突破（横盘+大阳线）',
        'description': '横盘N日（涨跌幅≤4%，箱体振幅≤12%）+ 今日大阳线突破（涨幅≥7%）',
        'params': {
            'n_days': {'type': 'int', 'default': 20, 'description': '横盘观察天数'},
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


def screen_quantitative_breakout(n_days=20):
    window_days = (n_days + 1) * 2 + 10
    sql = f"""
    WITH ranked AS (
        SELECT k.stock_code, k.trade_date, k.close_price, k.high_price, k.low_price,
               LAG(k.close_price) OVER (PARTITION BY k.stock_code ORDER BY k.trade_date) AS prev_close,
               ROW_NUMBER() OVER (PARTITION BY k.stock_code ORDER BY k.trade_date DESC) AS rn
        FROM daily_kline k
        WHERE k.trade_date >= DATE_SUB((SELECT MAX(trade_date) FROM daily_kline), INTERVAL {window_days} DAY)
    ),
    breakout AS (
        SELECT stock_code, close_price AS breakout_price, prev_close, trade_date
        FROM ranked
        WHERE rn = 1
          AND prev_close IS NOT NULL
          AND (close_price / prev_close - 1) * 100 >= 7.0
    ),
    consol AS (
        SELECT r.stock_code, r.high_price, r.low_price, r.close_price, r.prev_close
        FROM ranked r
        JOIN breakout b ON b.stock_code = r.stock_code
        WHERE r.rn > 1 AND r.rn <= {n_days + 1}
          AND r.prev_close IS NOT NULL
    ),
    consol_check AS (
        SELECT stock_code,
               COUNT(*) AS total_days,
               SUM(CASE WHEN ABS((close_price / prev_close - 1) * 100) > 4.0 THEN 1 ELSE 0 END) AS violation_count,
               MAX(high_price) AS n_day_high,
               MIN(low_price) AS n_day_low
        FROM consol
        GROUP BY stock_code
    )
    SELECT c.stock_code, s.stock_name, b.breakout_price,
           ROUND((c.n_day_high - c.n_day_low) / c.n_day_low * 100, 2) AS range_pct,
           ROUND((b.breakout_price / b.prev_close - 1) * 100, 2) AS breakout_pct,
           b.trade_date AS breakout_date
    FROM consol_check c
    JOIN breakout b ON b.stock_code = c.stock_code
    JOIN stocks s ON s.stock_code = c.stock_code
    WHERE c.violation_count = 0
      AND c.total_days >= {n_days}
      AND (c.n_day_high - c.n_day_low) / c.n_day_low * 100 <= 12.0
    ORDER BY b.breakout_price DESC
    """
    return query(sql)
