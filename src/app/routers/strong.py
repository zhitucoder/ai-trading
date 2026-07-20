from fastapi import APIRouter, Query
from ..database import query
from datetime import date, timedelta
import json

router = APIRouter()

INDEX_NAMES = {
    '000001': '上证综指', '000016': '上证50', '000300': '沪深300',
    '000905': '中证500', '000852': '中证1000',
}

SECTOR_COLORS = [
    '#26a69a', '#ef5350', '#42a5f5', '#ffa726', '#ab47bc',
    '#5c6bc0', '#66bb6a', '#ec407a', '#8d6e63', '#78909c',
]


def _prosperity_map():
    """Read pre-computed prosperity from sector_prosperity table. Returns dict sector_code -> {level, score}."""
    rows = query("SELECT sector_code, level, score FROM sector_prosperity")
    return {r['sector_code']: {'level': r['level'], 'score': float(r['score'] or 0)} for r in rows}


def _get_trade_dates():
    row = query("SELECT MAX(trade_date) AS d FROM index_kline")
    latest = row[0]['d'] if row else date.today()
    row30 = query(
        "SELECT MAX(trade_date) AS d FROM index_kline WHERE trade_date <= DATE_SUB(%s, INTERVAL 30 DAY)",
        [latest])
    d30 = row30[0]['d'] if row30 and row30[0]['d'] else latest

    year = latest.year
    row_ye = query(
        "SELECT MAX(trade_date) AS d FROM index_kline WHERE trade_date < %s",
        [f'{year}-01-01'])
    dye = row_ye[0]['d'] if row_ye and row_ye[0]['d'] else d30

    row_prev_ye = query(
        "SELECT MAX(trade_date) AS d FROM index_kline WHERE trade_date < %s",
        [f'{year-1}-01-01'])
    dye_prev = row_prev_ye[0]['d'] if row_prev_ye and row_prev_ye[0]['d'] else dye

    return latest, d30, dye, dye_prev


def _get_index_close(index_code, trade_date):
    r = query("SELECT close_price FROM index_kline WHERE index_code=%s AND trade_date=%s",
              [index_code, trade_date])
    return float(r[0]['close_price']) if r else None


def _calc_change(latest_close, prev_close):
    if latest_close and prev_close and prev_close > 0:
        return round((latest_close / prev_close - 1) * 100, 2)
    return None


