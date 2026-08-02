import json
import threading
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
from ..database import query, execute
from ..strategies.profile import generate_profile
from ..strategies.stock_intro import get_stock_intro
from ..profile_batch import run_batch, TAG_COLUMNS

router = APIRouter()
_refresh_lock = threading.Lock()


# ── 单股画像 ──
@router.get('/profile/{stock_code}')
def get_profile(stock_code: str, refresh: bool = False):
    if not refresh:
        r = query("SELECT profile_json FROM stock_profiles WHERE stock_code = %s "
                  "ORDER BY trade_date DESC LIMIT 1", [stock_code])
        if r and r[0]['profile_json']:
            raw = r[0]['profile_json']
            data = json.loads(raw) if isinstance(raw, str) else raw
        else:
            data = generate_profile(stock_code)
    else:
        data = generate_profile(stock_code)
    from ..strategies.dividend import get_dividend_summary
    data['intro'] = get_stock_intro(stock_code)
    data['dividend'] = get_dividend_summary(stock_code, latest_price=data.get('latest_price'))
    return data


# ── 人工维护公司介绍 ──
class IntroUpsert(BaseModel):
    text: str
    positioning_status: str = 'unknown'
    positioning_label: Optional[str] = None
    chain_position: Optional[str] = None


@router.post('/profile/{stock_code}/intro')
def set_stock_intro(stock_code: str, body: IntroUpsert):
    from ..strategies.stock_intro import upsert_stock_intro
    name_row = query("SELECT stock_name FROM stocks WHERE stock_code = %s", [stock_code])
    name = name_row[0]['stock_name'] if name_row else stock_code
    upsert_stock_intro(stock_code, name, body.text, body.positioning_status,
                       body.positioning_label, body.chain_position, source='manual')
    return {'status': 'ok', 'intro': get_stock_intro(stock_code)}


# ── 画像状态 ──
@router.get('/profiles/status')
def profiles_status():
    row = query("""
        SELECT MAX(trade_date) AS latest_data_date,
               COUNT(*) AS total_profiles
        FROM stock_profiles
    """)
    log = query("""
        SELECT status, started_at, finished_at
        FROM profile_refresh_log
        ORDER BY id DESC LIMIT 1
    """)
    fin = query("SELECT MAX(fin_report_date) AS d FROM stock_profiles")

    latest_data_date = row[0]['latest_data_date'] if row else None
    fin_date = fin[0]['d'] if fin and fin[0]['d'] else None

    status = 'idle'
    last_refresh_time = None
    if log:
        status = log[0]['status']
        if log[0]['started_at']:
            last_refresh_time = str(log[0]['started_at'])

    return {
        'latest_data_date': str(latest_data_date) if latest_data_date else None,
        'latest_trade_date': str(latest_data_date) if latest_data_date else None,
        'fin_report_date': str(fin_date) if fin_date else None,
        'total_profiles': row[0]['total_profiles'] if row else 0,
        'last_refresh_time': last_refresh_time,
        'refreshing': status == 'running',
    }


# ── 财务趋势图数据 ──
@router.get('/profile/{stock_code}/fin-chart')
def profile_fin_chart(stock_code: str):
    rev_rows = query("""
        SELECT report_date, operating_revenue, net_profit
        FROM fin_income
        WHERE stock_code = %s AND DATE_FORMAT(report_date,'%%m-%%d')='12-31'
          AND report_date >= '2018-01-01'
        ORDER BY report_date
    """, [stock_code])

    kline_rows = query("""
        SELECT
            DATE_FORMAT(DATE_SUB(trade_date, INTERVAL WEEKDAY(trade_date) DAY), '%%Y-%%m-%%d') AS week_start,
            SUBSTRING_INDEX(GROUP_CONCAT(open_price ORDER BY trade_date), ',', 1) + 0 AS open_price,
            MAX(high_price) AS high_price,
            MIN(low_price) AS low_price,
            SUBSTRING_INDEX(GROUP_CONCAT(close_price ORDER BY trade_date DESC), ',', 1) + 0 AS close_price
        FROM daily_kline
        WHERE stock_code = %s AND trade_date >= '2018-01-01'
        GROUP BY week_start
        ORDER BY week_start
    """, [stock_code])

    years, revenues, profits, growth_rates = [], [], [], []
    prev_np = None
    for r in rev_rows:
        yr = r['report_date'].year
        rev = float(r['operating_revenue'] or 0) / 1e8
        np = float(r['net_profit'] or 0) / 1e8
        growth = round((np - prev_np) / prev_np * 100, 1) if prev_np and prev_np != 0 else None
        years.append(yr)
        revenues.append(round(rev, 1))
        profits.append(round(np, 2))
        growth_rates.append(growth)
        prev_np = np

    return {'years': years, 'revenues': revenues, 'profits': profits,
            'growth_rates': growth_rates,
            'weekly_kline': [{'date': r['week_start'].strftime('%Y-%m-%d') if hasattr(r['week_start'], 'strftime') else str(r['week_start'])[:10],
                              'open': float(r['open_price']), 'high': float(r['high_price']),
                              'low': float(r['low_price']), 'close': float(r['close_price'])}
                             for r in kline_rows]}


