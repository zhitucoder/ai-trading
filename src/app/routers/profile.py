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

    sort_col = 'p.tech_score'
    if body.sort_by in ('fund_score', 'revenue_growth', 'net_profit_growth', 'price_change_pct'):
        sort_col = f'p.{body.sort_by}'
    sort_dir = 'DESC' if body.sort_order == 'desc' else 'ASC'
    offset = (body.page - 1) * body.page_size
    limit = body.page_size

    where = ' AND '.join(conditions)
    latest = query("SELECT MAX(data_date) AS d FROM stock_profiles")[0]['d']

    count_sql = f"SELECT COUNT(*) AS c FROM stock_profiles p WHERE p.data_date = %(ldate)s AND {where}"
    count_params = {'ldate': str(latest), **params}
    total = query(count_sql, count_params)[0]['c']

    tag_cols_sql = ', '.join(f'p.{c}' for c in TAG_COLUMNS)
    sql = f"""
        SELECT p.stock_code, p.stock_name, p.latest_price, p.price_change_pct,
               p.stage_id, p.stage_confidence, p.tech_score, p.fund_score,
               p.revenue_growth, p.net_profit_growth, p.debt_ratio,
               {tag_cols_sql}
        FROM stock_profiles p
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
