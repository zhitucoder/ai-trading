"""低估成长股 · 底部蓄势选股策略

寻找「业绩连续多年增长、但股价长期盘整在底部」的低估成长股，
在其爆发式上涨（主升浪）前纳入观察。

参考案例：603993 洛阳钼业 —— 归母净利连续 6 年增长（2020→2025），
股价 2018-2024 长期在 3.4~9.7 元箱体盘整，2025 下半年起主升浪。

数据口径（必须遵守）：
- 年度业绩：ads_stock_annual（parent_net_profit/profit_yoy/roe，派生指标一律以 ads_* 为准）
- 最新快照：ads_stock_latest（pe_ttm / profit_yoy 单季同比）
- 价格：daily_kline_qfq（前复权，避免分红送转导致「股价没涨」被误判）
- parent_net_profit 单位为元；profit_yoy / revenue_yoy 为百分数值（50.3 即 50.3%）

打分（0-100）：业绩质量 30 + 底部特征 40 + 启动确认 30。
"""
from datetime import date

from ..database import query

UNDERVALUED_GROWTH_STRATEGIES = {
    'undervalued_growth': {
        'name': '低估成长股·底部蓄势',
        'description': '业绩连续多年增长但股价长期盘整底部，估值压缩，主升浪启动前布局',
        'params': {},
    },
}

# 底部特征严格度：硬性过滤阈值（回撤/位置比例/背离度为小数，PE 上限）
STRICTNESS = {
    'bottom': {
        'name': '宽松',
        'drawdown_min': 0.0,
        'position_max': 1.0,
        'divergence_min': None,
        'pe_max': None,
    },
    'standard': {
        'name': '标准',
        'drawdown_min': 0.15,
        'position_max': 0.7,
        'divergence_min': 0.0,
        'pe_max': 50.0,
    },
    'strict': {
        'name': '严格',
        'drawdown_min': 0.25,
        'position_max': 0.5,
        'divergence_min': 0.10,
        'pe_max': 30.0,
    },
}

# 交易日近似：1 年 ≈ 250 个交易日
TRADING_DAYS_1Y = 250


def _sub_years(d, years):
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


def get_latest_trade_date():
    row = query("SELECT MAX(trade_date) AS d FROM daily_kline_qfq")
    return row[0]['d'] if row else None


def get_latest_annual_date():
    row = query("SELECT MAX(report_date) AS d FROM ads_stock_annual")
    return row[0]['d'] if row else None


def _query_annual_candidates(consecutive_years, profit_min, profit_max):
    """连续增长 + 净利规模筛选。

    最近 N 个年度归母净利逐年上升（且每年盈利），最新年度净利在 [profit_min, profit_max)。
    返回：stock_code, latest_profit(元), profit_3y_ago(元, rn=4), profit_yoy(百分数), roe。
    """
    latest_annual = get_latest_annual_date()
    if not latest_annual:
        return []
    sql = """
    WITH annual AS (
        SELECT a.stock_code, s.stock_name, a.report_date, a.parent_net_profit, a.profit_yoy, a.roe,
               ROW_NUMBER() OVER (PARTITION BY a.stock_code ORDER BY a.report_date DESC) AS rn,
               LAG(a.parent_net_profit) OVER (PARTITION BY a.stock_code ORDER BY a.report_date) AS prev_profit
        FROM ads_stock_annual a
        JOIN stocks s ON s.stock_code = a.stock_code
        WHERE a.report_date BETWEEN DATE_SUB(%(latest)s, INTERVAL 6 YEAR) AND %(latest)s
          AND s.stock_name NOT LIKE '%%ST%%'
    ),
    recent AS (
        SELECT * FROM annual WHERE rn <= %(N)s
    ),
    profit3 AS (
        SELECT stock_code, parent_net_profit AS profit_3y_ago
        FROM annual WHERE rn = 4
    )
    SELECT r.stock_code,
           MAX(r.stock_name)                                        AS stock_name,
           MAX(CASE WHEN r.rn = 1 THEN r.parent_net_profit END) AS latest_profit,
           MAX(p.profit_3y_ago)                                AS profit_3y_ago,
           MAX(CASE WHEN r.rn = 1 THEN r.profit_yoy END)        AS profit_yoy,
           MAX(CASE WHEN r.rn = 1 THEN r.roe END)               AS roe
    FROM recent r
    LEFT JOIN profit3 p ON p.stock_code = r.stock_code
    GROUP BY r.stock_code
    HAVING COUNT(*) = %(N)s
       AND SUM(CASE WHEN r.parent_net_profit <= 0 THEN 1 ELSE 0 END) = 0
       AND SUM(CASE WHEN r.parent_net_profit > r.prev_profit OR r.prev_profit IS NULL
                    THEN 1 ELSE 0 END) = COUNT(*)
       AND MAX(CASE WHEN r.rn = 1 THEN r.parent_net_profit END) >= %(profit_min)s
       AND (%(profit_max)s IS NULL
            OR MAX(CASE WHEN r.rn = 1 THEN r.parent_net_profit END) < %(profit_max)s)
    """
    return query(sql, {
        'latest': latest_annual,
        'N': consecutive_years,
        'profit_min': profit_min,
        'profit_max': profit_max,
    })