# ── 触发刷新 ──
@router.post('/profiles/refresh')
def trigger_refresh():
    if not _refresh_lock.acquire(blocking=False):
        raise HTTPException(429, '刷新已在进行中')

    def _run():
        try:
            run_batch(report_date=date.today())
        finally:
            _refresh_lock.release()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {'status': 'started', 'total_stocks': query("SELECT COUNT(*) AS c FROM stocks")[0]['c']}


# ── 刷新进度 ──
@router.get('/profiles/refresh/progress')
def refresh_progress():
    log = query("""
        SELECT status, total_stocks, computed_stocks, error_stocks,
               started_at, finished_at
        FROM profile_refresh_log ORDER BY id DESC LIMIT 1
    """)
    if not log:
        return {'status': 'idle'}
    l = log[0]
    elapsed = None
    remains = None
    if l['started_at']:
        secs = (l['finished_at'] or datetime.combine(date.today(), datetime.min.time())).timestamp() - l['started_at'].timestamp()
        elapsed = int(secs)
        if l['status'] == 'running' and l['computed_stocks'] > 0:
            per_stock = secs / l['computed_stocks']
            remains = int(per_stock * (l['total_stocks'] - l['computed_stocks']))
    return {
        'status': l['status'],
        'total': l['total_stocks'],
        'computed': l['computed_stocks'],
        'errors': l['error_stocks'],
        'elapsed_seconds': elapsed,
        'estimated_remaining_seconds': remains or 0,
    }


# ── 画像筛选 ──
class TagFilter(BaseModel):
    must: List[str] = []
    must_not: List[str] = []
    any: List[str] = []


class SearchRequest(BaseModel):
    stages: List[str] = []
    tags: TagFilter = TagFilter()
    tech_score_min: Optional[int] = None
    fund_score_min: Optional[int] = None
    revenue_growth_min: Optional[float] = None
    net_profit_growth_min: Optional[float] = None
    debt_ratio_max: Optional[float] = None
    price_change_min: Optional[float] = None
    price_change_max: Optional[float] = None
    gm_growth_q_min: Optional[float] = None
    gm_growth_2y_min: Optional[float] = None
    contract_liab_min: Optional[float] = None
    contract_liab_max: Optional[float] = None
    rev_cagr_3y_min: Optional[float] = None
    rev_cagr_3y_max: Optional[float] = None
    rev_cagr_5y_min: Optional[float] = None
    rev_cagr_5y_max: Optional[float] = None
    profit_cagr_3y_min: Optional[float] = None
    profit_cagr_3y_max: Optional[float] = None
    profit_cagr_5y_min: Optional[float] = None
    profit_cagr_5y_max: Optional[float] = None
    roe_min: Optional[float] = None
    roe_max: Optional[float] = None
    roe_ttm_min: Optional[float] = None
    roe_ttm_max: Optional[float] = None
    dividend_yield_min: Optional[float] = None
    dividend_yield_max: Optional[float] = None
    has_dividend_this_year: Optional[bool] = None
    consecutive_dividend_years: Optional[int] = None
    has_mid_year_dividend: Optional[bool] = None
    zxm_asset_weight: Optional[str] = None
    zxm_hematopoiesis: Optional[str] = None
    zxm_margin_level: Optional[str] = None
    zxm_cashflow_type: Optional[str] = None
    zxm_growth_rate: Optional[str] = None
    zxm_growth_quality: Optional[str] = None
    zxm_leverage: Optional[str] = None
    zxm_overall_rating: Optional[str] = None
    sectors: List[str] = []
    page: int = 1
    page_size: int = 50
    sort_by: str = 'tech_score'
    sort_order: str = 'desc'


def _tag_to_col(tag_id: str) -> str:
    prefix = tag_id.split('.')[0]
    suffix = tag_id.split('.')[1] if '.' in tag_id else tag_id
    return f'tag_{suffix}'

