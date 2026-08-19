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
