from ..database import query
from datetime import datetime, timedelta

IND_TAGS_DEF = {
    'ind.ma5_above_ma10': {'name': 'MA5 > MA10', 'group': '均线'},
    'ind.ma10_above_ma20': {'name': 'MA10 > MA20', 'group': '均线'},
    'ind.ma20_above_ma60': {'name': 'MA20 > MA60', 'group': '均线'},
    'ind.price_above_ma20': {'name': '站上20日均线', 'group': '均线'},
    'ind.price_above_ma50': {'name': '站上50日均线', 'group': '均线'},
    'ind.price_above_ma150': {'name': '站上150日均线', 'group': '均线'},
    'ind.price_above_ma200': {'name': '站上200日均线', 'group': '均线'},
    'ind.rsi_overbought': {'name': 'RSI超买', 'group': 'RSI'},
    'ind.rsi_oversold': {'name': 'RSI超卖', 'group': 'RSI'},
    'ind.volume_surge': {'name': '放量', 'group': '成交量'},
    'ind.volume_shrink': {'name': '缩量', 'group': '成交量'},
}

BIZ_TAGS_DEF = {
    'biz.boom_growth': {'name': '爆发增长', 'group': '成长性'},
    'biz.high_growth': {'name': '高成长', 'group': '成长性'},
    'biz.steady_growth': {'name': '稳健增长', 'group': '成长性'},
    'biz.revenue_decline': {'name': '营收下滑', 'group': '下滑/衰退'},
    'biz.profit_decline': {'name': '利润下滑', 'group': '下滑/衰退'},
    'biz.double_decline': {'name': '营收利润双降', 'group': '下滑/衰退'},
    'biz.profit_collapse': {'name': '业绩暴雷', 'group': '下滑/衰退'},
    'biz.profit_to_loss': {'name': '由盈转亏', 'group': '下滑/衰退'},
    'biz.growth_slowdown': {'name': '增速大幅放缓', 'group': '下滑/衰退'},
    'biz.financial_healthy': {'name': '财务健康', 'group': '财务健康'},
    'biz.financial_moderate': {'name': '负债适中', 'group': '财务健康'},
    'biz.financial_risky': {'name': '高负债风险', 'group': '财务健康'},
    'biz.financial_critical': {'name': '高杠杆', 'group': '财务健康'},
    'biz.financial_insolvent': {'name': '资不抵债', 'group': '财务健康'},
    'biz.strong_momentum': {'name': '趋势强劲', 'group': '趋势动量'},
    'biz.weak_momentum': {'name': '趋势疲弱', 'group': '趋势动量'},
    'biz.bullish': {'name': '多头排列', 'group': '趋势动量'},
    'biz.bearish': {'name': '空头排列', 'group': '趋势动量'},
    'biz.volume_price_up': {'name': '量价齐升', 'group': '趋势动量'},
    'biz.volume_price_down': {'name': '放量下跌', 'group': '趋势动量'},
    'biz.break_support': {'name': '破位下跌', 'group': '趋势动量'},
    'biz.consecutive_profit_3q': {'name': '连增3季', 'group': '连续增长'},
    'biz.consecutive_profit_5q': {'name': '连增5季', 'group': '连续增长'},
    'biz.consecutive_revenue_3q': {'name': '营收连增3季', 'group': '连续增长'},

    # ── 年度连续增长 ──
    'biz.annual_rev_growth_1y': {'name': '营收连增1年', 'group': '连续增长'},
    'biz.annual_rev_growth_2y': {'name': '营收连增2年', 'group': '连续增长'},
    'biz.annual_rev_growth_3y': {'name': '营收连增3年', 'group': '连续增长'},
    'biz.annual_rev_growth_4y': {'name': '营收连增4年', 'group': '连续增长'},
    'biz.annual_profit_growth_1y': {'name': '净利润连增1年', 'group': '连续增长'},
    'biz.annual_profit_growth_2y': {'name': '净利润连增2年', 'group': '连续增长'},
    'biz.annual_profit_growth_3y': {'name': '净利润连增3年', 'group': '连续增长'},
    'biz.annual_profit_growth_4y': {'name': '净利润连增4年', 'group': '连续增长'},
    'biz.annual_gm_improve_1y': {'name': '毛利率提升1年', 'group': '连续增长'},
    'biz.annual_gm_improve_2y': {'name': '毛利率连升2年', 'group': '连续增长'},
    'biz.annual_gm_improve_3y': {'name': '毛利率连升3年', 'group': '连续增长'},
    'biz.annual_gm_improve_4y': {'name': '毛利率连升4年', 'group': '连续增长'},
}

STAGE_DEF = {
    'stage.s2': {'name': '突围加速期'},
    'stage.s1s2': {'name': '过渡期'},
    'stage.s4': {'name': '衰败下跌期'},
    'stage.s3': {'name': '见顶派发期'},
    'stage.s1': {'name': '打底蓄势期'},
}