@router.post('/profiles/search')
def search_profiles(body: SearchRequest):
    conditions = ["p.profile_json IS NOT NULL"]
    params = {}

    if body.stages:
        placeholders = ','.join([f'%({k})s' for k in [f'stage_{i}' for i in range(len(body.stages))]])
        stage_params = {f'stage_{i}': s for i, s in enumerate(body.stages)}
        conditions.append(f'p.stage_id IN ({placeholders})')
        params.update(stage_params)

    for tag in body.tags.must:
        col = _tag_to_col(tag)
        if col in TAG_COLUMNS:
            conditions.append(f'p.{col} = TRUE')

    for tag in body.tags.must_not:
        col = _tag_to_col(tag)
        if col in TAG_COLUMNS:
            conditions.append(f'p.{col} = FALSE')

    if body.tags.any:
        cols = [_tag_to_col(t) for t in body.tags.any if _tag_to_col(t) in TAG_COLUMNS]
        any_conds = [f'p.{c} = TRUE' for c in cols]
        if any_conds:
            conditions.append(f'({" OR ".join(any_conds)})')

    if body.tech_score_min is not None:
        conditions.append('p.tech_score >= %(tech_score_min)s')
        params['tech_score_min'] = body.tech_score_min
    if body.fund_score_min is not None:
        conditions.append('p.fund_score >= %(fund_score_min)s')
        params['fund_score_min'] = body.fund_score_min
    if body.revenue_growth_min is not None:
        conditions.append('p.revenue_growth >= %(revenue_growth_min)s')
        params['revenue_growth_min'] = body.revenue_growth_min
    if body.net_profit_growth_min is not None:
        conditions.append('p.net_profit_growth >= %(net_profit_growth_min)s')
        params['net_profit_growth_min'] = body.net_profit_growth_min
    if body.debt_ratio_max is not None:
        conditions.append('(p.debt_ratio IS NULL OR p.debt_ratio <= %(debt_ratio_max)s)')
        params['debt_ratio_max'] = body.debt_ratio_max
    if body.price_change_min is not None:
        conditions.append('p.price_change_pct >= %(price_change_min)s')
        params['price_change_min'] = body.price_change_min
    if body.price_change_max is not None:
        conditions.append('p.price_change_pct <= %(price_change_max)s')
        params['price_change_max'] = body.price_change_max
    if body.gm_growth_q_min is not None:
        conditions.append("JSON_EXTRACT(p.profile_json, '$.gross_margin_growth_q') >= %(gm_growth_q_min)s")
        params['gm_growth_q_min'] = body.gm_growth_q_min
    if body.gm_growth_2y_min is not None:
        conditions.append("JSON_EXTRACT(p.profile_json, '$.gross_margin_growth_q') >= %(gm_growth_2y_min)s")
        conditions.append("JSON_EXTRACT(p.profile_json, '$.gm_growth_prev_yr') IS NOT NULL AND JSON_EXTRACT(p.profile_json, '$.gm_growth_prev_yr') >= %(gm_growth_2y_min)s")
        params['gm_growth_2y_min'] = body.gm_growth_2y_min

    if body.contract_liab_min is not None:
        conditions.append("JSON_EXTRACT(p.profile_json, '$.fin_data.contract_liab_to_assets') >= %(contract_liab_min)s")
        params['contract_liab_min'] = body.contract_liab_min
    if body.contract_liab_max is not None:
        conditions.append("(JSON_EXTRACT(p.profile_json, '$.fin_data.contract_liab_to_assets') IS NULL OR JSON_EXTRACT(p.profile_json, '$.fin_data.contract_liab_to_assets') <= %(contract_liab_max)s)")
        params['contract_liab_max'] = body.contract_liab_max

    cagr_filters = [
        ('rev_cagr_3y_min', 'rev_cagr_3y', '>='),
        ('rev_cagr_3y_max', 'rev_cagr_3y', '<='),
        ('rev_cagr_5y_min', 'rev_cagr_5y', '>='),
        ('rev_cagr_5y_max', 'rev_cagr_5y', '<='),
        ('profit_cagr_3y_min', 'profit_cagr_3y', '>='),
        ('profit_cagr_3y_max', 'profit_cagr_3y', '<='),
        ('profit_cagr_5y_min', 'profit_cagr_5y', '>='),
        ('profit_cagr_5y_max', 'profit_cagr_5y', '<='),
    ]
    for field, col, op in cagr_filters:
        val = getattr(body, field, None)
        if val is not None:
            conditions.append(f'p.{col} IS NOT NULL AND p.{col} {op} %({field})s')
            params[field] = val

    zxm_field_map = {
        'zxm_asset_weight': 'asset_weight', 'zxm_hematopoiesis': 'hematopoiesis',
        'zxm_margin_level': 'margin_level', 'zxm_cashflow_type': 'cashflow_type',
        'zxm_growth_rate': 'growth_rate', 'zxm_growth_quality': 'growth_quality',
        'zxm_leverage': 'leverage', 'zxm_overall_rating': 'overall_rating',
    }
    zxm_join = ''
    for body_field, db_col in zxm_field_map.items():
        val = getattr(body, body_field, None)
        if val:
            conditions.append(f'z.{db_col} = %({body_field})s')
            params[body_field] = val
    has_zxm = any(getattr(body, f, None) for f in zxm_field_map)
    if has_zxm:
        zxm_join = 'JOIN zxm_stock_tags z ON z.stock_code = p.stock_code AND z.report_date = (SELECT MAX(z2.report_date) FROM zxm_stock_tags z2 WHERE z2.stock_code = p.stock_code)'

    if body.sectors:
        placeholders = ','.join([f'%({k})s' for k in [f'sector_{i}' for i in range(len(body.sectors))]])
        sector_params = {f'sector_{i}': s for i, s in enumerate(body.sectors)}
        conditions.append(f'p.stock_code IN (SELECT ss.stock_code FROM stock_sectors ss WHERE ss.sector_code IN ({placeholders}))')
        params.update(sector_params)

    roe_filters = [
        ('roe_min', 'roe', '>='), ('roe_max', 'roe', '<='),
        ('roe_ttm_min', 'roe_ttm', '>='), ('roe_ttm_max', 'roe_ttm', '<='),
    ]
    for field, col, op in roe_filters:
        val = getattr(body, field, None)
        if val is not None:
            conditions.append(f'p.{col} IS NOT NULL AND p.{col} {op} %({field})s')
            params[field] = val

    dividend_filters = [
        ('dividend_yield_min', 'dividend_yield', '>='),
        ('dividend_yield_max', 'dividend_yield', '<='),
    ]
    for field, col, op in dividend_filters:
        val = getattr(body, field, None)
        if val is not None:
            conditions.append(f'p.{col} IS NOT NULL AND p.{col} {op} %({field})s')
            params[field] = val

    if body.has_dividend_this_year:
        conditions.append('p.has_dividend_this_year = TRUE')
    if body.has_mid_year_dividend:
        conditions.append('p.has_mid_year_dividend = TRUE')
    if body.consecutive_dividend_years:
        conditions.append('p.consecutive_dividend_years >= %(cdy)s')
        params['cdy'] = body.consecutive_dividend_years

    sort_col = 'p.tech_score'
    if body.sort_by in ('fund_score', 'revenue_growth', 'net_profit_growth', 'price_change_pct', 'dividend_yield',
                         'contract_liab_to_assets',
                         'rev_cagr_3y', 'rev_cagr_5y', 'rev_cagr_10y',
                         'profit_cagr_3y', 'profit_cagr_5y', 'profit_cagr_10y', 'roe', 'roe_ttm', 'gross_margin'):
        if body.sort_by == 'contract_liab_to_assets':
            sort_col = "CAST(JSON_EXTRACT(p.profile_json, '$.fin_data.contract_liab_to_assets') AS DECIMAL(10,2))"
        else:
            sort_col = f'p.{body.sort_by}'
    elif body.sort_by in zxm_field_map:
        sort_col = f'z.{zxm_field_map[body.sort_by]}'
    sort_dir = 'DESC' if body.sort_order == 'desc' else 'ASC'
    offset = (body.page - 1) * body.page_size
    limit = body.page_size

    where = ' AND '.join(conditions)
    latest = query("SELECT MAX(data_date) AS d FROM stock_profiles")[0]['d']

    join_clause = zxm_join
    count_sql = f"SELECT COUNT(*) AS c FROM stock_profiles p {join_clause} WHERE p.data_date = %(ldate)s AND {where}"
    count_params = {'ldate': str(latest), **params}
    total = query(count_sql, count_params)[0]['c']

    tag_cols_sql = ', '.join(f'p.{c}' for c in TAG_COLUMNS)
    zxm_select = ', '.join(f'z.{db_col} AS {body_field}' for body_field, db_col in zxm_field_map.items()) if has_zxm else ''
    sql = f"""
        SELECT p.stock_code, p.stock_name, p.latest_price, p.price_change_pct,
               p.stage_id, p.stage_confidence, p.tech_score, p.fund_score,
               p.revenue_growth, p.net_profit_growth, p.debt_ratio,
               p.roe, p.roe_ttm, p.gross_margin, p.prev_year_revenue,
               p.dividend_yield,
               p.rev_cagr_3y, p.rev_cagr_5y, p.rev_cagr_10y,
               p.profit_cagr_3y, p.profit_cagr_5y, p.profit_cagr_10y,
               JSON_EXTRACT(p.profile_json, '$.fin_data.contract_liab_to_assets') AS contract_liab_to_assets,
               {tag_cols_sql}
               {',' + zxm_select if zxm_select else ''}
        FROM stock_profiles p {join_clause}
        WHERE p.data_date = %(ldate)s AND {where}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %(lo)s OFFSET %(of)s
    """
    data_params = {'ldate': str(latest), 'lo': limit, 'of': offset, **params}
    rows = query(sql, data_params)

    STAGE_NAMES = {
        'stage.s1': '打底蓄势期', 'stage.s1s2': '过渡期',
        'stage.s2': '突围加速期', 'stage.s3': '见顶派发期', 'stage.s4': '衰败下跌期',
    }

    from ..strategies.profile import IND_TAGS_DEF, BIZ_TAGS_DEF
    TAG_DISPLAY = {**{f'ind.{k.split(".")[1]}': v['name'] for k, v in IND_TAGS_DEF.items()},
                   **{f'biz.{k.split(".")[1]}': v['name'] for k, v in BIZ_TAGS_DEF.items()}}

    for r in rows:
        r['stage_name'] = STAGE_NAMES.get(r['stage_id'], '')
        active = []
        for col in TAG_COLUMNS:
            if r.get(col):
                tag_key = col[4:]
                for prefix in ('biz.', 'ind.'):
                    tid = f'{prefix}{tag_key}'
                    if tid in TAG_DISPLAY:
                        active.append({'id': tid, 'name': TAG_DISPLAY[tid]})
                        break
        r['active_tags'] = active

    return {
        'total': total,
        'page': body.page,
        'page_size': body.page_size,
        'rows': rows,
    }


