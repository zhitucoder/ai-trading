from fastapi import APIRouter
from ..database import query

router = APIRouter()


@router.get('/macro/overview')
def macro_overview():
    latest = query("""
        SELECT end_date, quarter,
               SUM(total_mkv) as total_mkv,
               SUM(fund_count) as total_fund_count,
               COUNT(*) as stock_count
        FROM ads_stock_fund
        WHERE end_date LIKE '%%0630' OR end_date LIKE '%%1231'
        GROUP BY end_date, quarter
        ORDER BY end_date
    """)
    latest_date = latest[-1]['end_date'] if latest else None
    sector_flow = []
    if latest_date:
        sector_flow = query("""
            SELECT sector_name, mkv_change, mkv_change_pct, `signal`,
                   stock_count, total_fund_count, total_mkv
            FROM ads_fund_sector_flow
            WHERE end_date = %s AND sector_type = 'industry'
            ORDER BY mkv_change DESC
            LIMIT 20
        """, (latest_date,))
    return {'trend': latest, 'sector_flow': sector_flow, 'latest_date': latest_date}


@router.get('/sector/flow')
def sector_flow(sector_type: str = 'industry', end_date: str = None):
    if not end_date:
        row = query("SELECT MAX(end_date) as d FROM ads_fund_sector_flow WHERE sector_type=%s", (sector_type,))
        end_date = row[0]['d'] if row else None
    if not end_date:
        return []
    return query("""
        SELECT sector_name, mkv_change, mkv_change_pct, `signal`,
               stock_count, total_fund_count, total_mkv, avg_fund_count
        FROM ads_fund_sector_flow
        WHERE end_date = %s AND sector_type = %s
        ORDER BY mkv_change DESC
    """, (end_date, sector_type))


@router.get('/sector/{sector_name}/stocks')
def sector_stocks(sector_name: str, end_date: str = None):
    if not end_date:
        row = query("SELECT MAX(end_date) as d FROM ads_fund_sector_flow")
        end_date = row[0]['d'] if row else None
    if not end_date:
        return []
    return query("""
        SELECT c.stock_code, s.stock_name,
               c.fund_count, c.prev_fund_count, c.fund_count_change,
               c.amount_change_pct, c.total_mkv, c.mkv_change,
               c.active_count, c.passive_count
        FROM ads_fund_stock_change c
        JOIN stocks s ON c.stock_code = s.stock_code
        JOIN stock_sectors ss ON c.stock_code = ss.stock_code
        JOIN sectors sec ON ss.sector_code = sec.sector_code
        WHERE c.end_date = %s AND sec.sector_name = %s
        ORDER BY c.total_mkv DESC
    """, (end_date, sector_name))


@router.get('/stock/{stock_code}')
def stock_detail(stock_code: str):
    trend = query("SELECT * FROM ads_fund_stock_trend WHERE stock_code = %s", (stock_code,))
    history = query("""
        SELECT quarter, end_date, fund_count, prev_fund_count, fund_count_change,
               amount_change_pct, total_mkv, mkv_change, active_count, passive_count, active_ratio
        FROM ads_fund_stock_change
        WHERE stock_code = %s
        ORDER BY end_date
    """, (stock_code,))
    stock_info = query("SELECT stock_name FROM stocks WHERE stock_code = %s", (stock_code,))
    return {
        'trend': trend[0] if trend else None,
        'history': history,
        'stock_name': stock_info[0]['stock_name'] if stock_info else '',
    }


HOLDINGS_SORT = {
    'fund_name': 'fb.name',
    'fund_code': 'fp.ts_code',
    'amount': 'fp.amount',
    'mkv': 'fp.mkv',
    'stk_mkv_ratio': 'fp.stk_mkv_ratio',
    'stk_float_ratio': 'fp.stk_float_ratio',
}


@router.get('/stock/{stock_code}/holdings')
def stock_holdings(stock_code: str, end_date: str = None, sort_key: str = 'mkv',
                   sort_dir: str = 'desc', offset: int = 0, limit: int = 20):
    """某股票最近一个完整披露季度的基金持仓明细（分页 + 服务端排序）。"""
    sym = f'{stock_code}.%'
    if not end_date:
        row = query("""
            SELECT MAX(end_date) AS d FROM fund_portfolio
            WHERE symbol LIKE %s AND (end_date LIKE '%%0630' OR end_date LIKE '%%1231')
        """, (sym,))
        end_date = row[0]['d'] if row else None
    if not end_date:
        return {'end_date': None, 'quarter': '', 'total': 0, 'offset': 0, 'rows': []}

    col = HOLDINGS_SORT.get(sort_key, 'fp.mkv')
    direction = 'ASC' if sort_dir == 'asc' else 'DESC'

    total_row = query("""
        SELECT COUNT(*) AS c FROM fund_portfolio WHERE symbol LIKE %s AND end_date = %s
    """, (sym, end_date))
    total = total_row[0]['c'] if total_row else 0

    rows = query(f"""
        SELECT fp.ts_code AS fund_code, fb.name AS fund_name,
               fp.amount, fp.mkv, fp.stk_mkv_ratio, fp.stk_float_ratio
        FROM fund_portfolio fp
        LEFT JOIN fund_basic fb ON fb.ts_code = fp.ts_code
        WHERE fp.symbol LIKE %s AND fp.end_date = %s
        ORDER BY {col} {direction}
        LIMIT %s OFFSET %s
    """, (sym, end_date, limit, offset))

    return {
        'end_date': end_date,
        'quarter': _quarter_label(end_date),
        'total': total,
        'offset': offset,
        'rows': [{
            'fund_code': r['fund_code'],
            'fund_name': r['fund_name'] or r['fund_code'],
            'amount': float(r['amount']) if r['amount'] is not None else None,
            'mkv': float(r['mkv']) if r['mkv'] is not None else None,
            'stk_mkv_ratio': float(r['stk_mkv_ratio']) if r['stk_mkv_ratio'] is not None else None,
            'stk_float_ratio': float(r['stk_float_ratio']) if r['stk_float_ratio'] is not None else None,
        } for r in rows],
    }