def get_stock_name(code):
    r = query('SELECT stock_name FROM stocks WHERE stock_code = %s', [code])
    return r[0]['stock_name'] if r else None


def get_stock_sectors(code):
    rows = query('''
        SELECT ss.sector_code, s.sector_name, s.category, s.category_cn
        FROM stock_sectors ss
        JOIN sectors s ON s.sector_code = ss.sector_code
        WHERE ss.stock_code = %s
        ORDER BY s.category, s.level, ss.sector_code
    ''', [code])
    result = {'industry': [], 'region': [], 'concept': [], 'style': []}
    for r in rows:
        cat = r['category']
        if cat in result:
            result[cat].append({
                'code': r['sector_code'],
                'name': r['sector_name'],
            })
    return result


def get_klines(code, days=300):
    rows = query("""
        SELECT trade_date, open_price, high_price, low_price, close_price, volume
        FROM daily_kline
        WHERE stock_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
    """, [code, days])
    if not rows:
        return []
    rows.reverse()
    return [{
        'date': str(r['trade_date']),
        'open': float(r['open_price']),
        'high': float(r['high_price']),
        'low': float(r['low_price']),
        'close': float(r['close_price']),
        'volume': int(r['volume']),
    } for r in rows]


def calc_growth(cur, prev):
    if cur is None or prev is None or float(prev) == 0:
        return None
    return round((float(cur) - float(prev)) / float(prev) * 100, 2)


def _find_prev_year_gm_growth(quarterly_growth):
    if not quarterly_growth or len(quarterly_growth) < 5:
        return None
    latest_date = quarterly_growth[-1]['date']
    target_month = latest_date[5:7]
    target_year = str(int(latest_date[:4]) - 1)
    for q in reversed(quarterly_growth):
        if q['date'].startswith(target_year) and q['date'][5:7] == target_month:
            return q.get('gross_margin_growth')
    return None


def get_latest_financials(code):
    row = query("""
        SELECT fq.report_date,
               fq.q_revenue, fq.q_parent_net_profit,
               fq2.q_revenue AS prev_revenue,
               fq2.q_parent_net_profit AS prev_profit,
               b.total_assets, b.total_liabilities,
               c.contract_liab
        FROM fin_quarterly fq
        LEFT JOIN fin_quarterly fq2
            ON fq2.stock_code = fq.stock_code
            AND fq2.report_date = DATE_SUB(fq.report_date, INTERVAL 1 YEAR)
        LEFT JOIN fin_balance_sheet b
            ON b.stock_code = fq.stock_code AND b.report_date = fq.report_date
        LEFT JOIN fin_contract_bs c
            ON c.stock_code = fq.stock_code AND c.report_date = fq.report_date
        WHERE fq.stock_code = %s
        ORDER BY fq.report_date DESC
        LIMIT 1
    """, [code])
    if not row:
        return None
    return row[0]


def get_prev_financials(code):
    rows = query("""
        SELECT fq.report_date,
               fq.q_revenue, fq.q_parent_net_profit,
               fq2.q_revenue AS prev_revenue,
               fq2.q_parent_net_profit AS prev_profit
        FROM fin_quarterly fq
        LEFT JOIN fin_quarterly fq2
            ON fq2.stock_code = fq.stock_code
            AND fq2.report_date = DATE_SUB(fq.report_date, INTERVAL 1 YEAR)
        WHERE fq.stock_code = %s
        ORDER BY fq.report_date DESC
        LIMIT 2
    """, [code])
    if len(rows) < 2:
        return None
    return rows[1]


def get_growth_quarters(code, limit=5):
    rows = query("""
        SELECT fq.report_date,
               fq.q_revenue, fq.q_parent_net_profit,
               fq2.q_revenue AS prev_revenue,
               fq2.q_parent_net_profit AS prev_profit
        FROM fin_quarterly fq
        LEFT JOIN fin_quarterly fq2
            ON fq2.stock_code = fq.stock_code
            AND fq2.report_date = DATE_SUB(fq.report_date, INTERVAL 1 YEAR)
        WHERE fq.stock_code = %s
        ORDER BY fq.report_date DESC
        LIMIT %s
    """, [code, limit])
    return rows


def get_annual_financials(code, years=5):
    rows = query("""
        SELECT report_date, operating_revenue, operating_cost,
               net_profit, parent_net_profit
        FROM fin_income
        WHERE stock_code = %s AND MONTH(report_date) = 12 AND DAY(report_date) = 31
        ORDER BY report_date DESC
        LIMIT %s
    """, [code, years])
    return rows