@router.get('/profile/{stock_code}/zxm-tags')
def get_zxm_tags(stock_code: str):
    row = query("SELECT * FROM zxm_stock_tags WHERE stock_code = %s ORDER BY report_date DESC LIMIT 1", [stock_code])
    if not row:
        from ..zxm_tags import compute_tags
        tags = compute_tags(stock_code)
        if tags:
            tags.pop('stock_code')
            tags.pop('stock_name')
            return tags
        return {'error': 'no data'}
    r = row[0]
    r.pop('id')
    r.pop('stock_code')
    r.pop('stock_name')
    r.pop('created_at')
    r.pop('updated_at')
    return r


@router.get('/sectors')
def list_sectors(category: str = Query('industry', regex='^(industry|concept)$')):
    rows = query("""
        SELECT sector_code, sector_name FROM sectors
        WHERE category = %s ORDER BY sector_code
    """, [category])
    return {'rows': rows}


# ── 分红列表 ──
@router.get('/dividends/list')
def list_dividends(year: Optional[int] = None, is_mid: Optional[int] = None,
                   sort: str = 'ex_dividend_date', order: str = 'desc',
                   page: int = 1, page_size: int = 50):
    where = []
    params = {}
    if year:
        where.append('d.ex_dividend_date LIKE %(year)s')
        params['year'] = f'{year}%'
    if is_mid is not None:
        if is_mid == 2:
            where.append('d.is_mid_year = 0')
        else:
            where.append('d.is_mid_year = %(is_mid)s')
            params['is_mid'] = 1 if is_mid else 0
    if sort not in ('ex_dividend_date', 'report_date', 'cash_per_10', 'dividend_yield', 'payout_ratio'):
        sort = 'ex_dividend_date'
    sort_col = f'd.{sort}'
    sort_dir = 'DESC' if order == 'desc' else 'ASC'

    where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''
    total = query(f"SELECT COUNT(*) AS c FROM stock_dividend d{where_sql}", params)[0]['c']
    offset = (page - 1) * page_size
    rows = query(f"""
        SELECT d.stock_code, s.stock_name, d.report_date, d.assign_progress,
               d.plan_profile, d.cash_per_10, d.bonus_per_share, d.send_ratio,
               d.trans_ratio, d.dividend_yield, d.payout_ratio, d.eps,
               d.ex_dividend_date, d.equity_record_date, d.notice_date, d.is_mid_year
        FROM stock_dividend d
        LEFT JOIN stocks s ON s.stock_code = d.stock_code
        {where_sql}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %(lo)s OFFSET %(of)s
    """, {**params, 'lo': page_size, 'of': offset})

    for r in rows:
        if r['dividend_yield'] is not None:
            r['dividend_yield'] = round(float(r['dividend_yield']) * 100, 2)
        r['report_date'] = str(r['report_date']) if r['report_date'] else None
        r['ex_dividend_date'] = str(r['ex_dividend_date']) if r['ex_dividend_date'] else None
        r['equity_record_date'] = str(r['equity_record_date']) if r['equity_record_date'] else None
        r['notice_date'] = str(r['notice_date']) if r['notice_date'] else None

    return {'total': total, 'page': page, 'page_size': page_size, 'rows': rows}


