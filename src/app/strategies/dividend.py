from datetime import date, timedelta

from ..database import query

PROGRESS_DONE = '实施分配'
PROGRESS_PLAN = ('预披露', '董事会预案', '股东大会通过')


def get_dividend_summary(stock_code, latest_price=None):
    """从 stock_dividend 表汇总分红信息，供画像展示与筛选。无数据返回 None。"""
    rows = query("""
        SELECT report_date, assign_progress, plan_profile, cash_per_10,
               bonus_per_share, total_cash, send_ratio, trans_ratio,
               dividend_yield, payout_ratio, eps,
               plan_notice_date, equity_record_date, ex_dividend_date,
               notice_date, is_mid_year
        FROM stock_dividend
        WHERE stock_code = %s
        ORDER BY report_date DESC
    """, [stock_code])
    if not rows:
        return None

    done = [r for r in rows if r['assign_progress'] == PROGRESS_DONE]
    plans = [r for r in rows if r['assign_progress'] in PROGRESS_PLAN]

    today = date.today()
    this_year = today.year

    def cash_per_share(r):
        return float(r['cash_per_10']) / 10 if r['cash_per_10'] is not None else None

    this_year_cash = 0.0
    ttm_cash = 0.0
    for r in done:
        ex = r['ex_dividend_date']
        if not ex:
            continue
        cps = cash_per_share(r)
        if cps is None:
            continue
        if ex.year == this_year:
            this_year_cash += cps
        if today - ex <= timedelta(days=365):
            ttm_cash += cps

    latest = done[0] if done else (plans[0] if plans else rows[0])
    latest_cash = cash_per_share(latest)

    yield_pct = None
    if latest_price and ttm_cash > 0:
        yield_pct = round(ttm_cash / float(latest_price) * 100, 2)

    def to_out(r):
        return {
            'report_date': str(r['report_date']),
            'assign_progress': r['assign_progress'],
            'plan_profile': r['plan_profile'],
            'cash_per_10': float(r['cash_per_10']) if r['cash_per_10'] is not None else None,
            'bonus_per_share': cash_per_share(r),
            'dividend_yield': float(r['dividend_yield']) * 100 if r['dividend_yield'] is not None else None,
            'payout_ratio': float(r['payout_ratio']) if r['payout_ratio'] is not None else None,
            'ex_dividend_date': str(r['ex_dividend_date']) if r['ex_dividend_date'] else None,
            'equity_record_date': str(r['equity_record_date']) if r['equity_record_date'] else None,
            'notice_date': str(r['notice_date']) if r['notice_date'] else None,
            'is_mid_year': bool(r['is_mid_year']),
        }

    history = [to_out(r) for r in done]
    trend = _build_trend(done)
    consecutive_years = _consecutive_years(done)

    return {
        'this_year_cash_per_share': round(this_year_cash, 4) if this_year_cash else None,
        'ttm_cash_per_share': round(ttm_cash, 4) if ttm_cash else None,
        'yield_pct': yield_pct,
        'latest': to_out(latest) if done else None,
        'plan': to_out(plans[0]) if plans else None,
        'history': history,
        'trend': trend,
        'consecutive_years': consecutive_years,
    }


def _build_trend(done):
    """按除息日归属自然年，聚合历年每股派息合计、平均股息率、平均派息率、分红次数。"""
    years = {}
    for r in done:
        ex = r['ex_dividend_date']
        if not ex:
            continue
        cps = float(r['cash_per_10']) / 10 if r['cash_per_10'] is not None else None
        yld = float(r['dividend_yield']) * 100 if r['dividend_yield'] is not None else None
        pr = float(r['payout_ratio']) if r['payout_ratio'] is not None else None
        y = ex.year
        item = years.setdefault(y, {'cash': 0.0, 'yields': [], 'payouts': [], 'times': 0})
        if cps is not None:
            item['cash'] += cps
        if yld is not None:
            item['yields'].append(yld)
        if pr is not None:
            item['payouts'].append(pr)
        item['times'] += 1
    return [{
        'year': y,
        'cash_per_share': round(v['cash'], 4),
        'dividend_yield': round(sum(v['yields']) / len(v['yields']), 2) if v['yields'] else None,
        'payout_ratio': round(sum(v['payouts']) / len(v['payouts']), 1) if v['payouts'] else None,
        'times': v['times'],
    } for y, v in sorted(years.items())]


def _consecutive_years(done):
    """最近连续每年都有分红的年数（按除息日归属年份）。"""
    years = set()
    for r in done:
        ex = r['ex_dividend_date']
        if ex:
            years.add(ex.year)
    if not years:
        return 0
    count = 0
    y = date.today().year
    while y in years:
        count += 1
        y -= 1
    return count