def _chunks(items, size=500):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _query_price_series(codes, t_3y):
    """批量拉取候选池的前复权日线（t_3y 起），返回 {code: [(trade_date, close, volume), ...]}。"""
    series = {}
    for chunk in _chunks(codes):
        ph = ','.join(['%s'] * len(chunk))
        rows = query(f"""
            SELECT stock_code, trade_date, close_price, high_price, low_price, volume
            FROM daily_kline_qfq
            WHERE stock_code IN ({ph}) AND trade_date >= %s
            ORDER BY stock_code, trade_date
        """, chunk + [t_3y])
        for r in rows:
            series.setdefault(r['stock_code'], []).append(
                (r['trade_date'], float(r['close_price']),
                 float(r['high_price'] or r['close_price']),
                 float(r['low_price'] or r['close_price']),
                 float(r['volume'] or 0)))
    return series


def _query_latest_snapshot(codes):
    """ads_stock_latest：pe_ttm / 单季净利同比 / 市值。"""
    snap = {}
    for chunk in _chunks(codes):
        ph = ','.join(['%s'] * len(chunk))
        rows = query(f"""
            SELECT stock_code, pe_ttm, market_cap, profit_yoy, roe_ttm, dividend_yield
            FROM ads_stock_latest
            WHERE stock_code IN ({ph})
        """, chunk)
        for r in rows:
            snap[r['stock_code']] = r
    return snap


