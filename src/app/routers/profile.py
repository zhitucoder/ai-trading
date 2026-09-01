import json
import io
import threading
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
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
    ads = query("SELECT market_cap FROM ads_stock_latest WHERE stock_code = %s", [stock_code])
    if ads and ads[0]:
        data['market_cap'] = float(ads[0]['market_cap']) if ads[0]['market_cap'] is not None else None
        if data.get('fin_data') is None:
            data['fin_data'] = {}
        data['fin_data']['market_cap'] = data['market_cap']
    net_margin_row = query("SELECT net_margin FROM stock_profiles WHERE stock_code = %s AND net_margin IS NOT NULL ORDER BY data_date DESC LIMIT 1", [stock_code])
    if net_margin_row and net_margin_row[0].get('net_margin') is not None:
        data['net_margin'] = float(net_margin_row[0]['net_margin'])
        if data.get('fin_data') is None:
            data['fin_data'] = {}
        data['fin_data']['net_margin'] = data['net_margin']
    annual_margin = query("""
        SELECT operating_revenue, operating_cost, parent_net_profit
        FROM fin_income WHERE stock_code = %s AND MONTH(report_date)=12 AND DAY(report_date)=31
        ORDER BY report_date DESC LIMIT 1
    """, [stock_code])
    if annual_margin and annual_margin[0].get('operating_revenue'):
        _rev25 = float(annual_margin[0]['operating_revenue'])
        if _rev25 > 0:
            _cost25 = float(annual_margin[0]['operating_cost']) if annual_margin[0].get('operating_cost') is not None else 0
            _pnp25 = float(annual_margin[0]['parent_net_profit']) if annual_margin[0].get('parent_net_profit') is not None else 0
            if data.get('fin_data') is None:
                data['fin_data'] = {}
            data['fin_data']['gross_margin_2025'] = round((_rev25 - _cost25) / _rev25 * 100, 2)
            data['fin_data']['net_margin_2025'] = round(_pnp25 / _rev25 * 100, 2)
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

    fund_rows = query("""
        SELECT end_date, quarter, report_type, fund_count, active_count, passive_count,
               total_amount, total_mkv, close_price, intra_high
        FROM ads_stock_fund
        WHERE stock_code = %s
        ORDER BY end_date
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
                             for r in kline_rows],
            'fund_series': [{'end_date': r['end_date'].strftime('%Y-%m-%d') if hasattr(r['end_date'], 'strftime') else str(r['end_date'])[:10],
                             'quarter': r['quarter'], 'report_type': r['report_type'],
                             'fund_count': r['fund_count'] or 0,
                             'active_count': r['active_count'] or 0,
                             'passive_count': r['passive_count'] or 0,
                             'total_amount': float(r['total_amount'] or 0),
                             'total_mkv': float(r['total_mkv'] or 0),
                             'close_price': float(r['close_price'] or 0),
                             'intra_high': float(r['intra_high'] or 0)}
                            for r in fund_rows]}


# ── 融资融券与股价关系图数据 ──
@router.get('/profile/{stock_code}/margin-chart')
def profile_margin_chart(stock_code: str):
    three_years_ago = (datetime.now().replace(year=datetime.now().year - 3)).strftime('%Y%m%d')

    ex_row = query("SELECT exchange FROM stocks WHERE stock_code = %s", [stock_code])
    ts_code = None
    if ex_row and ex_row[0]['exchange']:
        suffix = '.SH' if ex_row[0]['exchange'].upper() == 'SH' else '.SZ'
        ts_code = stock_code + suffix

    margin_rows = []
    if ts_code:
        margin_rows = query("""
            SELECT trade_date, rzye, rqye
            FROM margin_detail
            WHERE ts_code = %s AND trade_date >= %s
            ORDER BY trade_date
        """, [ts_code, three_years_ago])

    kline_rows = query("""
        SELECT trade_date, close_price
        FROM daily_kline
        WHERE stock_code = %s AND trade_date >= %s
        ORDER BY trade_date
    """, [stock_code, three_years_ago.replace('-', '')])

    sampled_margin = []
    for i, r in enumerate(margin_rows):
        if i % 5 == 0:
            td = r['trade_date']
            if hasattr(td, 'strftime'):
                td_str = td.strftime('%Y%m%d')
            else:
                td_str = str(td).replace('-', '')
            sampled_margin.append({
                'date': td_str,
                'rzye': float(r['rzye'] or 0) / 1e8,
                'rqye': float(r['rqye'] or 0) / 1e8,
            })

    kline_data = []
    for r in kline_rows:
        td = r['trade_date']
        if hasattr(td, 'strftime'):
            td_str = td.strftime('%Y%m%d')
        else:
            td_str = str(td).replace('-', '')
        kline_data.append({
            'date': td_str,
            'close': float(r['close_price'] or 0),
        })

    return {
        'margin': sampled_margin,
        'kline': kline_data,
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
    prev_year_profit_min: Optional[float] = None
    prev_year_profit_max: Optional[float] = None
    cur_quarter_profit_min: Optional[float] = None
    cur_quarter_profit_max: Optional[float] = None
    debt_ratio_max: Optional[float] = None
    price_change_min: Optional[float] = None
    price_change_max: Optional[float] = None
    gm_growth_q_min: Optional[float] = None
    gm_growth_2y_min: Optional[float] = None
    contract_liab_min: Optional[float] = None
    contract_liab_max: Optional[float] = None
    receivable_to_revenue_min: Optional[float] = None
    receivable_to_revenue_max: Optional[float] = None
    receivable_to_assets_min: Optional[float] = None
    receivable_to_assets_max: Optional[float] = None
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
    net_margin_min: Optional[float] = None
    net_margin_max: Optional[float] = None
    gm_2025_min: Optional[float] = None
    gm_2025_max: Optional[float] = None
    net_margin_2025_min: Optional[float] = None
    net_margin_2025_max: Optional[float] = None
    market_cap_min: Optional[float] = None
    market_cap_max: Optional[float] = None
    pe_max: Optional[float] = None
    peg_max: Optional[float] = None
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
    fund_recent8_up_min: Optional[int] = None
    fund_recent8_net_min: Optional[int] = None
    fund_recent6_up_min: Optional[int] = None
    fund_recent4_up_min: Optional[int] = None
    fund_consec_growth_min: Optional[int] = None
    fund_consec_decline_min: Optional[int] = None
    recent2q_fund_count_min: Optional[int] = None
    recent2q_fund_count_max: Optional[int] = None
    recent4q_fund_count_min: Optional[int] = None
    recent4q_fund_count_max: Optional[int] = None
    recent1q_fund_count_min: Optional[int] = None
    recent1q_fund_count_max: Optional[int] = None
    recent8q_amount_min: Optional[float] = None
    fund_holding_growth_min: Optional[float] = None
    fund_holding_growth_max: Optional[float] = None
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
    if body.prev_year_profit_min is not None:
        conditions.append('fy.parent_net_profit IS NOT NULL AND fy.parent_net_profit >= %(prev_year_profit_min)s')
        params['prev_year_profit_min'] = body.prev_year_profit_min
    if body.prev_year_profit_max is not None:
        conditions.append('fy.parent_net_profit IS NOT NULL AND fy.parent_net_profit < %(prev_year_profit_max)s')
        params['prev_year_profit_max'] = body.prev_year_profit_max
    if body.cur_quarter_profit_min is not None:
        conditions.append('fq.parent_net_profit IS NOT NULL AND fq.parent_net_profit >= %(cur_quarter_profit_min)s')
        params['cur_quarter_profit_min'] = body.cur_quarter_profit_min
    if body.cur_quarter_profit_max is not None:
        conditions.append('fq.parent_net_profit IS NOT NULL AND fq.parent_net_profit < %(cur_quarter_profit_max)s')
        params['cur_quarter_profit_max'] = body.cur_quarter_profit_max
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

    for field, key in (('receivable_to_revenue_min', 'receivable_to_revenue'),
                       ('receivable_to_revenue_max', 'receivable_to_revenue'),
                       ('receivable_to_assets_min', 'receivable_to_assets'),
                       ('receivable_to_assets_max', 'receivable_to_assets')):
        val = getattr(body, field, None)
        if val is not None:
            if field.endswith('_min'):
                conditions.append(f"JSON_EXTRACT(p.profile_json, '$.fin_data.{key}') >= %({field})s")
            else:
                conditions.append(f"(JSON_EXTRACT(p.profile_json, '$.fin_data.{key}') IS NULL OR JSON_EXTRACT(p.profile_json, '$.fin_data.{key}') <= %({field})s)")
            params[field] = val

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

    ads_join = 'JOIN ads_stock_latest a ON a.stock_code = p.stock_code'
    has_ads = any(getattr(body, f, None) is not None for f in ('market_cap_min', 'market_cap_max'))
    if not has_ads and body.sort_by in ('market_cap', 'net_margin'):
        has_ads = True

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

    if body.net_margin_min is not None or body.net_margin_max is not None:
        conditions.append('p.net_margin IS NOT NULL')
    if body.net_margin_min is not None:
        conditions.append('p.net_margin >= %(net_margin_min)s')
        params['net_margin_min'] = body.net_margin_min
    if body.net_margin_max is not None:
        conditions.append('p.net_margin <= %(net_margin_max)s')
        params['net_margin_max'] = body.net_margin_max
    if body.gm_2025_min is not None or body.gm_2025_max is not None or \
       body.net_margin_2025_min is not None or body.net_margin_2025_max is not None:
        conditions.append('fy.operating_revenue IS NOT NULL')
    if body.gm_2025_min is not None:
        conditions.append('(fy.operating_revenue - fy.operating_cost) / NULLIF(fy.operating_revenue, 0) * 100 >= %(gm_2025_min)s')
        params['gm_2025_min'] = body.gm_2025_min
    if body.gm_2025_max is not None:
        conditions.append('(fy.operating_revenue - fy.operating_cost) / NULLIF(fy.operating_revenue, 0) * 100 <= %(gm_2025_max)s')
        params['gm_2025_max'] = body.gm_2025_max
    if body.net_margin_2025_min is not None:
        conditions.append('fy.parent_net_profit / NULLIF(fy.operating_revenue, 0) * 100 >= %(net_margin_2025_min)s')
        params['net_margin_2025_min'] = body.net_margin_2025_min
    if body.net_margin_2025_max is not None:
        conditions.append('fy.parent_net_profit / NULLIF(fy.operating_revenue, 0) * 100 <= %(net_margin_2025_max)s')
        params['net_margin_2025_max'] = body.net_margin_2025_max
    if body.market_cap_min is not None:
        conditions.append('a.market_cap IS NOT NULL AND a.market_cap >= %(market_cap_min)s')
        params['market_cap_min'] = body.market_cap_min
    if body.market_cap_max is not None:
        conditions.append('a.market_cap IS NOT NULL AND a.market_cap <= %(market_cap_max)s')
        params['market_cap_max'] = body.market_cap_max

    if body.pe_max is not None:
        conditions.append('p.pe_ttm IS NOT NULL AND p.pe_ttm <= %(pe_max)s')
        params['pe_max'] = body.pe_max
    if body.peg_max is not None:
        conditions.append('p.peg IS NOT NULL AND p.peg <= %(peg_max)s')
        params['peg_max'] = body.peg_max

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

    fund_trend_fields = [
        ('fund_recent8_up_min', 'recent8_up', '>='),
        ('fund_recent8_net_min', 'recent8_net', '>='),
        ('fund_recent6_up_min', 'recent6_up', '>='),
        ('fund_recent4_up_min', 'recent4_up', '>='),
        ('fund_consec_growth_min', 'max_consec_growth', '>='),
        ('fund_consec_decline_min', 'max_consec_decline', '>='),
        ('recent2q_fund_count_min', 'recent2q_fund_count', '>='),
        ('recent2q_fund_count_max', 'recent2q_fund_count', '<='),
        ('recent4q_fund_count_min', 'recent4q_fund_count', '>='),
        ('recent4q_fund_count_max', 'recent4q_fund_count', '<='),
        ('recent1q_fund_count_min', 'recent1q_fund_count', '>='),
        ('recent1q_fund_count_max', 'recent1q_fund_count', '<='),
        ('recent8q_amount_min', 'recent8q_amount', '>='),
        ('fund_holding_growth_min', 'recent1q_fund_growth', '>='),
        ('fund_holding_growth_max', 'recent1q_fund_growth', '<='),
    ]
    has_fund_trend = any(getattr(body, f, None) is not None for f, _, _ in fund_trend_fields)
    fund_trend_join = ''
    for field, col, op in fund_trend_fields:
        val = getattr(body, field, None)
        if val is not None:
            conditions.append(f'ft.{col} IS NOT NULL AND ft.{col} {op} %({field})s')
            params[field] = val

    sort_col = 'p.tech_score'
    if body.sort_by in ('fund_score', 'revenue_growth', 'net_profit_growth', 'price_change_pct', 'dividend_yield',
                         'contract_liab_to_assets',
                         'receivable_to_revenue', 'receivable_to_assets',
                         'rev_cagr_3y', 'rev_cagr_5y', 'rev_cagr_10y',
                         'profit_cagr_3y', 'profit_cagr_5y', 'profit_cagr_10y', 'roe', 'roe_ttm', 'gross_margin',
                         'pe_ttm', 'peg', 'price_cagr_3y', 'divergence'):
        if body.sort_by == 'contract_liab_to_assets':
            sort_col = "CAST(JSON_EXTRACT(p.profile_json, '$.fin_data.contract_liab_to_assets') AS DECIMAL(10,2))"
        elif body.sort_by == 'receivable_to_revenue':
            sort_col = "CAST(JSON_EXTRACT(p.profile_json, '$.fin_data.receivable_to_revenue') AS DECIMAL(10,2))"
        elif body.sort_by == 'receivable_to_assets':
            sort_col = "CAST(JSON_EXTRACT(p.profile_json, '$.fin_data.receivable_to_assets') AS DECIMAL(10,2))"
        else:
            sort_col = f'p.{body.sort_by}'
    elif body.sort_by in ('net_margin',):
        sort_col = 'p.net_margin'
    elif body.sort_by == 'net_margin_2025':
        sort_col = 'fy.parent_net_profit / NULLIF(fy.operating_revenue, 0) * 100'
    elif body.sort_by == 'gm_2025':
        sort_col = '(fy.operating_revenue - fy.operating_cost) / NULLIF(fy.operating_revenue, 0) * 100'
    elif body.sort_by == 'market_cap':
        sort_col = 'a.market_cap'
    elif body.sort_by in ('prev_year_profit',):
        sort_col = 'fy.parent_net_profit'
    elif body.sort_by == 'cur_quarter_profit':
        sort_col = 'fq.parent_net_profit'
    elif body.sort_by in ('recent8_up', 'recent8_net', 'max_consec_growth',
                          'recent2q_fund_count', 'recent4q_fund_count',
                          'recent1q_fund_count', 'fc26Q2',
                          'recent8q_amount', 'recent1q_fund_growth'):
        sort_col = f'ft.{body.sort_by}'
    elif body.sort_by in zxm_field_map:
        sort_col = f'z.{zxm_field_map[body.sort_by]}'
    sort_dir = 'DESC' if body.sort_order == 'desc' else 'ASC'
    offset = (body.page - 1) * body.page_size
    limit = body.page_size

    where = ' AND '.join(conditions)
    latest = query("SELECT MAX(data_date) AS d FROM stock_profiles")[0]['d']
    cur_q_row = query("""
        SELECT report_date AS d FROM fin_ratios
        GROUP BY report_date HAVING COUNT(*) > 1000
        ORDER BY report_date DESC LIMIT 1
    """)
    cur_q = cur_q_row[0]['d'] if cur_q_row else None
    prev_yr = f'{cur_q.year - 1}-12-31' if cur_q else None

    profit_join = ''
    if cur_q and prev_yr:
        profit_join = (f"LEFT JOIN fin_income fy ON fy.stock_code = p.stock_code AND fy.report_date = %(prev_yr)s "
                       f"LEFT JOIN fin_income fq ON fq.stock_code = p.stock_code AND fq.report_date = %(cur_q)s")

    join_clause = zxm_join
    if has_ads:
        join_clause = (zxm_join + ' ' + ads_join).strip()
    if profit_join:
        join_clause = (join_clause + ' ' + profit_join).strip()
    join_clause = (join_clause + ' LEFT JOIN ads_stock_fund_trend ft ON ft.stock_code = p.stock_code').strip()
    count_sql = f"SELECT COUNT(*) AS c FROM stock_profiles p {join_clause} WHERE p.data_date = %(ldate)s AND {where}"
    count_params = {'ldate': str(latest), 'prev_yr': str(prev_yr), 'cur_q': str(cur_q), **params}
    total = query(count_sql, count_params)[0]['c']

    tag_cols_sql = ', '.join(f'p.{c}' for c in TAG_COLUMNS)
    zxm_select = ', '.join(f'z.{db_col} AS {body_field}' for body_field, db_col in zxm_field_map.items()) if has_zxm else ''
    ads_select = ', a.market_cap AS market_cap' if has_ads else ''
    profit_select = (', fy.parent_net_profit AS prev_year_profit, fq.parent_net_profit AS cur_quarter_profit, '
                     '(fy.operating_revenue - fy.operating_cost) / NULLIF(fy.operating_revenue, 0) * 100 AS gm_2025, '
                     'fy.parent_net_profit / NULLIF(fy.operating_revenue, 0) * 100 AS net_margin_2025') if profit_join else ''
    fund_trend_select = (', ft.recent8_up, ft.recent8_net, ft.max_consec_growth, ft.max_consec_decline, '
                         'ft.recent2q_fund_count, ft.recent4q_fund_count, ft.recent1q_fund_count, '
                         'ft.fc25Q4, ft.fc26Q2, ft.recent8q_amount, ft.recent1q_fund_growth')
    sql = f"""
        SELECT p.stock_code, p.stock_name, p.latest_price, p.price_change_pct,
               p.stage_id, p.stage_confidence, p.tech_score, p.fund_score,
               p.revenue_growth, p.net_profit_growth, p.debt_ratio,
               p.roe, p.roe_ttm, p.gross_margin, p.prev_year_revenue,
               p.pe_ttm, p.peg,
               p.net_margin AS net_margin,
               p.dividend_yield,
               p.rev_cagr_3y, p.rev_cagr_5y, p.rev_cagr_10y,
               p.profit_cagr_3y, p.profit_cagr_5y, p.profit_cagr_10y,
               p.price_cagr_3y, p.divergence,
               JSON_EXTRACT(p.profile_json, '$.fin_data.contract_liab_to_assets') AS contract_liab_to_assets,
               JSON_EXTRACT(p.profile_json, '$.fin_data.receivable_to_revenue') AS receivable_to_revenue,
               JSON_EXTRACT(p.profile_json, '$.fin_data.receivable_to_assets') AS receivable_to_assets,
               {tag_cols_sql}
               {',' + zxm_select if zxm_select else ''}
               {ads_select}
               {profit_select}
               {fund_trend_select}
        FROM stock_profiles p {join_clause}
        WHERE p.data_date = %(ldate)s AND {where}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %(lo)s OFFSET %(of)s
    """
    data_params = {'ldate': str(latest), 'lo': limit, 'of': offset, 'prev_yr': str(prev_yr), 'cur_q': str(cur_q), **params}
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


@router.get('/dividends/tushare/list')
def list_dividends_tushare(year: Optional[int] = None, sort: str = 'ex_date',
                           order: str = 'desc', page: int = 1, page_size: int = 50):
    where = []
    params = {}
    if year:
        where.append('d.ex_date LIKE %(year)s')
        params['year'] = f'{year}%'
    if sort not in ('ex_date', 'end_date', 'cash_div_tax'):
        sort = 'ex_date'
    sort_col = f'd.{sort}'
    sort_dir = 'DESC' if order == 'desc' else 'ASC'

    where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''
    total = query(f"SELECT COUNT(*) AS c FROM dividend_tushare d{where_sql}", params)[0]['c']
    offset = (page - 1) * page_size
    rows = query(f"""
        SELECT d.ts_code, s.stock_name, d.end_date, d.div_proc, d.cash_div_tax,
               d.cash_div, d.stk_bo_rate, d.stk_co_rate, d.stk_div,
               d.ex_date, d.record_date, d.ann_date, d.pay_date
        FROM dividend_tushare d
        LEFT JOIN stocks s ON s.stock_code = SUBSTRING_INDEX(d.ts_code, '.', 1)
        {where_sql}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %(lo)s OFFSET %(of)s
    """, {**params, 'lo': page_size, 'of': offset})

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
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0d0d1a;color:#ccc;font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:16px}}h1{{font-size:16px;color:#00d4ff;margin-bottom:4px}}.sub{{font-size:12px;color:#ccc;margin-bottom:12px}}#chart{{width:100%;height:300px;background:#131322;border-radius:10px;border:1px solid #1e1e35;position:relative}}canvas{{width:100%;height:100%}}.legend{{display:flex;gap:16px;margin-top:8px;font-size:11px;color:#ccc;flex-wrap:wrap}}.foot{{margin-top:10px;font-size:13px;color:#999;text-align:left}}.foot .repo{{color:#e2b714}}</style>
<div><h1>{stock_code} {sname}</h1><div class=sub>营收·净利润·净利增长率·股价趋势</div></div>
<div id=chart><canvas id=c></canvas></div>
<div class=legend><span style=color:#6495ed>■ 营收(亿)</span><span style=color:#ffd700>■ 净利润(亿)</span><span style=color:#ff6b6b>■ 净利增长率%</span><span style=color:#4ecdc4>■ 周K</span></div>
<div class=foot><span class=repo>零基础 学AI量化/财报分析 详情 -></span>　本图由系统 <span class=repo>gitee.com/zhitucoder/ai-trading</span> 生成</div>
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


# ── 上市公司股份回购方案列表 API ──
PROGRESS_MAP = {
    '001': '董事会预案', '002': '股东大会通过', '003': '回购实施中',
    '004': '回购完成', '005': '已终止', '006': '回购完成(注销)',
    '007': '回购实施中', '008': '回购完成',
}


@router.get('/buyback/list')
def buyback_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    keyword: str = Query(''),
    progress: str = Query(''),
    purpose: str = Query(''),
    progress_status: str = Query(''),
    sort: str = Query('notice_date'),
    order: str = Query('desc'),
):
    """返回 stock_buyback_dfcf 表中的回购方案列表（不含逐日回购明细）。

    purpose: ''=全部, 'cancel'=注销目的, 'other'=其它目的
    progress_status: ''=全部, 'ongoing'=进行中, 'done'=已完成
    """
    sort_cols = {
        'notice_date': 'notice_date', 'repur_start_date': 'repur_start_date',
        'repur_end_date': 'repur_end_date', 'repur_num_cap': 'repur_num_cap',
        'repur_num_lower': 'repur_num_lower', 'repur_amount_lower': 'repur_amount_lower',
        'repur_amount_limit': 'repur_amount_limit',
        'repur_num': 'repur_num', 'repur_amount': 'repur_amount',
    }
    sort_sql = sort_cols.get(sort, 'notice_date')
    order_sql = 'ASC' if order.lower() == 'asc' else 'DESC'

    ONGOING = ("'001'", "'002'", "'003'", "'007'")
    DONE = ("'004'", "'006'", "'008'")

    where, params = [], []
    if keyword:
        where.append('(stock_code LIKE %s OR stock_name LIKE %s)')
        params += [f'%{keyword}%', f'%{keyword}%']
    if progress:
        where.append('repur_progress = %s')
        params.append(progress)
    if purpose == 'cancel':
        where.append('repur_objective LIKE %s')
        params.append('%注销%')
    elif purpose == 'other':
        where.append('(repur_objective IS NULL OR repur_objective NOT LIKE %s)')
        params.append('%注销%')
    if progress_status == 'ongoing':
        where.append(f'repur_progress IN ({",".join(ONGOING)})')
    elif progress_status == 'done':
        where.append(f'repur_progress IN ({",".join(DONE)})')
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    total = query(f"SELECT COUNT(*) n FROM stock_buyback_dfcf {where_sql}", params)[0]['n']
    offset = (page - 1) * page_size
    rows = query(
        f"""SELECT repur_code, stock_code, stock_name, repur_objective, share_type,
                   repur_progress, repur_num, repur_num_lower, repur_num_cap,
                   repur_amount, repur_amount_lower, repur_amount_limit,
                   repur_price_lower, repur_price_cap,
                   repur_start_date, repur_end_date, notice_date, finish_date
            FROM stock_buyback_dfcf {where_sql}
            ORDER BY {sort_sql} {order_sql}
            LIMIT %s OFFSET %s""",
        params + [page_size, offset])

    prog_rows = query(
        "SELECT repur_progress, COUNT(*) n FROM stock_buyback_dfcf GROUP BY repur_progress ORDER BY n DESC")
    progress_options = [{'code': r['repur_progress'],
                         'label': PROGRESS_MAP.get(r['repur_progress'], r['repur_progress']),
                         'count': r['n']} for r in prog_rows]

    def fmt(v):
        return str(v) if v is not None else None

    out = []
    for r in rows:
        out.append({
            'repur_code': r['repur_code'],
            'stock_code': r['stock_code'],
            'stock_name': r['stock_name'],
            'repur_objective': r['repur_objective'],
            'share_type': r['share_type'],
            'repur_progress': r['repur_progress'],
            'repur_progress_label': PROGRESS_MAP.get(r['repur_progress'], r['repur_progress']),
            'repur_num': r['repur_num'],
            'repur_num_lower': r['repur_num_lower'],
            'repur_num_cap': r['repur_num_cap'],
            'repur_amount': r['repur_amount'],
            'repur_amount_lower': r['repur_amount_lower'],
            'repur_amount_limit': r['repur_amount_limit'],
            'repur_price_lower': r['repur_price_lower'],
            'repur_price_cap': r['repur_price_cap'],
            'repur_start_date': fmt(r['repur_start_date']),
            'repur_end_date': fmt(r['repur_end_date']),
            'notice_date': fmt(r['notice_date']),
            'finish_date': fmt(r['finish_date']),
        })
    return {'total': total, 'page': page, 'page_size': page_size,
            'progress_options': progress_options, 'rows': out}


# ── 股份回购方案 独立展示页面（点击个股跳转至六维分析画像） ──
@router.get('/report/buyback', response_class=HTMLResponse)
def report_buyback():
    return _BUYBACK_HTML


_BUYBACK_HTML = """<!DOCTYPE html><html lang=zh><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1"><title>上市公司股份回购</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0d0d1a;color:#ccc;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;padding:14px}
h1{font-size:18px;color:#00d4ff;margin-bottom:2px}.sub{font-size:12px;color:#888;margin-bottom:12px}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
.bar input,.bar select{background:#131322;border:1px solid #2a2a45;color:#ccc;border-radius:8px;padding:7px 10px;font-size:13px;outline:none}
.bar input{min-width:140px}
.btn{background:#1e2a4a;border:1px solid #2a3a6a;color:#9cc4ff;border-radius:8px;padding:7px 14px;font-size:13px;cursor:pointer}
.btn:hover{background:#243456}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.tab{padding:5px 12px;border-radius:12px;font-size:12px;background:#131322;border:1px solid #2a2a45;color:#aaa;cursor:pointer}
.tab.on{background:#1e2a4a;color:#00d4ff;border-color:#2a4a7a}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:8px 6px;text-align:left;border-bottom:1px solid #1a1a30;vertical-align:top}
th{color:#8aa;font-weight:600;position:sticky;top:0;background:#0d0d1a;cursor:pointer;white-space:nowrap}
th .ar{color:#00d4ff;font-size:10px}
a.lk{color:#7db4ff;text-decoration:none}
a.lk:hover{text-decoration:underline}
.purpose{color:#bbb;line-height:1.4;max-width:340px}
.qty{color:#ffd700;white-space:nowrap}
.muted{color:#777}
.pg{display:flex;gap:10px;align-items:center;justify-content:center;margin-top:14px}
.pg button{background:#131322;border:1px solid #2a2a45;color:#9cc4ff;border-radius:8px;padding:6px 14px;cursor:pointer}
.pg button:disabled{opacity:.4;cursor:default}
.pginfo{font-size:12px;color:#888}
.badge{display:inline-block;padding:2px 8px;border-radius:8px;font-size:11px}
.b-done{background:rgba(34,197,94,0.15);color:#22c55e}
.b-doing{background:rgba(59,130,246,0.15);color:#3b82f6}
.b-plan{background:rgba(234,179,8,0.15);color:#eab308}
.b-stop{background:rgba(239,68,68,0.15);color:#ef4444}
.foot{margin-top:14px;font-size:10px;color:#444;text-align:center}
</style>
<div><h1>上市公司股份回购</h1><div class=sub>数据来源：东方财富数据中心 · 点击个股名称跳转六维画像</div></div>
<div class=bar>
  <input id=kw placeholder="搜索代码/名称" onkeydown="if(event.key==='Enter')load(1)">
  <select id=prog><option value="">全部进度</option></select>
  <button class=btn onclick="load(1)">查询</button>
</div>
<div class=tabs id=tabs></div>
<div style="overflow-x:auto"><table id=tb><thead><tr>
  <th onclick="sortBy('notice_date')">公告日 <span class=ar id=ar_notice_date></span></th>
  <th>股票</th>
  <th>回购目的</th>
  <th onclick="sortBy('repur_num_cap')">回购数量(股) <span class=ar id=ar_repur_num_cap></span></th>
  <th>回购金额(元)</th>
  <th>回购期限</th>
  <th>进度</th>
</tr></thead><tbody id=bd></tbody></table></div>
<div class=pg><button id=prev onclick="go(-1)">上一页</button><span class=pginfo id=pgi></span><button id=next onclick="go(1)">下一页</button></div>
<div class=foot>东方财富股份回购方案数据 · 系统 gitee.com/zhitucoder/ai-trading 生成</div>
<script>
var page=1, total=0, sort='notice_date', order='desc';
var fmtN=function(v){return v==null?'—':Number(v).toLocaleString('zh-CN')};
var fmtY=function(v){return v==null?'—':(Number(v)/1e8).toFixed(2)+'亿'};
function cls(p){if(p==='004'||p==='006'||p==='008')return 'b-done';if(p==='003'||p==='007')return 'b-doing';if(p==='005')return 'b-stop';return 'b-plan'}
function load(p){
  page=p||page;
  var kw=document.getElementById('kw').value.trim();
  var pr=document.getElementById('prog').value;
  var u='/api/buyback/list?page='+page+'&page_size=50&sort='+sort+'&order='+order+'&keyword='+encodeURIComponent(kw)+'&progress='+encodeURIComponent(pr);
  fetch(u).then(r=>r.json()).then(d=>{
    total=d.total;
    var html='';
    d.rows.forEach(function(r){
      var qty=(r.repur_num_lower!=null||r.repur_num_cap!=null)?(fmtN(r.repur_num_lower)+' ~ '+fmtN(r.repur_num_cap)):fmtN(r.repur_num);
      var amt=(r.repur_amount_lower!=null||r.repur_amount_limit!=null)?(fmtY(r.repur_amount_lower)+' ~ '+fmtY(r.repur_amount_limit)):fmtY(r.repur_amount);
      var per=(r.repur_start_date||'—')+' ~ '+(r.repur_end_date||'—');
      var obj=(r.repur_objective||'').replace(/[\\r\\n]+/g,' ');
      if(obj.length>60)obj=obj.slice(0,60)+'…';
      html+='<tr><td class=muted>'+(r.notice_date||'—')+'</td>'+
        '<td><a class=lk href="/api/report/zxm/'+r.stock_code+'" target="_blank">'+r.stock_code+'<br>'+r.stock_name+'</a></td>'+
        '<td class=purpose>'+obj+'</td>'+
        '<td class=qty>'+qty+'</td>'+
        '<td class=muted>'+amt+'</td>'+
        '<td class=muted>'+per+'</td>'+
        '<td><span class="badge '+cls(r.repur_progress)+'">'+r.repur_progress_label+'</span></td></tr>';
    });
    document.getElementById('bd').innerHTML=html;
    var tp=Math.ceil(total/50)||1;
    document.getElementById('pgi').textContent='第 '+page+' / '+tp+' 页 · 共 '+total+' 条';
    document.getElementById('prev').disabled=page<=1;
    document.getElementById('next').disabled=page>=tp;
    ['notice_date','repur_num_cap'].forEach(function(k){document.getElementById('ar_'+k).textContent='';});
    document.getElementById('ar_'+sort).textContent=order==='desc'?'▼':'▲';
  });
}
function go(d){var tp=Math.ceil(total/50)||1;var p=Math.min(tp,Math.max(1,page+d));if(p!==page)load(p);}
function sortBy(k){if(sort===k){order=order==='desc'?'asc':'desc'}else{sort=k;order='desc'}load(page);}
function loadTabs(){
  fetch('/api/buyback/list?page_size=1').then(r=>r.json()).then(d=>{
    var t=document.getElementById('tabs');var h='';
    h+='<span class="tab on" data-p="" onclick="pickTab(this,\'\')">全部 ('+d.total+')</span>';
    d.progress_options.forEach(function(o){h+='<span class="tab" data-p="'+o.code+'" onclick="pickTab(this,\''+o.code+'\')">'+o.label+' ('+o.count+')</span>';});
    t.innerHTML=h;
  });
}
function pickTab(el,p){document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('on')});el.classList.add('on');document.getElementById('prog').value=p;load(1);}
loadTabs();load(1);
</script></html>"""


# ── 基金持仓与股价联动 matplotlib 图（复用 fund-holding-analysis skill 画法） ──
_matplotlib_loaded = False
_plt = None


def _ensure_matplotlib():
    global _matplotlib_loaded, _plt
    if _matplotlib_loaded:
        return _plt
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    for f in ['/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
              '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc']:
        try:
            fm.fontManager.addfont(f)
            plt.rcParams['font.family'] = fm.FontProperties(fname=f).get_name()
            break
        except Exception:
            pass
    plt.rcParams['axes.unicode_minus'] = False
    _plt = plt
    _matplotlib_loaded = True
    return _plt


@router.get('/profile/{stock_code}/fund-chart-img')
def profile_fund_chart_img(stock_code: str, width: int = 760):
    """返回 matplotlib 三面板 PNG（复用 fund-holding-analysis skill 画法）：
    上=股价(收盘+盘中高点)，中=持仓基金家数，下=基金持股量柱。
    数据来源：ads_stock_fund 预计算表。"""
    rows = query(
        "SELECT end_date, quarter, report_type, fund_count, total_amount, "
        "close_price, intra_high FROM ads_stock_fund "
        "WHERE stock_code=%s ORDER BY end_date", [stock_code])
    if not rows:
        raise HTTPException(404, 'ads_stock_fund 无数据，请先运行分析预计算更新')
    if len(rows) < 2:
        raise HTTPException(404, '数据不足 2 个报告期')
    name = ''
    r = query("SELECT stock_name FROM stocks WHERE stock_code=%s", [stock_code])
    if r:
        name = r[0].get('stock_name') or ''
    suffix = 'SH' if stock_code.startswith('6') else 'SZ'

    plt = _ensure_matplotlib()
    ends = [str(x['end_date']) for x in rows]
    labels = [x['quarter'] for x in rows]
    is_full = [x['report_type'] != 'Q' for x in rows]
    prices = [float(x['close_price'] or 0) for x in rows]
    highs = [float(x['intra_high'] or 0) for x in rows]
    funds = [int(x['fund_count'] or 0) for x in rows]
    shares = [float(x['total_amount'] or 0) / 1e8 for x in rows]

    x = list(range(len(rows)))
    fig, axes = plt.subplots(3, 1, figsize=(10.5, 6.8), sharex=True,
                             gridspec_kw={'height_ratios': [1.1, 1, 1]})
    fig.patch.set_facecolor('#ffffff')

    ax = axes[0]
    ax.plot(x, prices, color='#e23b3b', lw=2.2, marker='o', ms=5, zorder=3,
            label='季度末收盘价(不复权)')
    ax.scatter(x, highs, color='#ff8c1a', marker='^', s=55, zorder=4,
               label='季度内盘中最高(不复权)')
    ax.set_ylabel('股价 (元)', fontsize=10)
    ax.set_title(f'{name}({stock_code}) 股价与基金持仓联动关系 ({labels[0]}–{labels[-1]})',
                 fontsize=13, fontweight='bold', pad=8)
    ax.grid(axis='y', ls='--', alpha=0.35)
    for xi, v in zip(x, prices):
        ax.annotate(f'{v:.0f}', (xi, v), textcoords='offset points',
                    xytext=(0, 6), ha='center', fontsize=7, color='#e23b3b')
    ax.legend(loc='upper left', fontsize=8)
    if any(highs):
        peak_i = max(range(len(highs)), key=lambda i: highs[i])
        ax.annotate(f'历史顶点 {highs[peak_i]:.2f}\n({ends[peak_i]} 盘中)',
                    xy=(peak_i, highs[peak_i]),
                    xytext=(peak_i - 2.5, highs[peak_i] + max(prices) * 0.12),
                    fontsize=8, color='#ff8c1a', fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color='#ff8c1a', lw=1.2))

    ax = axes[1]
    full_x = [xi for xi, f in enumerate(is_full) if f]
    part_x = [xi for xi, f in enumerate(is_full) if not f]
    ax.plot(full_x, [funds[i] for i in full_x], color='#2b7bd4', lw=2.2,
            marker='s', ms=6, label='半年报/年报(全部持仓)')
    ax.plot(part_x, [funds[i] for i in part_x], color='#2b7bd4', lw=1.4,
            marker='o', ms=6, ls='--', label='季报(仅前十大重仓)', alpha=0.75)
    ax.set_ylabel('持仓基金数 (只)', fontsize=10)
    ax.grid(axis='y', ls='--', alpha=0.35)
    ax.legend(loc='upper left', fontsize=9)
    for xi in full_x:
        ax.annotate(f'{funds[xi]}', (xi, funds[xi]), textcoords='offset points',
                    xytext=(0, 5), ha='center', fontsize=7.5, color='#2b7bd4')

    ax = axes[2]
    ax.bar(x, shares, color=['#4a9d5f' if f else '#8fc9a3' for f in is_full],
           width=0.62, label='基金持股总量(亿股)')
    ax.set_ylabel('基金持股 (亿股)', fontsize=10)
    ax.grid(axis='y', ls='--', alpha=0.35)
    for xi, v in zip(x, shares):
        ax.annotate(f'{v:.2f}', (xi, v), textcoords='offset points',
                    xytext=(0, 4), ha='center', fontsize=7.5, color='#2b5f3c')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8, rotation=0)
    ax.set_xlabel('报告期', fontsize=10)

    fig.text(0.5, 0.012,
             '注：股价为不复权口径。季报(3/9月)仅披露前十大重仓股，基金数与持股量天然偏低；'
             '半年报/年报(6/12月)披露全部持仓。深绿柱=半年报/年报口径，浅绿柱=季报口径。',
             ha='center', fontsize=7.5, color='#666')

    plt.tight_layout(rect=[0, 0.03, 1, 0.99])
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type='image/png')
