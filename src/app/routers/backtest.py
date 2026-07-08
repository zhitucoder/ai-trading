from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime, timedelta
from ..database import query

router = APIRouter()


def get_stock_name(code):
    r = query('SELECT stock_name FROM stocks WHERE stock_code = %s', [code])
    return r[0]['stock_name'] if r else ''


@router.get('/kline/{stock_code}')
def get_kline(stock_code: str, days: int = 500):
    name = get_stock_name(stock_code)
    sql = """
    SELECT trade_date, open_price, high_price, low_price, close_price, volume
    FROM daily_kline
    WHERE stock_code = %s
    ORDER BY trade_date DESC
    LIMIT %s
    """
    rows = query(sql, [stock_code, days])
    rows.reverse()
    return {'stock_code': stock_code, 'stock_name': name, 'rows': rows}


class TradeRecord(BaseModel):
    date: str
    direction: str
    shares: int
    price: float


class PositionBacktestInput(BaseModel):
    stock_code: str
    trades: List[TradeRecord]


@router.post('/backtest/position')
def position_backtest(body: PositionBacktestInput):
    stock_code = body.stock_code
    trades = sorted(body.trades, key=lambda t: t.date)

    if not trades:
        return {'daily_pnl': [], 'summary': {}}

    trade_dates = [t.date for t in trades]
    min_date = min(trade_dates)
    max_date = max(trade_dates)

    prices = query("""
        SELECT trade_date, close_price
        FROM daily_kline
        WHERE stock_code = %s AND trade_date >= %s AND trade_date <= (SELECT MAX(trade_date) FROM daily_kline)
        ORDER BY trade_date
    """, [stock_code, min_date])

    if not prices:
        return {'daily_pnl': [], 'summary': {}}

    price_dates = [p['trade_date'].isoformat() for p in prices]

    # Build trade map: date -> list of (direction, shares, price)
    trade_map = {}
    for t in trades:
        # Use the closest available trading date (>= trade date)
        closest = None
        for pd in price_dates:
            if pd >= t.date:
                closest = pd
                break
        if closest:
            trade_map.setdefault(closest, []).append((t.direction, t.shares, t.price))

    # Calculate daily P&L using average cost basis
    total_shares = 0
    total_cost = 0
    peak_value = 0
    max_drawdown = 0
    total_invested = 0
    total_sold_value = 0

    daily_pnl = []
    for p in prices:
        d = p['trade_date'].isoformat()
        cp = float(p['close_price'])

        if d in trade_map:
            for direction, shares, tprice in trade_map[d]:
                if direction == 'buy':
                    total_shares += shares
                    total_cost += shares * tprice
                    total_invested += shares * tprice
                else:
                    shares_sold = min(shares, total_shares)
                    if shares_sold > 0 and total_shares > 0:
                        avg_cost = total_cost / total_shares
                        sell_value = shares_sold * tprice
                        cost_of_sold = shares_sold * avg_cost
                        total_sold_value += sell_value
                        total_shares -= shares_sold
                        total_cost -= cost_of_sold

        market_value = total_shares * cp
        cost_basis = total_cost if total_shares > 0 else 0
        unrealized_pnl = market_value - cost_basis
        realized_pnl = total_sold_value - (total_invested - total_cost) if total_invested > 0 else 0
        total_pnl = realized_pnl + unrealized_pnl

        if market_value > peak_value:
            peak_value = market_value
        dd = (peak_value - market_value) / peak_value * 100 if peak_value > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

        daily_pnl.append({
            'date': d,
            'shares_held': total_shares,
            'cost_basis': round(cost_basis, 2),
            'market_value': round(market_value, 2),
            'unrealized_pnl': round(unrealized_pnl, 2),
            'daily_pnl': round(unrealized_pnl - (daily_pnl[-1]['unrealized_pnl'] if daily_pnl else 0) + (realized_pnl if d in trade_map and any(t[0]=='sell' for t in trade_map[d]) else 0), 2),
            'cumulative_pnl': round(total_pnl, 2),
        })

    if not daily_pnl:
        return {'daily_pnl': [], 'summary': {}}

    last = daily_pnl[-1]
    final_value = last['market_value']
    total_return = ((final_value + total_sold_value - total_invested) / total_invested * 100) if total_invested > 0 else 0

    return {
        'daily_pnl': daily_pnl,
        'summary': {
            'total_invested': round(total_invested, 2),
            'final_market_value': round(final_value, 2),
            'total_sold_value': round(total_sold_value, 2),
            'total_pnl': round(last['cumulative_pnl'], 2),
            'total_return': round(total_return, 2),
            'max_drawdown': round(max_drawdown, 2),
            'shares_held': total_shares,
        },
    }