def compute_annual_growth(annual_rows):
    if not annual_rows or len(annual_rows) < 2:
        return {
            'gross_margin_trend': [],
            'annual_revenue_growth': [],
            'annual_profit_growth': [],
            'annual_gm_growth': [],
            'consecutive_revenue_years': 0,
            'consecutive_profit_years': 0,
            'consecutive_gm_years': 0,
        }

    rows = list(reversed(annual_rows))
    gross_margin_trend = []
    rev_growths = []
    profit_growths = []
    gm_improvements = []
    gm_growth_rates = []

    for row in rows:
        rev = float(row['operating_revenue']) if row.get('operating_revenue') else 0
        cost = float(row['operating_cost']) if row.get('operating_cost') else 0
        year = str(row['report_date'])[:4] if row.get('report_date') else ''
        gm_rate = (rev - cost) / rev * 100 if rev > 0 else None
        gross_margin_trend.append({'year': year, 'rate': round(gm_rate, 2) if gm_rate is not None else None})

    for i in range(1, len(rows)):
        prev_rev_val = float(rows[i - 1]['operating_revenue']) if rows[i - 1].get('operating_revenue') else 0
        rev_val = float(rows[i]['operating_revenue']) if rows[i].get('operating_revenue') else 0
        prev_profit_val = float(rows[i - 1]['parent_net_profit']) if rows[i - 1].get('parent_net_profit') else 0
        profit_val = float(rows[i]['parent_net_profit']) if rows[i].get('parent_net_profit') else 0
        cur_gm = gross_margin_trend[i]['rate']
        prev_gm = gross_margin_trend[i - 1]['rate']

        rev_growth = (rev_val - prev_rev_val) / prev_rev_val * 100 if prev_rev_val > 0 else None
        profit_growth = (profit_val - prev_profit_val) / prev_profit_val * 100 if prev_profit_val > 0 else None
        rev_growths.append(rev_growth)
        profit_growths.append(profit_growth)
        gm_improvements.append(cur_gm is not None and prev_gm is not None and cur_gm > prev_gm)
        gm_growth = (cur_gm - prev_gm) / prev_gm * 100 if cur_gm is not None and prev_gm is not None and prev_gm > 0 else None
        gm_growth_rates.append(gm_growth)

    def count_consecutive(values):
        cnt = 0
        for v in reversed(values):
            if v is not None and v > 0:
                cnt += 1
            else:
                break
        return cnt

    annual_rev = [{'year': gross_margin_trend[i + 1]['year'],
                   'rate': round(rev_growths[i], 2) if rev_growths[i] is not None else None}
                  for i in range(len(rev_growths))]
    annual_profit = [{'year': gross_margin_trend[i + 1]['year'],
                      'rate': round(profit_growths[i], 2) if profit_growths[i] is not None else None}
                     for i in range(len(profit_growths))]
    annual_gm_growth = [{'year': gross_margin_trend[i + 1]['year'],
                         'rate': round(gm_growth_rates[i], 2) if gm_growth_rates[i] is not None else None}
                        for i in range(len(gm_growth_rates))]

    return {
        'gross_margin_trend': gross_margin_trend,
        'annual_revenue_growth': annual_rev,
        'annual_profit_growth': annual_profit,
        'annual_gm_growth': annual_gm_growth,
        'consecutive_revenue_years': count_consecutive(rev_growths),
        'consecutive_profit_years': count_consecutive(profit_growths),
        'consecutive_gm_years': count_consecutive(gm_improvements),
    }


def get_rolling_annual_gm(code, max_years=5):
    """基于最新季度往前推4个季度为一年，计算滚动毛利率连升年数"""
    quarters = query("""
        SELECT report_date, operating_revenue, operating_cost
        FROM fin_income
        WHERE stock_code = %s
        ORDER BY report_date DESC
        LIMIT %s
    """, [code, max_years * 4 + 4])
    if not quarters or len(quarters) < 8:
        return 0

    rows = list(reversed(quarters))

    sq_list = []
    for i, r in enumerate(rows):
        rev = float(r['operating_revenue']) if r['operating_revenue'] else 0
        cost = float(r['operating_cost']) if r['operating_cost'] else 0
        if i == 0 or r['report_date'].month == 3:
            sq_rev, sq_cost = rev, cost
        else:
            prev = rows[i - 1]
            prev_rev = float(prev['operating_revenue']) if prev['operating_revenue'] else 0
            prev_cost = float(prev['operating_cost']) if prev['operating_cost'] else 0
            sq_rev = rev - prev_rev
            sq_cost = cost - prev_cost
        sq_list.append({'rev': sq_rev, 'cost': sq_cost, 'date': str(r['report_date'])})

    if len(sq_list) < max_years * 4:
        return 0

    rolling_gm = []
    for y in range(max_years):
        start = -(y + 1) * 4
        end = -y * 4 if y > 0 else None
        chunk = sq_list[start:end]
        total_rev = sum(q['rev'] for q in chunk)
        total_cost = sum(q['cost'] for q in chunk)
        if total_rev > 0:
            gm = (total_rev - total_cost) / total_rev * 100
            rolling_gm.append(gm)
        else:
            rolling_gm.append(None)

    consecutive = 0
    for i in range(len(rolling_gm) - 1):
        if rolling_gm[i] is not None and rolling_gm[i + 1] is not None and rolling_gm[i] > rolling_gm[i + 1]:
            consecutive += 1
        else:
            break

    return consecutive