@router.get('/strong/sectors')
def sector_strength(
    category: str = Query('all'),
    sort_by: str = Query('relative_ytd'),
    sort_order: str = Query('desc'),
    prosperity: str = Query('all'),
    level: str = Query('all'),
    fin_quarter: str = Query('annual'),
):
    latest, d30, dye, dye_prev = _get_trade_dates()

    # 前一交易日
    row_prev = query("SELECT MAX(trade_date) AS d FROM sector_kline WHERE trade_date < %s", [latest])
    d_prev = row_prev[0]['d'] if row_prev and row_prev[0]['d'] else latest

    idx_latest = _get_index_close('000001', latest)
    idx_prev = _get_index_close('000001', d_prev)
    idx_30 = _get_index_close('000001', d30)
    idx_ye = _get_index_close('000001', dye)
    idx_ye_prev = _get_index_close('000001', dye_prev)

    idx_today = _calc_change(idx_latest, idx_prev) if idx_latest and idx_prev else None
    idx_m30 = _calc_change(idx_latest, idx_30) if idx_latest and idx_30 else None
    idx_ytd = _calc_change(idx_latest, idx_ye) if idx_latest and idx_ye else None

    cat_filter = ''
    if category in ('industry', 'concept'):
        cat_filter = f"AND s.category = '{category}'"

    level_filter = ''
    if category == 'industry' and level == '1':
        level_filter = 'AND s.level = 0'
    elif category == 'industry' and level == '2':
        level_filter = 'AND s.level = 1'

    sql = f"""
    SELECT s.sector_code, s.sector_name, s.category, s.category_cn,
           sk_l.close_price AS latest_close,
           sk_l.trade_date AS latest_date,
           sk_prev.close_price AS close_prev,
           sk_30.close_price AS close_30,
           sk_ye.close_price AS close_ye
    FROM sectors s
    JOIN sector_kline sk_l ON s.sector_code = sk_l.sector_code
        AND sk_l.trade_date = (
            SELECT MAX(trade_date) FROM sector_kline WHERE sector_code = s.sector_code
        )
    LEFT JOIN sector_kline sk_prev ON s.sector_code = sk_prev.sector_code
        AND sk_prev.trade_date = (
            SELECT MAX(trade_date) FROM sector_kline
            WHERE sector_code = s.sector_code AND trade_date < %s
        )
    LEFT JOIN sector_kline sk_30 ON s.sector_code = sk_30.sector_code
        AND sk_30.trade_date = (
            SELECT MAX(trade_date) FROM sector_kline
            WHERE sector_code = s.sector_code AND trade_date <= %s
        )
    LEFT JOIN sector_kline sk_ye ON s.sector_code = sk_ye.sector_code
        AND sk_ye.trade_date = (
            SELECT MAX(trade_date) FROM sector_kline
            WHERE sector_code = s.sector_code AND trade_date <= %s
        )
    WHERE s.category IN ('industry', 'concept') {cat_filter} {level_filter}
    """
    rows = query(sql, [latest, d30, dye])

    prosp_map = _prosperity_map()

    sectors = []
    for r in rows:
        lc = float(r['latest_close']) if r['latest_close'] else None
        cp = float(r['close_prev']) if r['close_prev'] else None
        c30 = float(r['close_30']) if r['close_30'] else None
        cye = float(r['close_ye']) if r['close_ye'] else None

        today_val = _calc_change(lc, cp) if lc and cp else None
        m30_val = _calc_change(lc, c30) if lc and c30 else None
        ytd_val = _calc_change(lc, cye) if lc and cye else None

        rel_today = round(today_val - idx_today, 2) if today_val is not None and idx_today is not None else None
        rel_m30 = round(m30_val - idx_m30, 2) if m30_val is not None and idx_m30 is not None else None
        rel_ytd = round(ytd_val - idx_ytd, 2) if ytd_val is not None and idx_ytd is not None else None

        p = prosp_map.get(r['sector_code'], {'level': 'medium', 'score': 0})
        sectors.append({
            'sector_code': r['sector_code'],
            'sector_name': r['sector_name'],
            'category': r['category'],
            'category_cn': r['category_cn'],
            'latest_close': lc,
            'today': today_val,
            'm30': m30_val,
            'ytd': ytd_val,
            'relative_today': rel_today,
            'relative_m30': rel_m30,
            'relative_ytd': rel_ytd,
            'prosperity': p['level'],
            'prosperity_score': p['score'],
        })

    if prosperity in ('high', 'medium', 'low'):
        sectors = [s for s in sectors if s['prosperity'] == prosperity]

    if category in ('industry', 'concept'):
        fin_rows = query(
            "SELECT sector_code, report_date, total_revenue, total_net_profit, revenue_growth, net_profit_growth "
            "FROM ads_sector_finance")

        fin_by_sector = {}
        for r in fin_rows:
            sc = r['sector_code']
            if sc not in fin_by_sector:
                fin_by_sector[sc] = []
            fin_by_sector[sc].append(r)

        month_map = {'q1': 3, 'q2': 6, 'q3': 9}

        def compute_fin(sector_code):
            data = fin_by_sector.get(sector_code, [])
            if not data:
                return {}
            data.sort(key=lambda x: x['report_date'])

            if fin_quarter == 'annual':
                years = {}
                for d in data:
                    yr = str(d['report_date'].year)
                    if yr not in years:
                        years[yr] = []
                    years[yr].append(d)
                sorted_years = sorted(years.keys())
                target_year = sorted_years[-1]
                if len(years[target_year]) < 4 and len(sorted_years) > 1:
                    target_year = sorted_years[-2]
                yd = years[target_year]
                total_rev = sum(float(d['total_revenue']) for d in yd)
                total_profit = sum(float(d['total_net_profit']) for d in yd)
                prev_year = str(int(target_year) - 1)
                if prev_year in years:
                    pd = years[prev_year]
                    prev_rev = sum(float(d['total_revenue']) for d in pd)
                    prev_profit = sum(float(d['total_net_profit']) for d in pd)
                    rev_growth = round((total_rev - prev_rev) / prev_rev * 100, 2) if prev_rev > 0 else None
                    profit_growth = round((total_profit - prev_profit) / prev_profit * 100, 2) if prev_profit > 0 else None
                else:
                    rev_growth = None
                    profit_growth = None
                return {
                    'total_revenue': round(total_rev, 2),
                    'total_net_profit': round(total_profit, 2),
                    'revenue_growth': rev_growth,
                    'net_profit_growth': profit_growth,
                }
            else:
                m = month_map.get(fin_quarter)
                if not m:
                    return {}
                qdata = [d for d in data if d['report_date'].month == m]
                if not qdata:
                    return {}
                latest_q = qdata[-1]
                return {
                    'total_revenue': float(latest_q['total_revenue']),
                    'total_net_profit': float(latest_q['total_net_profit']),
                    'revenue_growth': float(latest_q['revenue_growth']) if latest_q['revenue_growth'] is not None else None,
                    'net_profit_growth': float(latest_q['net_profit_growth']) if latest_q['net_profit_growth'] is not None else None,
                }

        for s in sectors:
            fin = compute_fin(s['sector_code'])
            s.update(fin)

    sort_key = sort_by
    reverse = sort_order == 'desc'
    sectors.sort(key=lambda x: (x.get(sort_key) or -9999), reverse=reverse)

    return {
        'index': {
            'code': '000001', 'name': '上证综指',
            'today': idx_today, 'm30': idx_m30, 'ytd': idx_ytd,
        },
        'sectors': sectors,
        'dates': {'latest': str(latest), 'd30': str(d30), 'dye': str(dye)},
    }