def _compute_price_metrics(series):
    """从前复权日线序列计算底部特征与启动确认指标。

    series 升序 [(date, close, high, low, volume)]。
    返回 dict 或 None（数据不足）。
    """
    if not series or len(series) < TRADING_DAYS_1Y:
        return None

    n = len(series)
    closes = [s[1] for s in series]
    highs = [s[2] for s in series]
    lows = [s[3] for s in series]
    vols = [s[4] for s in series]
    last_close = closes[-1]

    # 近 3 年区间（序列即从 3 年前起）
    high_3y = max(highs)
    low_3y = min(lows)

    # 近 1 年 / 前 1 年窗口（约 250 交易日 / 年）
    i_1y = n - 1 - TRADING_DAYS_1Y if n > TRADING_DAYS_1Y else 0
    i_2y = n - 1 - 2 * TRADING_DAYS_1Y if n > 2 * TRADING_DAYS_1Y else 0
    if i_1y <= 0:
        high_1y, low_1y = max(highs), min(lows)
        low_prev_1y = None
    else:
        high_1y = max(highs[i_1y:])
        low_1y = min(lows[i_1y:])
        low_prev_1y = min(lows[i_2y:i_1y]) if i_2y > 0 and i_2y < i_1y else None

    close_3y_ago = closes[0]
    close_250d_ago = closes[n - 1 - TRADING_DAYS_1Y] if n > TRADING_DAYS_1Y else None

    # 均线 & 金叉（最近 60 交易日窗口内 MA60 上穿 MA250）
    above_ma250 = False
    if n >= 250:
        ma250 = sum(closes[-250:]) / 250
        ma60 = sum(closes[-60:]) / 60
        above_ma250 = last_close > ma250 and ma60 > ma250

    golden_cross = False
    if n >= 310:
        for i in range(n - 60, n):
            if i < 250:
                continue
            w60 = sum(closes[i - 59:i + 1]) / 60
            w250 = sum(closes[i - 249:i + 1]) / 250
            p60 = sum(closes[i - 60:i]) / 60
            p250 = sum(closes[i - 250:i]) / 250
            if p60 <= p250 and w60 > w250:
                golden_cross = True
                break

    # 平台放量突破：近 20 日某日放量(>5日均量1.5倍) 且收盘创近 60 日新高
    volume_breakout = False
    if n >= 80:
        for i in range(n - 20, n):
            prev_vol = sum(vols[i - 5:i]) / 5 if i >= 5 else None
            hi_60 = max(closes[max(i - 60, 0):i])
            if prev_vol and prev_vol > 0 and vols[i] > prev_vol * 1.5 and closes[i] >= hi_60:
                volume_breakout = True
                break

    # 底部抬升：近 1 年最低价 > 前 1 年最低价
    bottom_lift = bool(low_prev_1y is not None and low_1y > low_prev_1y)

    # 底部特征指标
    drawdown_3y = 1 - last_close / high_3y if high_3y else None
    amp_3y = high_3y / low_3y - 1 if low_3y else None
    amp_1y = high_1y / low_1y - 1 if low_1y else None
    position_pct = (last_close - low_3y) / (high_3y - low_3y) if high_3y > low_3y else 0.0
    pct_250d = last_close / close_250d_ago - 1 if close_250d_ago else None
    price_cagr_3y = (last_close / close_3y_ago) ** (1 / 3) - 1 if close_3y_ago > 0 else None

    return {
        'drawdown_3y': drawdown_3y,
        'amp_3y': amp_3y,
        'amp_1y': amp_1y,
        'position_pct': position_pct,
        'pct_250d': pct_250d,
        'price_cagr_3y': price_cagr_3y,
        'above_ma250': above_ma250,
        'golden_cross': golden_cross,
        'volume_breakout': volume_breakout,
        'bottom_lift': bottom_lift,
    }


def _score_perf(n_years, profit_yoy, roe):
    """业绩质量(30)：连续年数12 + 最新年度净利同比9 + ROE档位9。"""
    s_n = 12 * min(max(n_years, 0) / 7.0, 1.0)
    s_yoy = 9 * min(max(profit_yoy or 0, 0) / 40.0, 1.0)
    s_roe = 9 * min(max(roe or 0, 0) / 15.0, 1.0)
    return s_n + s_yoy + s_roe


def _score_bottom(divergence, drawdown, amp_3y, position):
    """底部特征(40)：背离度14 + 距高点回撤8 + 3年振幅8 + 位置比例10。"""
    s_div = 14 * min(max(divergence or 0, 0) / 0.20, 1.0)
    s_dd = 8 * min(max(drawdown or 0, 0) / 0.25, 1.0)
    s_amp = 8 * max(min((2.0 - (amp_3y or 0)) / 2.0, 1.0), 0.0)
    s_pos = 10 * max((0.5 - (position or 0)) / 0.5, 0.0)
    return s_div + s_dd + s_amp + s_pos


def _score_confirm(above_ma250, golden_cross, volume_breakout, profit_accel, bottom_lift):
    """启动确认(30)：站上年线8 + 金叉7 + 放量突破7 + 业绩加速5 + 底部抬升3。"""
    return (8 if above_ma250 else 0) \
        + (7 if golden_cross else 0) \
        + (7 if volume_breakout else 0) \
        + (5 if profit_accel else 0) \
        + (3 if bottom_lift else 0)