def _single_quarter_from_fin_income(code, report_dates):
    if not report_dates:
        return {}
    inc_rows = query("""
        SELECT report_date, operating_revenue, operating_cost
        FROM fin_income
        WHERE stock_code = %s AND (report_date = %s """ +
        ''.join(["OR report_date = %s "] * (len(report_dates) - 1)) + """)
        ORDER BY report_date ASC
    """, [code] + [str(d) for d in report_dates])
    if not inc_rows:
        return {}
    result = {}
    for i, r in enumerate(inc_rows):
        d = str(r['report_date'])
        cumul_rev = float(r['operating_revenue']) if r['operating_revenue'] else 0
        cumul_cost = float(r['operating_cost']) if r['operating_cost'] else 0
        if i == 0 or r['report_date'].month == 3:
            sq_rev, sq_cost = cumul_rev, cumul_cost
        else:
            prev = inc_rows[i - 1]
            prev_rev = float(prev['operating_revenue']) if prev['operating_revenue'] else 0
            prev_cost = float(prev['operating_cost']) if prev['operating_cost'] else 0
            sq_rev = cumul_rev - prev_rev
            sq_cost = cumul_cost - prev_cost
        result[d] = {'sq_rev': sq_rev, 'sq_cost': sq_cost}
    return result


def get_quarterly_growth(code, quarters=20):
    rows = query("""
        SELECT fq.report_date,
               fq.q_revenue, fq.q_parent_net_profit,
               fq2.q_revenue AS prev_revenue,
               fq2.q_parent_net_profit AS prev_profit
        FROM fin_quarterly fq
        LEFT JOIN fin_quarterly fq2
            ON fq2.stock_code = fq.stock_code
            AND fq2.report_date = DATE_SUB(fq.report_date, INTERVAL 1 YEAR)
        WHERE fq.stock_code = %s
        ORDER BY fq.report_date DESC
        LIMIT %s
    """, [code, quarters])
    if not rows or len(rows) < 2:
        return []

    rows = list(reversed(rows))
    report_dates = [r['report_date'] for r in rows]
    sq_map = _single_quarter_from_fin_income(code, report_dates)

    prev_report_dates = [d.replace(year=d.year - 1) for d in report_dates]
    prev_sq_map = _single_quarter_from_fin_income(code, prev_report_dates)

    result = []
    for r in rows:
        d = str(r['report_date'])
        rev = float(r['q_revenue']) if r['q_revenue'] else None
        profit = float(r['q_parent_net_profit']) if r['q_parent_net_profit'] else None
        prev_rev = float(r['prev_revenue']) if r['prev_revenue'] else None
        prev_profit = float(r['prev_profit']) if r['prev_profit'] else None
        rev_growth = (rev - prev_rev) / prev_rev * 100 if rev is not None and prev_rev and prev_rev > 0 else None
        profit_growth = (profit - prev_profit) / prev_profit * 100 if profit is not None and prev_profit and prev_profit > 0 else None

        sq = sq_map.get(d)
        gm = None
        if sq and sq['sq_rev'] > 0:
            gm = round((sq['sq_rev'] - sq['sq_cost']) / sq['sq_rev'] * 100, 2)

        prev_d = str(r['report_date'].replace(year=r['report_date'].year - 1))
        prev_sq = prev_sq_map.get(prev_d)
        prev_gm = None
        if prev_sq and prev_sq['sq_rev'] > 0:
            prev_gm = round((prev_sq['sq_rev'] - prev_sq['sq_cost']) / prev_sq['sq_rev'] * 100, 2)

        gm_growth = None
        if gm is not None and prev_gm is not None and prev_gm > 0:
            gm_growth = round((gm - prev_gm) / prev_gm * 100, 2)

        result.append({
            'date': d,
            'revenue': rev,
            'profit': profit,
            'revenue_growth': round(rev_growth, 2) if rev_growth is not None else None,
            'profit_growth': round(profit_growth, 2) if profit_growth is not None else None,
            'gross_margin': gm,
            'gross_margin_growth': gm_growth,
        })
    return result