@router.get('/strong/index-kline')
def index_kline(
    codes: str = Query('000001'),
    days: int = Query(120),
):
    code_list = [c.strip() for c in codes.split(',') if c.strip()][:5]
    series = []
    for code in code_list:
        name = INDEX_NAMES.get(code)
        if not name:
            r = query("SELECT sector_name FROM sectors WHERE sector_code=%s", [code])
            name = r[0]['sector_name'] if r else code

        is_index = code in INDEX_NAMES
        if is_index:
            rows = query(
                "SELECT trade_date, open_price, high_price, low_price, close_price, volume "
                "FROM index_kline WHERE index_code=%s ORDER BY trade_date DESC LIMIT %s",
                [code, days])
        else:
            rows = list(query(
                "SELECT trade_date, open_price, high_price, low_price, close_price, volume "
                "FROM sector_kline WHERE sector_code=%s ORDER BY trade_date DESC LIMIT %s",
                [code, days]))
        rows.reverse()
        series.append({
            'code': code,
            'name': name,
            'type': 'index' if is_index else 'sector',
            'data': [{
                'date': str(r['trade_date']),
                'open': float(r['open_price']),
                'high': float(r['high_price']),
                'low': float(r['low_price']),
                'close': float(r['close_price']),
                'volume': int(r['volume']),
            } for r in rows],
        })
    return {'series': series}