class MABacktestInput(BaseModel):
    stock_code: str
    start_date: str
    end_date: str
    short_ma: int = 5
    long_ma: int = 20
    total_capital: float = 100000


@router.post('/backtest/ma')
def ma_backtest(
    stock_code: str = Query(...),
    start_date: str = Query(...),
    end_date: str = Query(...),
    short_ma: int = Query(5),
    long_ma: int = Query(20),
    total_capital: float = Query(100000),
):

    buffer = max(short_ma, long_ma) + 10
    sql_start = query("SELECT DATE_SUB(%s, INTERVAL %s DAY) AS d", [start_date, buffer])[0]['d']
    if isinstance(sql_start, timedelta):
        sql_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=buffer)).strftime('%Y-%m-%d')
    else:
        sql_start = sql_start.isoformat() if hasattr(sql_start, 'isoformat') else str(sql_start)

    prices = query("""
        SELECT trade_date, close_price
        FROM daily_kline
        WHERE stock_code = %s AND trade_date >= %s AND trade_date <= %s
        ORDER BY trade_date
    """, [stock_code, sql_start, end_date])

    if not prices:
        return {'trades': [], 'daily': [], 'summary': {}}

    dates = [p['trade_date'].isoformat() if hasattr(p['trade_date'], 'isoformat') else str(p['trade_date'])[:10] for p in prices]
    closes = [float(p['close_price']) for p in prices]
    n = len(closes)

    # Calculate MA
    ma_short = []
    ma_long = []
    for i in range(n):
        if i + 1 >= short_ma:
            ma_short.append(sum(closes[i + 1 - short_ma:i + 1]) / short_ma)
        else:
            ma_short.append(None)
        if i + 1 >= long_ma:
            ma_long.append(sum(closes[i + 1 - long_ma:i + 1]) / long_ma)
        else:
            ma_long.append(None)

    start_idx = 0
    for i, d in enumerate(dates):
        if d >= start_date:
            start_idx = i
            break

    cash = total_capital
    shares_held = 0
    trades = []
    wins = 0
    losses = 0
    peak_value = total_capital
    max_drawdown = 0
    total_invested = 0

    daily = []
    in_position = False

    for i in range(start_idx, n):
        if ma_short[i] is None or ma_long[i] is None:
            continue

        prev_short = ma_short[i - 1] if i > 0 and ma_short[i - 1] is not None else 0
        prev_long = ma_long[i - 1] if i > 0 and ma_long[i - 1] is not None else 0
        curr_short = ma_short[i]
        curr_long = ma_long[i]
        cp = closes[i]

        # Golden cross → buy as many 100-share lots as cash allows
        if not in_position and prev_short <= prev_long and curr_short > curr_long:
            max_shares = int(cash / cp / 100) * 100
            if max_shares >= 100:
                shares_held = max_shares
                cost = shares_held * cp
                cash -= cost
                total_invested += cost
                in_position = True
                trades.append({
                    'entry_date': dates[i],
                    'entry_price': round(cp, 2),
                    'shares': shares_held,
                })

        # Death cross → sell all
        elif in_position and prev_short >= prev_long and curr_short < curr_long:
            proceeds = shares_held * cp
            pnl = proceeds - (shares_held * trades[-1]['entry_price'])
            pnl_pct = (cp - trades[-1]['entry_price']) / trades[-1]['entry_price'] * 100
            cash += proceeds
            trades[-1]['exit_date'] = dates[i]
            trades[-1]['exit_price'] = round(cp, 2)
            trades[-1]['pnl'] = round(pnl, 2)
            trades[-1]['pnl_pct'] = round(pnl_pct, 2)
            if pnl > 0: wins += 1
            else: losses += 1
            shares_held = 0
            in_position = False

        portfolio = cash + shares_held * cp
        if portfolio > peak_value:
            peak_value = portfolio
        dd = (peak_value - portfolio) / peak_value * 100 if peak_value > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

        daily.append({
            'date': dates[i], 'close_price': round(cp, 2),
            'in_position': in_position,
            'cash': round(cash, 2), 'shares_held': shares_held,
            'portfolio': round(portfolio, 2),
            'cumulative_pnl': round(portfolio - total_capital, 2),
        })

    # Close open position at end
    if in_position and trades:
        cp = closes[-1]
        proceeds = shares_held * cp
        pnl = proceeds - (shares_held * trades[-1]['entry_price'])
        pnl_pct = (cp - trades[-1]['entry_price']) / trades[-1]['entry_price'] * 100
        trades[-1]['exit_date'] = dates[-1]
        trades[-1]['exit_price'] = round(cp, 2)
        trades[-1]['pnl'] = round(pnl, 2)
        trades[-1]['pnl_pct'] = round(pnl_pct, 2)
        if pnl > 0: wins += 1
        else: losses += 1

    closed_trades = [t for t in trades if 'exit_date' in t]
    total_trades = len(closed_trades)
    total_pnl = portfolio - total_capital
    total_return = (total_pnl / total_capital * 100) if total_capital > 0 else 0
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    return {
        'trades': trades,
        'daily': daily,
        'summary': {
            'total_trades': total_trades,
            'win_count': wins,
            'loss_count': losses,
            'win_rate': round(win_rate, 2),
            'total_capital': total_capital,
            'total_pnl': round(total_pnl, 2),
            'total_return': round(total_return, 2),
            'max_drawdown': round(max_drawdown, 2),
            'final_cash': round(cash, 2),
            'final_shares': shares_held,
        },
    }