def compute_ma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def compute_ma_series(prices, period):
    result = []
    for i in range(len(prices)):
        if i + 1 < period:
            result.append(None)
        else:
            result.append(sum(prices[i + 1 - period:i + 1]) / period)
    return result


def compute_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(len(prices) - period, len(prices)):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def compute_indicator_tags(klines, fin):
    closes = [k['close'] for k in klines]
    volumes = [k['volume'] for k in klines]
    n = len(closes)

    ma5 = compute_ma(closes, 5)
    ma10 = compute_ma(closes, 10)
    ma20 = compute_ma(closes, 20)
    ma50 = compute_ma(closes, 50)
    ma60 = compute_ma(closes, 60)
    ma150 = compute_ma(closes, 150)
    ma200 = compute_ma(closes, 200)

    latest_close = closes[-1] if closes else 0

    ind_map = {}
    ind_map['ma5_above_ma10'] = ma5 is not None and ma10 is not None and ma5 > ma10
    ind_map['ma10_above_ma20'] = ma10 is not None and ma20 is not None and ma10 > ma20
    ind_map['ma20_above_ma60'] = ma20 is not None and ma60 is not None and ma20 > ma60
    ind_map['price_above_ma20'] = ma20 is not None and latest_close > ma20
    ind_map['price_above_ma50'] = ma50 is not None and latest_close > ma50
    ind_map['price_above_ma150'] = ma150 is not None and latest_close > ma150
    ind_map['price_above_ma200'] = ma200 is not None and latest_close > ma200

    rsi14 = compute_rsi(closes, 14)
    if rsi14 is not None:
        ind_map['rsi_overbought'] = rsi14 > 70
        ind_map['rsi_oversold'] = rsi14 < 30
    else:
        ind_map['rsi_overbought'] = False
        ind_map['rsi_oversold'] = False

    volume_ma20 = sum(volumes[-20:]) / 20 if n >= 20 else None
    if volume_ma20 and volume_ma20 > 0:
        ind_map['volume_surge'] = volumes[-1] > volume_ma20 * 1.5
        ind_map['volume_shrink'] = volumes[-1] < volume_ma20 * 0.5
    else:
        ind_map['volume_surge'] = False
        ind_map['volume_shrink'] = False

    ind_tags = []
    for tag_id_suffix, val in ind_map.items():
        if val:
            full_id = f'ind.{tag_id_suffix}'
            ind_tags.append({
                'id': full_id,
                'name': IND_TAGS_DEF.get(full_id, {}).get('name', tag_id_suffix),
            })

    ma_values = {
        'ma5': round(ma5, 2) if ma5 else None,
        'ma10': round(ma10, 2) if ma10 else None,
        'ma20': round(ma20, 2) if ma20 else None,
        'ma50': round(ma50, 2) if ma50 else None,
        'ma60': round(ma60, 2) if ma60 else None,
        'ma150': round(ma150, 2) if ma150 else None,
        'ma200': round(ma200, 2) if ma200 else None,
        'rsi14': rsi14,
        'volume_ma20': round(volume_ma20) if volume_ma20 else None,
        'latest_volume': volumes[-1],
    }

    return ind_tags, ma_values, ind_map