@router.get('/stocks/search')
def search_stocks(q: str = Query('', min_length=1)):
    q = q.strip()
    if not q:
        return {'rows': []}
    rows = query("""
        SELECT stock_code, stock_name FROM stocks
        WHERE stock_code LIKE %(code)s
           OR stock_name LIKE %(name)s
           OR pinyin LIKE %(py)s
           OR py_initials LIKE %(init)s
        ORDER BY stock_code
        LIMIT 10
    """, {'code': f'{q}%', 'name': f'%{q}%', 'py': f'{q}%', 'init': f'{q}%'})
    return {'rows': rows}


@router.get('/watchlist')
def get_watchlist():
    rows = query("""
        SELECT w.stock_code, w.stock_name, w.added_at,
               p.latest_price, p.price_change_pct, p.stage_id, p.revenue_growth,
               p.net_profit_growth, p.tech_score, p.fund_score
        FROM user_watchlist w
        LEFT JOIN stock_profiles p ON p.stock_code = w.stock_code
            AND p.data_date = (SELECT MAX(data_date) FROM stock_profiles)
        ORDER BY w.added_at DESC
    """)
    STAGE_NAMES = {
        'stage.s1': '打底蓄势期', 'stage.s1s2': '过渡期',
        'stage.s2': '突围加速期', 'stage.s3': '见顶派发期', 'stage.s4': '衰败下跌期',
    }
    for r in rows:
        r['stage_name'] = STAGE_NAMES.get(r['stage_id'], '')
    return {'rows': rows, 'total': len(rows)}