@router.get('/strong/sector-stocks')
def sector_stocks(
    sector_code: str = Query(...),
    sort_by: str = Query('relative_ytd'),
    sort_order: str = Query('desc'),
):
    latest, d30, dye, dye_prev = _get_trade_dates()

    idx_latest = _get_index_close('000001', latest)
    idx_30 = _get_index_close('000001', d30)
    idx_ye = _get_index_close('000001', dye)

    idx_today = _calc_change(idx_latest, idx_30) if idx_latest and idx_30 else None
    idx_m30 = _calc_change(idx_latest, idx_30) if idx_latest and idx_30 else None
    idx_ytd = _calc_change(idx_latest, idx_ye) if idx_latest and idx_ye else None

    sr = query("SELECT sector_name, category_cn FROM sectors WHERE sector_code=%s", [sector_code])
    sector_info = sr[0] if sr else {}

    sk_row = query(
        "SELECT close_price FROM sector_kline WHERE sector_code=%s AND trade_date=%s",
        [sector_code, latest])
    sector_close = float(sk_row[0]['close_price']) if sk_row else None
    sk_30 = query(
        "SELECT close_price FROM sector_kline WHERE sector_code=%s AND trade_date=%s",
        [sector_code, d30])
    sector_close_30 = float(sk_30[0]['close_price']) if sk_30 else None
    sk_ye = query(
        "SELECT close_price FROM sector_kline WHERE sector_code=%s AND trade_date=%s",
        [sector_code, dye])
    sector_close_ye = float(sk_ye[0]['close_price']) if sk_ye else None

    sector_today = _calc_change(sector_close, sector_close_30)
    sector_m30 = _calc_change(sector_close, sector_close_30)
    sector_ytd = _calc_change(sector_close, sector_close_ye)

    sql = """
    SELECT st.stock_code, st.stock_name,
           dk_l.close_price AS latest_close, dk_l.trade_date AS latest_date,
           dk_prev.close_price AS close_prev,
           dk_30.close_price AS close_30,
           dk_ye.close_price AS close_ye
    FROM stock_sectors ss
    JOIN stocks st ON ss.stock_code = st.stock_code
    JOIN daily_kline dk_l ON st.stock_code = dk_l.stock_code
        AND dk_l.trade_date = (
            SELECT MAX(trade_date) FROM daily_kline WHERE stock_code = st.stock_code
        )
    LEFT JOIN daily_kline dk_prev ON st.stock_code = dk_prev.stock_code
        AND dk_prev.trade_date = (
            SELECT MAX(trade_date) FROM daily_kline
            WHERE stock_code = st.stock_code AND trade_date < dk_l.trade_date
        )
    LEFT JOIN daily_kline dk_30 ON st.stock_code = dk_30.stock_code
        AND dk_30.trade_date = (
            SELECT MAX(trade_date) FROM daily_kline
            WHERE stock_code = st.stock_code AND trade_date <= %s
        )
    LEFT JOIN daily_kline dk_ye ON st.stock_code = dk_ye.stock_code
        AND dk_ye.trade_date = (
            SELECT MAX(trade_date) FROM daily_kline
            WHERE stock_code = st.stock_code AND trade_date <= %s
        )
    WHERE ss.sector_code = %s
    """
    rows = query(sql, [d30, dye, sector_code])

    stocks = []
    for r in rows:
        lc = float(r['latest_close']) if r['latest_close'] else None
        cprev = float(r['close_prev']) if r['close_prev'] else None
        c30 = float(r['close_30']) if r['close_30'] else None
        cye = float(r['close_ye']) if r['close_ye'] else None

        today_val = _calc_change(lc, cprev) if lc and cprev else None
        m30_val = _calc_change(lc, c30) if lc and c30 else None
        ytd_val = _calc_change(lc, cye) if lc and cye else None

        stocks.append({
            'stock_code': r['stock_code'],
            'stock_name': r['stock_name'],
            'latest_price': lc,
            'today': today_val,
            'm30': m30_val,
            'ytd': ytd_val,
            'relative_today': round(today_val - idx_today, 2) if today_val is not None and idx_today is not None else None,
            'relative_m30': round(m30_val - idx_m30, 2) if m30_val is not None and idx_m30 is not None else None,
            'relative_ytd': round(ytd_val - idx_ytd, 2) if ytd_val is not None and idx_ytd is not None else None,
            'sector_relative_today': round(today_val - sector_today, 2) if today_val is not None and sector_today is not None else None,
            'sector_relative_m30': round(m30_val - sector_m30, 2) if m30_val is not None and sector_m30 is not None else None,
            'sector_relative_ytd': round(ytd_val - sector_ytd, 2) if ytd_val is not None and sector_ytd is not None else None,
        })

    sort_key = sort_by
    reverse = sort_order == 'desc'
    stocks.sort(key=lambda x: (x.get(sort_key) or -9999), reverse=reverse)

    return {
        'sector': {
            'code': sector_code,
            'name': sector_info.get('sector_name', ''),
            'category_cn': sector_info.get('category_cn', ''),
            'today': sector_today, 'm30': sector_m30, 'ytd': sector_ytd,
        },
        'index_ref': {
            'code': '000001', 'name': '上证综指',
            'today': idx_today, 'm30': idx_m30, 'ytd': idx_ytd,
        },
        'stocks': stocks,
    }