def compute_business_tags(ind_map, fin, prev_fin, growth_quarters, klines):
    biz_flags = {}

    def has_ind(suffix):
        return ind_map.get(suffix, False)

    rev_growth = None
    profit_growth = None
    debt = None

    if fin:
        rev_growth = calc_growth(fin.get('q_revenue'), fin.get('prev_revenue'))
        profit_growth = calc_growth(fin.get('q_parent_net_profit'), fin.get('prev_profit'))
        ta = fin.get('total_assets')
        tl = fin.get('total_liabilities')
        if ta is not None and tl is not None and float(ta) > 0:
            debt = round(float(tl) / float(ta) * 100, 2)
        else:
            debt = None

    if rev_growth is not None and profit_growth is not None:
        biz_flags['boom_growth'] = rev_growth > 50 and profit_growth > 50
        biz_flags['high_growth'] = rev_growth > 20 and profit_growth > 20
        biz_flags['steady_growth'] = rev_growth > 0 and profit_growth > 0
        biz_flags['revenue_decline'] = rev_growth < 0
        biz_flags['profit_decline'] = profit_growth < 0
        biz_flags['double_decline'] = rev_growth < 0 and profit_growth < 0
        biz_flags['profit_collapse'] = profit_growth < -50

        if prev_fin:
            prev_profit = calc_growth(prev_fin.get('q_revenue'), prev_fin.get('prev_revenue'))
            prev_rev = calc_growth(prev_fin.get('q_parent_net_profit'), prev_fin.get('prev_profit'))
            if prev_profit is not None and prev_profit > 0 and profit_growth < 0:
                biz_flags['profit_to_loss'] = True
            if prev_rev is not None and prev_rev > 30 and rev_growth < 10:
                biz_flags['growth_slowdown'] = True
        else:
            biz_flags['profit_to_loss'] = False
            biz_flags['growth_slowdown'] = False

    if debt is not None:
        biz_flags['financial_healthy'] = debt < 40 and (profit_growth or 0) > 0
        biz_flags['financial_moderate'] = 40 <= debt <= 60
        biz_flags['financial_risky'] = debt > 60
        biz_flags['financial_critical'] = debt > 80
        biz_flags['financial_insolvent'] = debt > 100

    ma5_above_ma10 = has_ind('ma5_above_ma10')
    ma10_above_ma20 = has_ind('ma10_above_ma20')
    ma20_above_ma60 = has_ind('ma20_above_ma60')
    price_above_ma20 = has_ind('price_above_ma20')
    price_above_ma200 = has_ind('price_above_ma200')
    volume_surge = has_ind('volume_surge')

    biz_flags['strong_momentum'] = price_above_ma200 and ma20_above_ma60
    biz_flags['weak_momentum'] = not price_above_ma200
    biz_flags['bullish'] = ma5_above_ma10 and ma10_above_ma20 and ma20_above_ma60
    biz_flags['bearish'] = not ma5_above_ma10 and not price_above_ma20
    biz_flags['volume_price_up'] = volume_surge and price_above_ma20
    biz_flags['volume_price_down'] = volume_surge and not price_above_ma20

    closes = [k['close'] for k in klines]
    n = len(closes)
    ma60_series = compute_ma_series(closes, 60)
    if n >= 2 and ma60_series[-2] is not None and ma60_series[-1] is not None:
        biz_flags['break_support'] = closes[-2] > ma60_series[-2] and closes[-1] < ma60_series[-1]
    else:
        biz_flags['break_support'] = False

    if growth_quarters and len(growth_quarters) >= 3:
        q_profits = [calc_growth(q.get('q_parent_net_profit'), q.get('prev_profit')) for q in growth_quarters]
        q_profits = [p for p in q_profits if p is not None]
        q_revs = [calc_growth(q.get('q_revenue'), q.get('prev_revenue')) for q in growth_quarters]
        q_revs = [r for r in q_revs if r is not None]
        biz_flags['consecutive_profit_3q'] = len(q_profits) >= 3 and all(p > 0 for p in q_profits[:3])
        biz_flags['consecutive_profit_5q'] = len(q_profits) >= 5 and all(p > 0 for p in q_profits[:5])
        biz_flags['consecutive_revenue_3q'] = len(q_revs) >= 3 and all(r > 0 for r in q_revs[:3])
    else:
        biz_flags['consecutive_profit_3q'] = False
        biz_flags['consecutive_profit_5q'] = False
        biz_flags['consecutive_revenue_3q'] = False

    biz_tags = []
    for tag_id_suffix, val in biz_flags.items():
        if val:
            full_id = f'biz.{tag_id_suffix}'
            biz_tags.append({
                'id': full_id,
                'name': BIZ_TAGS_DEF.get(full_id, {}).get('name', tag_id_suffix),
            })

    return biz_tags