def screen_undervalued_growth(
    consecutive_years: int = 5,
    profit_min: float = 1e9,
    profit_max: float | None = None,
    strictness: str = 'standard',
    require_confirm: bool = False,
) -> list[dict]:
    """低估成长股·底部蓄势筛选。

    Args:
        consecutive_years: 连续增长年数 N ∈ {3,4,5,6,7}
        profit_min: 最新年度归母净利下限(元)
        profit_max: 上限(元)，None 不限
        strictness: bottom|standard|strict 底部严格度
        require_confirm: 是否强制 ≥2 个启动确认信号
    """
    conf = STRICTNESS.get(strictness, STRICTNESS['standard'])

    candidates = _query_annual_candidates(consecutive_years, profit_min, profit_max)
    if not candidates:
        return []

    codes = [c['stock_code'] for c in candidates]
    latest_trade = get_latest_trade_date()
    if not latest_trade:
        return []

    t_3y = _sub_years(latest_trade, 3)
    series_map = _query_price_series(codes, t_3y)
    snap_map = _query_latest_snapshot(codes)

    annual_map = {c['stock_code']: c for c in candidates}

    results = []
    for cand in candidates:
        code = cand['stock_code']
        pm = _compute_price_metrics(series_map.get(code, []))
        if not pm:
            continue
        snap = snap_map.get(code, {})

        latest_profit = float(cand['latest_profit'] or 0)
        profit_3y_ago = float(cand['profit_3y_ago'] or 0)
        profit_cagr_3y = (latest_profit / profit_3y_ago) ** (1 / 3) - 1 \
            if profit_3y_ago > 0 else None
        price_cagr_3y = pm['price_cagr_3y']
        divergence = (profit_cagr_3y - price_cagr_3y) if (profit_cagr_3y is not None and price_cagr_3y is not None) else None

        annual_profit_yoy = float(cand['profit_yoy'] or 0)
        cur_profit_yoy = float(snap.get('profit_yoy') or 0)
        pe_ttm = float(snap['pe_ttm']) if snap.get('pe_ttm') is not None else None
        peg = pe_ttm / cur_profit_yoy if (pe_ttm and pe_ttm > 0 and cur_profit_yoy > 0) else None

        # 启动确认信号
        profit_accel = cur_profit_yoy > annual_profit_yoy
        confirm_signals = [
            pm['above_ma250'], pm['golden_cross'],
            pm['volume_breakout'], profit_accel, pm['bottom_lift'],
        ]
        n_confirm = sum(1 for s in confirm_signals if s)

        # 严格度硬性过滤
        if pm['drawdown_3y'] is not None and pm['drawdown_3y'] < conf['drawdown_min']:
            continue
        if pm['position_pct'] is not None and pm['position_pct'] > conf['position_max']:
            continue
        if conf['divergence_min'] is not None and (divergence is None or divergence < conf['divergence_min']):
            continue
        if conf['pe_max'] is not None and (pe_ttm is None or pe_ttm <= 0 or pe_ttm > conf['pe_max']):
            continue
        if require_confirm and n_confirm < 2:
            continue

        score = _score_perf(consecutive_years, annual_profit_yoy, float(cand['roe'] or 0)) \
            + _score_bottom(divergence, pm['drawdown_3y'], pm['amp_3y'], pm['position_pct']) \
            + _score_confirm(pm['above_ma250'], pm['golden_cross'], pm['volume_breakout'],
                             profit_accel, pm['bottom_lift'])

        def pct(v):
            return round(v * 100, 1) if v is not None else None

        results.append({
            'stock_code': code,
            'stock_name': cand.get('stock_name', ''),
            'n_years': consecutive_years,
            'latest_profit': round(latest_profit, 0),
            'profit_cagr_3y': pct(profit_cagr_3y),
            'cur_profit_yoy': round(cur_profit_yoy, 1) if cur_profit_yoy else None,
            'price_cagr_3y': pct(price_cagr_3y),
            'divergence': pct(divergence),
            'drawdown_3y': pct(pm['drawdown_3y']),
            'amp_3y': pct(pm['amp_3y']),
            'amp_1y': pct(pm['amp_1y']),
            'position_pct': pct(pm['position_pct']),
            'pct_250d': pct(pm['pct_250d']),
            'pe_ttm': round(pe_ttm, 1) if pe_ttm else None,
            'peg': round(peg, 2) if peg else None,
            'above_ma250': 1 if pm['above_ma250'] else 0,
            'n_confirm': n_confirm,
            'score': round(score, 1),
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results