@router.get('/strong/stock-kline')
def stock_kline(
    sector_code: str = Query(...),
    stock_codes: str = Query(''),
    days: int = Query(120),
):
    latest, d30, dye, dye_prev = _get_trade_dates()

    code_list = [c.strip() for c in stock_codes.split(',') if c.strip()][:5] if stock_codes else []

    if not code_list:
        sr = query(
            "SELECT st.stock_code, dk_l.close_price / dk_ye.close_price AS perf "
            "FROM stock_sectors ss "
            "JOIN stocks st ON ss.stock_code = st.stock_code "
            "JOIN daily_kline dk_l ON st.stock_code = dk_l.stock_code AND dk_l.trade_date = %s "
            "LEFT JOIN daily_kline dk_ye ON st.stock_code = dk_ye.stock_code AND dk_ye.trade_date = %s "
            "WHERE ss.sector_code = %s "
            "ORDER BY perf DESC LIMIT 3",
            [latest, dye, sector_code])
        code_list = [r['stock_code'] for r in sr]

    series = []

    sr = query("SELECT sector_name FROM sectors WHERE sector_code=%s", [sector_code])
    sector_name = sr[0]['sector_name'] if sr else sector_code
    sk_rows = list(query(
        "SELECT trade_date, open_price, high_price, low_price, close_price, volume "
        "FROM sector_kline WHERE sector_code=%s ORDER BY trade_date DESC LIMIT %s",
        [sector_code, days]))
    sk_rows.reverse()
    series.append({
        'code': sector_code, 'name': sector_name, 'type': 'sector',
        'data': [{
            'date': str(r['trade_date']),
            'open': float(r['open_price']), 'high': float(r['high_price']),
            'low': float(r['low_price']), 'close': float(r['close_price']),
            'volume': int(r['volume']),
        } for r in sk_rows],
    })

    for sc in code_list:
        r_name = query("SELECT stock_name FROM stocks WHERE stock_code=%s", [sc])
        name = r_name[0]['stock_name'] if r_name else sc
        rows = list(query(
            "SELECT trade_date, open_price, high_price, low_price, close_price, volume "
            "FROM daily_kline WHERE stock_code=%s ORDER BY trade_date DESC LIMIT %s",
            [sc, days]))
        rows.reverse()
        series.append({
            'code': sc, 'name': name, 'type': 'stock',
            'data': [{
                'date': str(r['trade_date']),
                'open': float(r['open_price']), 'high': float(r['high_price']),
                'low': float(r['low_price']), 'close': float(r['close_price']),
                'volume': int(r['volume']),
            } for r in rows],
        })

    return {'series': series}