def compute_stage(klines, ma_values, ind_map):
    closes = [k['close'] for k in klines]
    high_prices = [k['high'] for k in klines]
    low_prices = [k['low'] for k in klines]
    n = len(closes)

    latest_close = closes[-1] if closes else 0

    ma50 = ma_values.get('ma50')
    ma150 = ma_values.get('ma150')
    ma200 = ma_values.get('ma200')
    ma200_series = compute_ma_series(closes, 200)

    year_data = klines[-250:] if n >= 250 else klines
    high_52w = max(k['high'] for k in year_data) if year_data else 0
    low_52w = min(k['low'] for k in year_data) if year_data else 0

    # ── S2 Trend Template (all must be true) ──
    s2_criteria = []
    s2_criteria.append(latest_close > (ma150 or 0) and latest_close > (ma200 or 0))
    s2_criteria.append((ma150 or 0) > (ma200 or 0))

    ma200_curr = ma200_series[-1] if len(ma200_series) >= 1 and ma200_series[-1] is not None else None
    ma200_past = ma200_series[-22] if len(ma200_series) >= 22 and ma200_series[-22] is not None else None
    s2_criteria.append(ma200_curr is not None and ma200_past is not None and ma200_curr > ma200_past)

    s2_criteria.append(latest_close > (ma50 or 0))
    s2_criteria.append((ma50 or 0) > (ma150 or 0) and (ma50 or 0) > (ma200 or 0))
    s2_criteria.append(low_52w > 0 and latest_close >= low_52w * 1.3)
    s2_criteria.append(high_52w > 0 and latest_close >= high_52w * 0.75)

    s2_met = sum(1 for c in s2_criteria if c)
    s2_all_met = s2_met == 7

    # ── S1S2 ──
    s1s2_criteria = []
    s1s2_criteria.append(latest_close > (ma150 or 0) and latest_close > (ma200 or 0))
    s1s2_criteria.append((ma150 or 0) > (ma200 or 0))
    s1s2_criteria.append(ma200_curr is not None and ma200_past is not None and ma200_curr > ma200_past)

    if n >= 100:
        recent_high = max(closes[-50:])
        prev_high = max(closes[-100:-50])
        recent_low = min(closes[-50:])
        prev_low = min(closes[-100:-50])
        s1s2_criteria.append(recent_high > prev_high)
        s1s2_criteria.append(recent_low > prev_low)
    else:
        s1s2_criteria.append(False)
        s1s2_criteria.append(False)

    s1s2_met = sum(1 for c in s1s2_criteria if c)
    s1s2_all_met = s1s2_met == len(s1s2_criteria)

    # ── S4 ──
    s4_below_ma200_pct = 0
    if len(ma200_series) >= 50:
        below = sum(1 for i in range(-50, 0) if ma200_series[i] is not None and closes[i] < ma200_series[i])
        s4_below_ma200_pct = below / 50
    s4_criteria = []
    s4_criteria.append(s4_below_ma200_pct >= 0.6)
    s4_criteria.append(ma200_curr is not None and ma200_past is not None and ma200_curr < ma200_past)
    s4_criteria.append(low_52w > 0 and latest_close < low_52w * 1.1)
    s4_any = any(s4_criteria)

    # ── S3 ──
    if n >= 51:
        recent_volatility = sum(abs(closes[i] - closes[i - 1]) / closes[i - 1]
                                for i in range(-20, 0) if closes[i - 1] > 0) / 20
        past_volatility = sum(abs(closes[i] - closes[i - 1]) / closes[i - 1]
                              for i in range(-50, -20) if closes[i - 1] > 0) / 30
        s3_volatile = past_volatility > 0 and recent_volatility > past_volatility * 1.5

        ma200_flat = True
        if ma200_curr is not None and ma200_past is not None:
            change_pct = abs(ma200_curr - ma200_past) / ma200_past
            ma200_flat = change_pct < 0.02
    else:
        s3_volatile = False
        ma200_flat = False

    # ── Determine stage (priority: S2 → S1S2 → S4 → S3 → S1) ──
    if s2_all_met:
        stage_id = 'stage.s2'
        confidence = min(95, int(s2_met / 7 * 100) + 10)
    elif s1s2_all_met:
        stage_id = 'stage.s1s2'
        confidence = int(s1s2_met / len(s1s2_criteria) * 100)
    elif s4_any:
        stage_id = 'stage.s4'
        confidence = 75
    elif s3_volatile or ma200_flat:
        stage_id = 'stage.s3'
        confidence = 60
    else:
        stage_id = 'stage.s1'
        confidence = 50

    stage_def = STAGE_DEF.get(stage_id, {})
    return {
        'id': stage_id,
        'name': stage_def.get('name', ''),
        'confidence': confidence,
    }


def compute_scores(biz_tags, stage):
    tech_score = 50
    has_bullish = any(t['id'] == 'biz.bullish' for t in biz_tags)
    has_strong_momentum = any(t['id'] == 'biz.strong_momentum' for t in biz_tags)
    has_volume_price_up = any(t['id'] == 'biz.volume_price_up' for t in biz_tags)

    if has_bullish:
        tech_score += 20
    if has_strong_momentum:
        tech_score += 15
    if has_volume_price_up:
        tech_score += 10

    has_bearish = any(t['id'] == 'biz.bearish' for t in biz_tags)
    has_weak_momentum = any(t['id'] == 'biz.weak_momentum' for t in biz_tags)
    has_break_support = any(t['id'] == 'biz.break_support' for t in biz_tags)

    if has_bearish:
        tech_score -= 20
    if has_weak_momentum:
        tech_score -= 15
    if has_break_support:
        tech_score -= 10

    stage_id = stage['id']
    if stage_id == 'stage.s2':
        tech_score += 15
    elif stage_id == 'stage.s4':
        tech_score -= 20

    fund_score = 50
    has_high_growth = any(t['id'] == 'biz.high_growth' for t in biz_tags)
    has_financial_healthy = any(t['id'] == 'biz.financial_healthy' for t in biz_tags)

    if has_high_growth:
        fund_score += 20
    if any(t['id'] == 'biz.boom_growth' for t in biz_tags):
        fund_score += 15
    if has_financial_healthy:
        fund_score += 15

    if any(t['id'] == 'biz.double_decline' for t in biz_tags):
        fund_score -= 25
    if any(t['id'] == 'biz.profit_collapse' for t in biz_tags):
        fund_score -= 20
    if any(t['id'] == 'biz.financial_risky' for t in biz_tags):
        fund_score -= 10
    if any(t['id'] == 'biz.financial_insolvent' for t in biz_tags):
        fund_score -= 20

    tech_score = max(0, min(100, tech_score))
    fund_score = max(0, min(100, fund_score))

    return {'tech': tech_score, 'fund': fund_score}