@router.get('/backtest/quantitative-breakout')
def quantitative_breakout_backtest(
    stock_code: str = Query(...),
    n_days: int = Query(20, description='横盘观察天数'),
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    sql = """
    WITH prices AS (
        SELECT trade_date, close_price, high_price, low_price,
               LAG(close_price) OVER (ORDER BY trade_date) AS prev_close
        FROM daily_kline
        WHERE stock_code = %(stock_code)s
          AND trade_date >= DATE_SUB(%(start_date)s, INTERVAL %(n_days)s + 10 DAY)
          AND trade_date <= %(end_date)s
    ),
    daily_chg AS (
        SELECT trade_date, close_price, high_price, low_price,
               (close_price - prev_close) / prev_close * 100 AS change_pct
        FROM prices
        WHERE prev_close IS NOT NULL
    ),
    signal_check AS (
        SELECT trade_date, close_price, change_pct,
               MAX(CASE WHEN ABS(change_pct) > 4.0 THEN 1 ELSE 0 END)
                   OVER (ORDER BY trade_date ROWS BETWEEN %(n_days)s PRECEDING AND 1 PRECEDING) AS consol_violation,
               MAX(high_price)
                   OVER (ORDER BY trade_date ROWS BETWEEN %(n_days)s PRECEDING AND 1 PRECEDING) AS n_day_high,
               MIN(low_price)
                   OVER (ORDER BY trade_date ROWS BETWEEN %(n_days)s PRECEDING AND 1 PRECEDING) AS n_day_low,
               ROW_NUMBER() OVER (ORDER BY trade_date) AS rn
        FROM daily_chg
    )
    SELECT trade_date, ROUND(close_price, 2) AS signal_price,
           ROUND(change_pct, 2) AS breakout_pct,
           ROUND((n_day_high - n_day_low) / n_day_low * 100, 2) AS range_pct
    FROM signal_check
    WHERE rn > %(n_days)s
      AND change_pct >= 7.0
      AND consol_violation = 0
      AND (n_day_high - n_day_low) / n_day_low * 100 <= 12.0
      AND trade_date >= %(start_date)s
      AND trade_date <= %(end_date)s
    ORDER BY trade_date DESC
    """
    rows = query(sql, {'stock_code': stock_code, 'n_days': n_days, 'start_date': start_date, 'end_date': end_date})
    name = get_stock_name(stock_code)
    return {
        'stock_code': stock_code,
        'stock_name': name,
        'n_days': n_days,
        'signals': rows,
        'total_signals': len(rows),
    }


@router.get('/backtest/quantitative-breakout/market')
def quantitative_breakout_market_backtest(
    months: int = Query(6, description='回溯月数', ge=1, le=24),
):
    sql = """
    WITH breakout_stocks AS (
        SELECT DISTINCT k1.stock_code
        FROM daily_kline k1
        JOIN daily_kline k2 ON k2.stock_code = k1.stock_code AND k2.trade_date = DATE_SUB(k1.trade_date, INTERVAL 1 DAY)
        WHERE k1.trade_date >= DATE_SUB((SELECT MAX(trade_date) FROM daily_kline), INTERVAL %(months)s MONTH)
          AND k1.close_price / k2.close_price >= 1.07
    ),
    prices AS (
        SELECT k.stock_code, k.trade_date, k.close_price,
               LAG(k.close_price) OVER (PARTITION BY k.stock_code ORDER BY k.trade_date) AS prev_close,
               LEAD(k.close_price, 21) OVER (PARTITION BY k.stock_code ORDER BY k.trade_date) AS future_close_1m,
               k.high_price, k.low_price
        FROM daily_kline k
        WHERE k.stock_code IN (SELECT stock_code FROM breakout_stocks)
          AND k.trade_date >= DATE_SUB((SELECT MAX(trade_date) FROM daily_kline), INTERVAL %(months)s + 1 MONTH)
    ),
    daily_chg AS (
        SELECT stock_code, trade_date, close_price, high_price, low_price, future_close_1m,
               (close_price - prev_close) / prev_close * 100 AS change_pct
        FROM prices WHERE prev_close IS NOT NULL
    ),
    signal_check AS (
        SELECT stock_code, trade_date, close_price, change_pct, future_close_1m,
               MAX(CASE WHEN ABS(change_pct) > 4.0 THEN 1 ELSE 0 END)
                   OVER (PARTITION BY stock_code ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS consol_violation,
               MAX(high_price)
                   OVER (PARTITION BY stock_code ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS n_day_high,
               MIN(low_price)
                   OVER (PARTITION BY stock_code ORDER BY trade_date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS n_day_low,
               ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date) AS rn
        FROM daily_chg
    )
    SELECT s.stock_code, st.stock_name, s.trade_date, ROUND(s.close_price, 2) AS signal_price,
           ROUND(s.change_pct, 2) AS breakout_pct,
           ROUND((s.n_day_high - s.n_day_low) / s.n_day_low * 100, 2) AS range_pct,
           ROUND((s.future_close_1m / s.close_price - 1) * 100, 2) AS return_1m_pct
    FROM signal_check s
    JOIN stocks st ON st.stock_code = s.stock_code
    WHERE s.rn > 20
      AND s.change_pct >= 7.0
      AND s.consol_violation = 0
      AND (s.n_day_high - s.n_day_low) / s.n_day_low * 100 <= 12.0
      AND s.future_close_1m IS NOT NULL
    ORDER BY s.trade_date DESC, s.stock_code
    """
    rows = query(sql, {'months': months})
    returns = [r['return_1m_pct'] for r in rows if r['return_1m_pct'] is not None]
    win = sum(1 for r in returns if r > 0)
    loss = sum(1 for r in returns if r <= 0)
    total = len(returns)
    return {
        'months': months,
        'total_signals': len(rows),
        'summary': {
            'total_signals': total,
            'win_count': win,
            'loss_count': loss,
            'win_rate': round(win / total * 100, 2) if total > 0 else 0,
            'avg_return': round(sum(returns) / total, 2) if total > 0 else 0,
            'max_return': round(max(returns), 2) if total > 0 else 0,
            'min_return': round(min(returns), 2) if total > 0 else 0,
        },
        'signals': rows,
    }


@router.get('/kline_range/{stock_code}')
def get_kline_range(stock_code: str, start_date: str, end_date: str):
    name = get_stock_name(stock_code)
    sql = """
    SELECT trade_date, open_price, high_price, low_price, close_price, volume
    FROM daily_kline
    WHERE stock_code = %s AND trade_date >= %s AND trade_date <= %s
    ORDER BY trade_date
    """
    rows = query(sql, [stock_code, start_date, end_date])
    return {'stock_code': stock_code, 'stock_name': name, 'rows': rows}