@router.post('/watchlist/add')
def add_watchlist(stock_code: str = Query(...)):
    name_row = query("SELECT stock_name FROM stocks WHERE stock_code = %s", [stock_code])
    name = name_row[0]['stock_name'] if name_row else stock_code
    execute("REPLACE INTO user_watchlist (stock_code, stock_name) VALUES (%s, %s)", [stock_code, name])
    return {'status': 'ok'}


@router.post('/watchlist/remove')
def remove_watchlist(stock_code: str = Query(...)):
    execute("DELETE FROM user_watchlist WHERE stock_code = %s", [stock_code])
    return {'status': 'ok'}


@router.get('/watchlist/check')
def check_watchlist(stock_code: str = Query(...)):
    r = query("SELECT 1 FROM user_watchlist WHERE stock_code = %s", [stock_code])
    return {'in_watchlist': len(r) > 0}


# ── 独立页面报告 ──
@router.get('/report/trend/{stock_code}', response_class=HTMLResponse)
def report_trend(stock_code: str):
    name_row = query("SELECT stock_name FROM stocks WHERE stock_code = %s", [stock_code])
    sname = name_row[0]['stock_name'] if name_row else stock_code

    rev_rows = query("""
        SELECT report_date, operating_revenue, net_profit
        FROM fin_income
        WHERE stock_code = %s AND DATE_FORMAT(report_date,'%%m-%%d')='12-31'
          AND report_date >= '2018-01-01'
        ORDER BY report_date
    """, [stock_code])

    kline_rows = query("""
        SELECT DATE_FORMAT(DATE_SUB(trade_date, INTERVAL WEEKDAY(trade_date) DAY), '%%Y-%%m-%%d') AS week_start,
               SUBSTRING_INDEX(GROUP_CONCAT(open_price ORDER BY trade_date), ',', 1) + 0 AS open_price,
               MAX(high_price) AS high_price, MIN(low_price) AS low_price,
               SUBSTRING_INDEX(GROUP_CONCAT(close_price ORDER BY trade_date DESC), ',', 1) + 0 AS close_price
        FROM daily_kline WHERE stock_code = %s AND trade_date >= '2018-01-01'
        GROUP BY week_start ORDER BY week_start
    """, [stock_code])

    years, revenues, profits, growth_rates = [], [], [], []
    prev_np = None
    for r in rev_rows:
        yr = r['report_date'].year
        rev = float(r['operating_revenue'] or 0) / 1e8
        np = float(r['net_profit'] or 0) / 1e8
        growth = round((np - prev_np) / prev_np * 100, 1) if prev_np and prev_np != 0 else None
        years.append(yr); revenues.append(round(rev, 1)); profits.append(round(np, 2)); growth_rates.append(growth)
        prev_np = np

    wk = [{'date': r['week_start'].strftime('%Y-%m-%d') if hasattr(r['week_start'], 'strftime') else str(r['week_start'])[:10],
           'o': float(r['open_price']), 'h': float(r['high_price']),
           'l': float(r['low_price']), 'c': float(r['close_price'])} for r in kline_rows]

    import json
    data_json = json.dumps({'years': years, 'revenues': revenues, 'profits': profits,
                           'growth_rates': growth_rates, 'weekly_kline': wk})

    return f"""<!DOCTYPE html><html lang=zh><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1"><title>{stock_code} {sname} 财务趋势</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0d0d1a;color:#ccc;font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:16px}}h1{{font-size:16px;color:#00d4ff;margin-bottom:4px}}.sub{{font-size:12px;color:#ccc;margin-bottom:12px}}#chart{{width:100%;height:300px;background:#131322;border-radius:10px;border:1px solid #1e1e35;position:relative}}canvas{{width:100%;height:100%}}.legend{{display:flex;gap:16px;margin-top:8px;font-size:11px;color:#ccc;flex-wrap:wrap}}</style>
<div><h1>{stock_code} {sname}</h1><div class=sub>营收·净利润·净利增长率·股价趋势</div></div>
<div id=chart><canvas id=c></canvas></div>
<div class=legend><span style=color:#6495ed>■ 营收(亿)</span><span style=color:#ffd700>■ 净利润(亿)</span><span style=color:#ff6b6b>■ 净利增长率%</span><span style=color:#4ecdc4>■ 周K</span></div>
<script>var d={data_json};!function(){{var c=document.getElementById('c'),p=c.parentElement,ctx=c.getContext('2d'),W=p.clientWidth,H=p.clientHeight,pr=window.devicePixelRatio||1;c.width=W*pr;c.height=H*pr;c.style.width=W+'px';c.style.height=H+'px';ctx.scale(pr,pr);
var pad={{top:8,bottom:32,left:50,right:50}},cw=W-pad.left-pad.right,ch=H-pad.top-pad.bottom,n=d.years.length,xs=d.years.map((_,i)=>pad.left+cw*i/(n-1||1)),rMax=Math.max(...d.revenues)*1.15,pMin=Math.min(...d.profits)*1.1,pMax=Math.max(...d.profits)*1.15,pR=pMax-pMin||1,gv=d.growth_rates.filter(v=>v!=null),gMin=Math.min(...gv)*1.1,gMax=Math.max(...gv)*1.15,gR=gMax-gMin||1;
var pk=d.weekly_kline||[],pl=Infinity,pm=0;pk.forEach(function(b){{if(b.l<pl)pl=b.l;if(b.h>pm)pm=b.h}});var pSpan=(pm-pl)||1,pl2=pl-0.1*pSpan,pm2=pm+0.1*pSpan,pSpan2=(pm2-pl2)||1;
function yr(v){{return pad.top+ch*(1-v/rMax)}}
function yp(v){{return pad.top+ch*(1-(v-pMin)/pR)}}
function yg(v){{return pad.top+ch*(1-(v-gMin)/gR)}}
function ypr(v){{return pad.top+ch*(1-(v-pl2)/pSpan2)}}
var ys=d.years[0],ye=d.years[n-1],ms=new Date(ys,0,1).getTime(),me=new Date(ye,11,31).getTime(),mr=me-ms||1;
function dx(s){{return pad.left+cw*(new Date(s).getTime()-ms)/mr}}
ctx.strokeStyle='rgba(255,255,255,0.05)';ctx.lineWidth=1;for(var i=0;i<=4;i++){{var y=pad.top+ch*i/4;ctx.beginPath();ctx.moveTo(pad.left,y);ctx.lineTo(pad.left+cw,y);ctx.stroke()}}
for(var i=0;i<n;i++){{var x=xs[i]-14,w=28,h=ch*d.revenues[i]/rMax;ctx.fillStyle='rgba(100,149,237,0.65)';ctx.fillRect(x,pad.top+ch-h,w,h)}}
ctx.beginPath();ctx.strokeStyle='#ffd700';ctx.lineWidth=2.5;for(var i=0;i<n;i++){{var y=yp(d.profits[i]);i===0?ctx.moveTo(xs[i],y):ctx.lineTo(xs[i],y)}}ctx.stroke();ctx.fillStyle='#ffd700';for(var i=0;i<n;i++){{var y=yp(d.profits[i]);ctx.beginPath();ctx.arc(xs[i],y,3.5,0,Math.PI*2);ctx.fill()}}
ctx.beginPath();ctx.setLineDash([6,3]);ctx.strokeStyle='#ff6b6b';ctx.lineWidth=2;for(var i=0;i<n;i++){{var v=d.growth_rates[i];if(v==null)continue;var y=yg(v);i===0||d.growth_rates[i-1]==null?ctx.moveTo(xs[i],y):ctx.lineTo(xs[i],y)}}ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#ff6b6b';for(var i=0;i<n;i++){{var v=d.growth_rates[i];if(v==null)continue;ctx.beginPath();ctx.arc(xs[i],yg(v),3,0,Math.PI*2);ctx.fill()}}
if(pk.length>0){{var cw2=Math.max(1,Math.min(6,cw/pk.length*0.6));for(var i=0;i<pk.length;i++){{var b=pk[i],x=dx(b.date),yO=ypr(b.o),yC=ypr(b.c),yH=ypr(b.h),yL=ypr(b.l),up=b.c>=b.o;ctx.strokeStyle=up?'#ef4444':'#10b981';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,yH);ctx.lineTo(x,yL);ctx.stroke();var bt=Math.min(yO,yC),bh=Math.max(Math.abs(yO-yC),1);ctx.fillStyle=up?'#ef4444':'#10b981';ctx.fillRect(x-cw2/2,bt,cw2,bh)}}}}
ctx.fillStyle='#ccc';ctx.font='10px sans-serif';ctx.textAlign='right';for(var i=0;i<=4;i++){{ctx.fillText(Math.round(rMax*i/4)+'亿',pad.left-6,pad.top+ch*(1-i/4)+4)}}
ctx.textAlign='left';ctx.fillStyle='#86f7dc';for(var i=0;i<=4;i++){{ctx.fillText(Math.round(pm2*i/4)+'元',pad.left+cw+6,pad.top+ch*(1-i/4)+4)}}
ctx.fillStyle='#e2e8f0';ctx.font='11px sans-serif';ctx.textAlign='center';for(var i=0;i<n;i++){{ctx.fillText(d.years[i],xs[i],H-pad.bottom+16)}}
}}();</script></html>"""