def generate_profile(stock_code):
    name = get_stock_name(stock_code)
    if not name:
        return {'error': f'股票代码 {stock_code} 不存在'}

    sectors = get_stock_sectors(stock_code)

    klines = get_klines(stock_code)
    if not klines:
        return {'error': f'股票 {stock_code} 无K线数据'}

    fin = get_latest_financials(stock_code)
    prev_fin = get_prev_financials(stock_code)
    growth_quarters = get_growth_quarters(stock_code)
    annual_rows = get_annual_financials(stock_code)
    annual_growth = compute_annual_growth(annual_rows)
    quarterly_growth = get_quarterly_growth(stock_code)

    ind_tags, ma_values, ind_map = compute_indicator_tags(klines, fin)

    biz_tags = compute_business_tags(ind_map, fin, prev_fin, growth_quarters, klines)

    if annual_growth['consecutive_revenue_years'] >= 1:
        for n in range(1, min(annual_growth['consecutive_revenue_years'], 4) + 1):
            biz_tags.append({'id': f'biz.annual_rev_growth_{n}y', 'name': BIZ_TAGS_DEF[f'biz.annual_rev_growth_{n}y']['name']})
    if annual_growth['consecutive_profit_years'] >= 1:
        for n in range(1, min(annual_growth['consecutive_profit_years'], 4) + 1):
            biz_tags.append({'id': f'biz.annual_profit_growth_{n}y', 'name': BIZ_TAGS_DEF[f'biz.annual_profit_growth_{n}y']['name']})

    consecutive_gm = get_rolling_annual_gm(stock_code)
    if consecutive_gm >= 1:
        for n in range(1, min(consecutive_gm, 4) + 1):
            biz_tags.append({'id': f'biz.annual_gm_improve_{n}y', 'name': BIZ_TAGS_DEF[f'biz.annual_gm_improve_{n}y']['name']})

    stage = compute_stage(klines, ma_values, ind_map)

    scores = compute_scores(biz_tags, stage)

    latest = klines[-1]
    latest_price = latest['close']

    fin_data = {}
    if fin:
        rev_growth = calc_growth(fin.get('q_revenue'), fin.get('prev_revenue'))
        profit_growth = calc_growth(fin.get('q_parent_net_profit'), fin.get('prev_profit'))
        ta = fin.get('total_assets')
        tl = fin.get('total_liabilities')
        debt_ratio = round(float(tl) / float(ta) * 100, 2) if ta is not None and tl is not None and float(ta) > 0 else None
        cl = fin.get('contract_liab')
        contract_liab_to_assets = round(float(cl) / float(ta) * 100, 2) if cl is not None and ta is not None and float(ta) > 0 else None
        fin_data = {
            'revenue_growth_rate': rev_growth,
            'net_profit_growth_rate': profit_growth,
            'debt_ratio': debt_ratio,
            'contract_liab_to_assets': contract_liab_to_assets,
            'contract_liab_raw': float(cl) if cl is not None else None,
            'q_revenue': float(fin['q_revenue']) if fin.get('q_revenue') is not None else None,
            'q_parent_net_profit': float(fin['q_parent_net_profit']) if fin.get('q_parent_net_profit') is not None else None,
            'report_date': str(fin['report_date']) if fin.get('report_date') else None,
        }

    price_change = round((latest_price - klines[-2]['close']) / klines[-2]['close'] * 100, 2) if len(klines) >= 2 else 0

    return {
        'code': stock_code,
        'name': name,
        'date': latest['date'],
        'latest_price': latest_price,
        'price_change_pct': price_change,
        'volume': latest['volume'],
        'sectors': sectors,
        'stage': stage,
        'biz_tags': biz_tags,
        'ind_tags': ind_tags,
        'scores': scores,
        'ma_values': ma_values,
        'fin_data': fin_data,
        'annual_data': {
            'gross_margin_trend': annual_growth['gross_margin_trend'],
            'revenue_growth': annual_growth['annual_revenue_growth'],
            'profit_growth': annual_growth['annual_profit_growth'],
            'gm_growth': annual_growth['annual_gm_growth'],
        },
        'gross_margin_growth_q': quarterly_growth[-1]['gross_margin_growth'] if quarterly_growth and len(quarterly_growth) > 0 else None,
        'gm_growth_prev_yr': _find_prev_year_gm_growth(quarterly_growth),
        'quarterly_growth': quarterly_growth,
    }