@router.get('/strong/top-stocks')
def top_stocks(
    category: str = Query('all'),
    sort_by: str = Query('relative_ytd'),
    top_n: int = Query(3),
):
    latest, d30, dye, dye_prev = _get_trade_dates()

    idx_latest = _get_index_close('000001', latest)
    idx_ye = _get_index_close('000001', dye)
    idx_ytd = _calc_change(idx_latest, idx_ye)

    cat_filter = ''
    if category in ('industry', 'concept'):
        cat_filter = f"AND s.category = '{category}'"

    sector_sql = f"""
    SELECT s.sector_code, s.sector_name,
           sl.close_price AS latest_close,
           sly.close_price AS close_ye
    FROM sectors s
    JOIN sector_kline sl ON sl.sector_code = s.sector_code
        AND sl.trade_date = (
            SELECT MAX(trade_date) FROM sector_kline WHERE sector_code = s.sector_code)
    LEFT JOIN sector_kline sly ON sly.sector_code = s.sector_code
        AND sly.trade_date = (
            SELECT MAX(trade_date) FROM sector_kline
            WHERE sector_code = s.sector_code AND trade_date <= %s)
    WHERE s.category IN ('industry', 'concept') {cat_filter}
    """
    sector_rows = query(sector_sql, [dye])
    sector_codes = [r['sector_code'] for r in sector_rows]
    if not sector_codes:
        return {'sectors': [], 'idx_ytd': idx_ytd}

    placeholders = ','.join(['%s'] * len(sector_codes))
    stock_sql = f"""
    SELECT ss.sector_code, st.stock_code, st.stock_name,
           dk_l.close_price AS latest_close,
           dk_ye.close_price AS close_ye
    FROM stock_sectors ss
    JOIN stocks st ON ss.stock_code = st.stock_code
    JOIN daily_kline dk_l ON dk_l.stock_code = st.stock_code
        AND dk_l.trade_date = (
            SELECT MAX(trade_date) FROM daily_kline WHERE stock_code = st.stock_code)
    LEFT JOIN daily_kline dk_ye ON dk_ye.stock_code = st.stock_code
        AND dk_ye.trade_date = (
            SELECT MAX(trade_date) FROM daily_kline
            WHERE stock_code = st.stock_code AND trade_date <= %s)
    WHERE ss.sector_code IN ({placeholders})
    """
    stock_rows = query(stock_sql, [dye] + sector_codes)

    stocks_by_sector = {}
    for r in stock_rows:
        scode = r['sector_code']
        lc = float(r['latest_close']) if r['latest_close'] else None
        cye = float(r['close_ye']) if r['close_ye'] else None
        ytd = _calc_change(lc, cye)
        rel_ytd = round(ytd - idx_ytd, 2) if ytd is not None and idx_ytd is not None else None
        stocks_by_sector.setdefault(scode, []).append({
            'stock_code': r['stock_code'],
            'stock_name': r['stock_name'],
            'ytd': ytd,
            'relative_ytd': rel_ytd,
        })

    sectors = []
    for sr in sector_rows:
        scode = sr['sector_code']
        s_ytd = _calc_change(
            float(sr['latest_close']) if sr['latest_close'] else None,
            float(sr['close_ye']) if sr['close_ye'] else None)
        stock_list = stocks_by_sector.get(scode, [])
        stock_list.sort(key=lambda x: (x.get('relative_ytd') or -9999), reverse=True)
        top = stock_list[:top_n]
        if top:
            sectors.append({
                'sector_code': scode,
                'sector_name': sr['sector_name'],
                'sector_ytd': s_ytd,
                'stocks': top,
            })

    sectors.sort(key=lambda x: (x.get('sector_ytd') or -9999), reverse=True)

    return {'sectors': sectors, 'idx_ytd': idx_ytd}


@router.get('/strong/sector-finance')
def sector_finance(sector_code: str = Query(...)):
    sr = query("SELECT sector_name, category_cn FROM sectors WHERE sector_code=%s", [sector_code])
    if not sr:
        return {'error': 'sector not found'}
    name = sr[0]['sector_name']
    cat_cn = sr[0]['category_cn']

    data = query(
        "SELECT report_date, total_revenue, total_net_profit, revenue_growth, net_profit_growth "
        "FROM ads_sector_finance WHERE sector_code=%s ORDER BY report_date",
        [sector_code])

    kline = query(
        "SELECT trade_date, close_price FROM sector_kline WHERE sector_code=%s "
        "ORDER BY trade_date",
        [sector_code])

    return {
        'sector_code': sector_code,
        'sector_name': name,
        'category_cn': cat_cn,
        'finance': [{
            'report_date': str(r['report_date']),
            'total_revenue': float(r['total_revenue']),
            'total_net_profit': float(r['total_net_profit']),
            'revenue_growth': float(r['revenue_growth']) if r['revenue_growth'] is not None else None,
            'net_profit_growth': float(r['net_profit_growth']) if r['net_profit_growth'] is not None else None,
        } for r in data],
        'kline': [{
            'date': str(k['trade_date']),
            'close': float(k['close_price']),
        } for k in kline],
    }
