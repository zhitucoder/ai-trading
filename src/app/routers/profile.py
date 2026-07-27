import json
import threading
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from ..database import query, execute
from ..strategies.profile import generate_profile
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
            return json.loads(raw) if isinstance(raw, str) else raw
    return generate_profile(stock_code)


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
    zxm_asset_weight: Optional[str] = None
    zxm_hematopoiesis: Optional[str] = None
    zxm_margin_level: Optional[str] = None
    zxm_cashflow_type: Optional[str] = None
    zxm_growth_rate: Optional[str] = None
    zxm_growth_quality: Optional[str] = None
    zxm_leverage: Optional[str] = None
    zxm_overall_rating: Optional[str] = None
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

    sort_col = 'p.tech_score'
    if body.sort_by in ('fund_score', 'revenue_growth', 'net_profit_growth', 'price_change_pct', 'contract_liab_to_assets',
                         'rev_cagr_3y', 'rev_cagr_5y', 'rev_cagr_10y',
                         'profit_cagr_3y', 'profit_cagr_5y', 'profit_cagr_10y'):
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