@router.get('/stock/{stock_code}/fund/{fund_code}')
def stock_fund_history(stock_code: str, fund_code: str):
    """某基金对某股票最近2年（Q2/Q4 完整披露季度）的持仓增减历史。"""
    sym = f'{stock_code}.%'
    rows = query("""
        SELECT end_date, amount, mkv, stk_mkv_ratio, stk_float_ratio
        FROM fund_portfolio
        WHERE ts_code = %s AND symbol LIKE %s
          AND (end_date LIKE '%%0630' OR end_date LIKE '%%1231')
        ORDER BY end_date
    """, (fund_code, sym))
    rows = rows[-8:]

    fund_row = query("SELECT name FROM fund_basic WHERE ts_code = %s", (fund_code,))
    fund_name = fund_row[0]['name'] if fund_row else fund_code

    out = []
    prev = None
    for r in rows:
        item = {
            'end_date': r['end_date'],
            'quarter': _quarter_label(r['end_date']),
            'amount': float(r['amount']) if r['amount'] is not None else None,
            'mkv': float(r['mkv']) if r['mkv'] is not None else None,
            'stk_mkv_ratio': float(r['stk_mkv_ratio']) if r['stk_mkv_ratio'] is not None else None,
            'stk_float_ratio': float(r['stk_float_ratio']) if r['stk_float_ratio'] is not None else None,
        }
        if prev and prev['amount'] and item['amount'] is not None:
            item['amount_change'] = item['amount'] - prev['amount']
            item['amount_change_pct'] = item['amount_change'] / prev['amount'] * 100
            item['ratio_change'] = (item['stk_mkv_ratio'] - prev['stk_mkv_ratio']
                                    if item['stk_mkv_ratio'] is not None and prev['stk_mkv_ratio'] is not None else None)
        else:
            item['amount_change'] = None
            item['amount_change_pct'] = None
            item['ratio_change'] = None
        out.append(item)
        prev = item

    return {
        'fund_code': fund_code,
        'fund_name': fund_name,
        'stock_code': stock_code,
        'rows': out,
    }


def _quarter_label(end_date):
    if not end_date or len(end_date) != 8:
        return end_date or ''
    q = {'03': 'Q1', '06': 'Q2', '09': 'Q3', '12': 'Q4'}.get(end_date[4:6], '')
    return f'{end_date[2:4]}{q}' if q else end_date


@router.get('/screen')
def screen(type: str = 'sustain', end_date: str = None):
    if not end_date:
        row = query("SELECT MAX(end_date) as d FROM ads_fund_stock_change")
        end_date = row[0]['d'] if row else None
    if not end_date:
        return []

    if type == 'crash':
        return query("""
            SELECT c.stock_code, s.stock_name, c.fund_count, c.fund_count_change,
                   c.amount_change_pct, c.total_mkv, c.mkv_change
            FROM ads_fund_stock_change c
            JOIN stocks s ON c.stock_code = s.stock_code
            WHERE c.end_date = %s AND c.amount_change_pct < -80
            ORDER BY c.amount_change_pct ASC
            LIMIT 50
        """, (end_date,))
    elif type == 'surge':
        return query("""
            SELECT c.stock_code, s.stock_name, c.fund_count, c.fund_count_change,
                   c.amount_change_pct, c.total_mkv, c.mkv_change
            FROM ads_fund_stock_change c
            JOIN stocks s ON c.stock_code = s.stock_code
            WHERE c.end_date = %s AND c.amount_change_pct > 50
            ORDER BY c.amount_change_pct DESC
            LIMIT 50
        """, (end_date,))
    elif type == 'thousand':
        return query("""
            SELECT stock_code,
                   (SELECT stock_name FROM stocks WHERE stock_code = t.stock_code) as stock_name,
                   fund_count, trend_label, total_mkv, increase_quarters, latest_change_pct
            FROM ads_fund_stock_trend t
            WHERE fund_count >= 1000
            ORDER BY fund_count DESC
            LIMIT 50
        """)
    elif type == 'sustain':
        return query("""
            SELECT stock_code,
                   (SELECT stock_name FROM stocks WHERE stock_code = t.stock_code) as stock_name,
                   fund_count, trend_label, trend_score, total_mkv,
                   increase_quarters, consecutive_increase, latest_change_pct
            FROM ads_fund_stock_trend t
            WHERE trend_score >= 3
            ORDER BY fund_count DESC
            LIMIT 50
        """)
    return []