@router.get('/report/zxm/{stock_code}', response_class=HTMLResponse)
def report_zxm(stock_code: str):
    from ..zxm_tags import compute_tags
    tags = compute_tags(stock_code)
    if not tags or 'error' in tags:
        return HTMLResponse('<h2>无数据</h2>')

    sname = tags.get('stock_name', stock_code)
    import json

    dims = [
        ('资产结构', [
            ('类型', tags.get('asset_type')), ('资产轻重', tags.get('asset_weight')),
            ('现金', tags.get('cash_status')), ('存货风险', tags.get('inventory_risk')),
            ('合同负债', tags.get('contract_liab_tag')),
        ]),
        ('资本结构', [
            ('造血类型', tags.get('hematopoiesis')),
            ('造血占比', f'{tags.get("hematopoiesis_ratio")}%' if tags.get('hematopoiesis_ratio') is not None else '-'),
            ('杠杆', tags.get('leverage')),
            ('有息负债率', f'{tags.get("debt_ratio")}%' if tags.get('debt_ratio') is not None else '-'),
        ]),
        ('利润质量', [
            ('毛利', tags.get('margin_level')),
            ('核心利润率', f'{tags.get("core_profit_margin")}%' if tags.get('core_profit_margin') is not None else '-'),
            ('利润来源', tags.get('profit_source')),
            ('盈利状态', tags.get('profit_status')),
        ]),
        ('三大匹配', [
            ('固资→营收', tags.get('match_fa_rev')),
            ('营收→核心利润', tags.get('match_rev_profit')),
            ('核心利润→OCF', tags.get('match_profit_ocf')),
        ]),
        ('现金流', [
            ('现金流类型', tags.get('cashflow_type')),
            ('OCF/净利', f'{tags.get("ocf_to_np")}' if tags.get('ocf_to_np') is not None else '-'),
            ('自由现金流', tags.get('fcf_status')),
        ]),
        ('成长性', [
            ('增速', tags.get('growth_rate')),
            ('增长质量', tags.get('growth_quality')),
        ]),
    ]

    risk_flags = tags.get('risk_flags', '[]')
    if isinstance(risk_flags, str):
        try: risk_flags = json.loads(risk_flags)
        except: risk_flags = []

    rating = tags.get('overall_rating', '-')
    pattern = tags.get('pattern_label', '')

    rating_colors = {'优秀': '#22c55e', '良好': '#3b82f6', '中等': '#eab308', '中下': '#f97316', '差': '#ef4444'}
    rc = rating_colors.get(rating, '#666')

    def tag_html(label, val):
        if val is None or val == '未知': return ''
        good = ['造血型','经营主导型','现金充裕','轻资产','零杠杆','低杠杆','高毛利','盈利','价值创造型','产能高效','强转化','中转化','现金实现强','现金奶牛','爆发增长','高速增长','稳健增长','增收增利','优秀','良好','FCF充裕','存货风险低','合同负债高','合同负债正常','现金正常']
        bad = ['输血型','投资主导型','现金紧张','重资产','高杠杆','低毛利','亏损','会计调整型','产能低效','极弱转化','现金实现弱','纸面富贵','失血状态','衰退','减收减利','差','中下','FCF为负','存货风险高','增收不增利']
        cls = 'good' if val in good else ('bad' if val in bad else '')
        return f'<div class="tag {cls}">{label}<span class="tv">{val}</span></div>'

    dim_html = ''
    for dim_name, items in dims:
        items_html = ''.join(tag_html(label, val) for label, val in items)
        dim_html += f'<div class="dim"><div class="dimt">{dim_name}</div>{items_html}</div>'

    risk_html = ''
    if risk_flags:
        risk_html = '<div class="risk">' + ''.join(f'<span class="rt">{r}</span>' for r in risk_flags) + '</div>'

    return f"""<!DOCTYPE html><html lang=zh><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1"><title>{stock_code} {sname} 六维分析</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0d0d1a;color:#ccc;font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:12px}}
h1{{font-size:20px;color:#00d4ff;margin-bottom:4px}}.sub{{font-size:15px;color:#666;margin-bottom:14px}}
.rating{{display:inline-block;padding:6px 18px;border-radius:14px;font-size:18px;font-weight:700;color:#000;background:{rc}}}
.pattern{{margin:10px 0 16px}}.pl{{background:linear-gradient(135deg,#00d4ff,#3b82f6);padding:5px 16px;border-radius:14px;font-size:16px;font-weight:700;color:#000;display:inline-block}}
.grid{{display:grid;grid-template-columns:1fr;gap:10px}}
.dim{{background:rgba(255,255,255,0.03);border-radius:10px;padding:14px;border:1px solid rgba(255,255,255,0.06)}}
.dimt{{font-size:14px;font-weight:600;color:#00d4ff;margin-bottom:8px;letter-spacing:0.5px}}
.tag{{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-radius:8px;font-size:14px;margin:4px 0;background:rgba(255,255,255,0.04);color:#aaa}}
.tag.good{{background:rgba(34,197,94,0.12)}}.tag.good .tv{{color:#22c55e;font-weight:600}}
.tag.bad{{background:rgba(239,68,68,0.12)}}.tag.bad .tv{{color:#ef4444;font-weight:600}}
.tv{{margin-left:4px}}
.risk{{margin-top:10px;display:flex;flex-wrap:wrap;gap:4px}}
.rt{{padding:2px 8px;border-radius:8px;font-size:11px;background:rgba(239,68,68,0.12);color:#ef4444}}
.footer{{margin-top:12px;font-size:10px;color:#444;text-align:center}}
</style>
<div><h1>{stock_code} {sname}</h1><div class=sub><span class=rating>{rating}</span> <span class=pl>{pattern}</span></div></div>
<div class=grid>{dim_html}</div>{risk_html}
<div class=footer>六维分析方法论财务诊断 v1.0 · 数据基于最新年报</div></html>"""
