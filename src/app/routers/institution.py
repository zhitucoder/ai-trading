from fastapi import APIRouter
from ..database import query, query_one

router = APIRouter()

# 归属势力 → 展示层配置（前端 Tab 与图标）
OWNER_GROUPS = [
    {'owner_type': 'shebao', 'label': '社保基金', 'icon': '🏛'},
    {'owner_type': 'yanglao', 'label': '基本养老保险', 'icon': '🧓'},
    {'owner_type': 'baoxian', 'label': '保险', 'icon': '🛡'},
    {'owner_type': 'caizheng', 'label': '财政部系', 'icon': '🏦'},
    {'owner_type': 'guozwei', 'label': '国资委系', 'icon': '🏭'},
    {'owner_type': 'hk_central', 'label': '北向·香港中央结算', 'icon': '🌐'},
]

# 北向是市场汇总通道而非单一实体，共持透视默认排除
CROSS_EXCLUDE = {'hk_central'}

# 总览持仓表可排序列白名单（防 SQL 注入）
OVERVIEW_SORTABLE = {
    'stock_code', 'stock_name', 'holder_cnt', 'total_hold',
    'hold_float_ratio', 'close_price', 'hold_mkv',
    'prev_hold_mkv', 'mkv_change', 'yoy_hold_mkv',
    'yoy_change', 'yoy_change_pct', 'consec',
}

_QUARTER_END = ['0331', '0630', '0930', '1231']


def _yoy_date(end_date):
    """同比日期：同一季度、上一年。20260630 → 20250630"""
    return f'{int(end_date[:4]) - 1}{end_date[4:]}'


def _prev_quarter_date(end_date):
    """上一季度日期：20260630 → 20260331"""
    qy = int(end_date[:4]) * 4 + (int(end_date[4:6]) - 1) // 3 - 1
    y, q = divmod(qy, 4)
    return f'{y:04d}{_QUARTER_END[q]}'


def _streak_map(changes):
    """按股票统计『连续增持/减持季度数』。
    输入: [{stock_code, action}]（按日期升序）
    返回: {stock_code: {'consec': int, 'last_action': str}}
      consec>0 = 连续增持 N 季；consec<0 = 连续减持 N 季；0 = 最近一季持平/无记录
    增持/新开仓视为向上，减持/清仓视为向下。
    """
    by_code = {}
    for c in changes:
        by_code.setdefault(c['stock_code'], []).append(c['action'])
    out = {}
    for code, actions in by_code.items():
        consec = 0
        for a in reversed(actions):
            if a in ('增持', '新开仓'):
                if consec >= 0:
                    consec += 1
                else:
                    break
            elif a in ('减持', '清仓'):
                if consec <= 0:
                    consec -= 1
                else:
                    break
            else:
                break
        out[code] = {'consec': consec, 'last_action': actions[-1] if actions else None}
    return out


@router.get('/institution/owners')
def institution_owners():
    sub = query("""
        SELECT DISTINCT owner_type, group_name, owner_label
        FROM ads_institution_overview
        ORDER BY owner_type, group_name
    """)
    by_type = {}
    for r in sub:
        by_type.setdefault(r['owner_type'], []).append({
            'group_name': r['group_name'],
            'owner_label': r['owner_label'],
        })
    for g in OWNER_GROUPS:
        g['groups'] = by_type.get(g['owner_type'], [])
    latest = query_one("SELECT MAX(end_date) d FROM ads_institution_overview") or {}
    dates = [r['end_date'] for r in query(
        "SELECT DISTINCT end_date FROM ads_institution_overview ORDER BY end_date")]
    return {'owners': OWNER_GROUPS, 'dates': dates, 'latest_date': latest.get('d')}


def _resolve_group(owner_type, group_name):
    if group_name:
        return 'group_name = %s', [group_name]
    return 'owner_type = %s', [owner_type]


@router.get('/institution/{owner_type}/overview')
def institution_overview(owner_type: str, group_name: str = None,
                         page: int = 1, page_size: int = 50,
                         sort_by: str = 'hold_mkv', sort_dir: str = 'desc',
                         q: str = '', consec: str = ''):
    where, params = _resolve_group(owner_type, group_name)
    latest = query_one("""
        SELECT end_date, quarter, group_name, stock_cnt, holder_cnt, total_mkv, avg_ratio
        FROM ads_institution_overview WHERE """ + where + """
        ORDER BY end_date DESC LIMIT 1
    """, params) or {}
    trend = query("""
        SELECT end_date, quarter, group_name, stock_cnt, holder_cnt, total_mkv, avg_ratio
        FROM ads_institution_overview WHERE """ + where + """
        ORDER BY end_date
    """, params)
    trend_by_date = {r['end_date']: r for r in trend}
    for r in trend:
        p = trend_by_date.get(_yoy_date(r['end_date']))
        r['yoy_mkv'] = p['total_mkv'] if p else None
        if p and p['total_mkv'] and r['total_mkv'] is not None:
            r['yoy_change'] = round(r['total_mkv'] - p['total_mkv'], 2)
            r['yoy_change_pct'] = round((r['total_mkv'] - p['total_mkv']) / p['total_mkv'] * 100, 2)
        else:
            r['yoy_change'] = None
            r['yoy_change_pct'] = None
    latest_date = latest.get('end_date')

    top = []
    total = 0
    if latest_date:
        all_rows = query("""
            SELECT stock_code, stock_name, end_date, holder_cnt, total_hold,
                   hold_float_ratio, close_price, hold_mkv
            FROM ads_institution_stock WHERE """ + where, params)
        by_code_date = {}
        for r in all_rows:
            by_code_date.setdefault(r['stock_code'], {})[r['end_date']] = r
        changes = query("""
            SELECT stock_code, end_date, action FROM ads_institution_change
            WHERE """ + where + """ ORDER BY stock_code, end_date
        """, params)
        streaks = _streak_map(changes)
        latest_rows = []
        for code, dmap in by_code_date.items():
            row = dmap.get(latest_date)
            if not row:
                continue
            prev = dmap.get(_prev_quarter_date(latest_date))
            yoy = dmap.get(_yoy_date(latest_date))
            sk = streaks.get(code, {})
            item = dict(row)
            item['prev_hold_mkv'] = prev['hold_mkv'] if prev else None
            item['mkv_change'] = round(row['hold_mkv'] - prev['hold_mkv'], 2) if prev and row['hold_mkv'] is not None and prev['hold_mkv'] is not None else None
            item['yoy_hold_mkv'] = yoy['hold_mkv'] if yoy else None
            item['yoy_change'] = round(row['hold_mkv'] - yoy['hold_mkv'], 2) if yoy and row['hold_mkv'] is not None and yoy['hold_mkv'] is not None else None
            item['yoy_change_pct'] = round(item['yoy_change'] / yoy['hold_mkv'] * 100, 2) if yoy and yoy['hold_mkv'] else None
            item['consec'] = sk.get('consec', 0)
            item['last_action'] = sk.get('last_action')
            latest_rows.append(item)
        if q:
            qk = q.strip().lower()
            latest_rows = [r for r in latest_rows
                           if qk in (r['stock_code'] or '').lower()
                           or qk in (r['stock_name'] or '').lower()]
        if consec:
            consec = consec.strip()
            if consec.startswith('>='):
                try:
                    n = int(consec[2:])
                    latest_rows = [r for r in latest_rows if r['consec'] >= n]
                except ValueError:
                    pass
            elif consec.startswith('<='):
                try:
                    n = int(consec[2:])
                    latest_rows = [r for r in latest_rows if r['consec'] <= n]
                except ValueError:
                    pass
            elif consec == 'up':
                latest_rows = [r for r in latest_rows if r['consec'] > 0]
            elif consec == 'down':
                latest_rows = [r for r in latest_rows if r['consec'] < 0]
        total = len(latest_rows)
        sort_key = sort_by if sort_by in OVERVIEW_SORTABLE else 'hold_mkv'
        reverse = sort_dir.lower() != 'asc'
        latest_rows.sort(key=lambda r: (r.get(sort_key) is None, r.get(sort_key) or 0), reverse=reverse)
        page = max(1, page)
        page_size = min(200, max(1, page_size))
        start = (page - 1) * page_size
        top = latest_rows[start:start + page_size]
    return {'owner_type': owner_type, 'group_name': group_name,
            'latest': latest, 'trend': trend, 'top': top, 'latest_date': latest_date,
            'total': total, 'page': page, 'page_size': page_size}


@router.get('/institution/{owner_type}/change')
def institution_change(owner_type: str, group_name: str = None,
                       quarter: str = None, action: str = None):
    where, params = _resolve_group(owner_type, group_name)
    if not quarter:
        row = query_one("""
            SELECT MAX(end_date) d FROM ads_institution_change WHERE """ + where, params) or {}
        qd = row.get('d') or '0630'
        quarter = qd[:4] + 'Q' + str((int(qd[4:6]) - 1) // 3 + 1)
    sql = "SELECT * FROM ads_institution_change WHERE " + where + " AND quarter = %s"
    params = params + [quarter]
    if action:
        sql += " AND action = %s"
        params = params + [action]
    rows = query(sql + " ORDER BY ABS(mkv_change) DESC LIMIT 100", params)
    return {'quarter': quarter, 'rows': rows}


@router.get('/institution/{owner_type}/sector')
def institution_sector(owner_type: str, group_name: str = None,
                       quarter: str = None, sector_type: str = 'industry'):
    where, params = _resolve_group(owner_type, group_name)
    if not quarter:
        row = query_one("""
            SELECT MAX(end_date) d FROM ads_institution_sector
            WHERE """ + where + " AND sector_type=%s", params + [sector_type]) or {}
        qd = row.get('d') or '0630'
        quarter = qd[:4] + 'Q' + str((int(qd[4:6]) - 1) // 3 + 1)
    if not quarter:
        return {'quarter': None, 'rows': []}
    rows = query("""
        SELECT sector_name, stock_cnt, hold_mkv, prev_hold_mkv, mkv_change
        FROM ads_institution_sector
        WHERE """ + where + """ AND end_date=%s AND sector_type=%s
        ORDER BY hold_mkv DESC LIMIT 50
    """, params + [quarter_to_date(quarter), sector_type])
    return {'quarter': quarter, 'rows': rows}


@router.get('/institution/{owner_type}/stock/{stock_code}')
def institution_stock_trajectory(owner_type: str, stock_code: str, group_name: str = None):
    where, params = _resolve_group(owner_type, group_name)
    rows = query("""
        SELECT end_date, quarter, holder_cnt, total_hold, hold_ratio,
               hold_float_ratio, close_price, hold_mkv
        FROM ads_institution_stock
        WHERE """ + where + """ AND stock_code=%s
        ORDER BY end_date
    """, params + [stock_code])
    change = query("""
        SELECT end_date, prev_end_date, quarter, hold_mkv, prev_hold_mkv,
               mkv_change, total_hold, prev_total_hold, hold_change, hold_change_pct, action
        FROM ads_institution_change
        WHERE """ + where + """ AND stock_code=%s
        ORDER BY end_date
    """, params + [stock_code])
    return {'stock_code': stock_code, 'history': rows, 'change': change}


@router.get('/institution/cross')
def institution_cross(types: str = 'shebao,yanglao,baoxian', quarter: str = None):
    tlist = [t.strip() for t in types.split(',') if t.strip()]
    tlist = [t for t in tlist if t not in CROSS_EXCLUDE]
    if not tlist:
        return {'quarter': quarter, 'rows': []}
    if not quarter:
        row = query_one("SELECT MAX(end_date) d FROM ads_institution_stock") or {}
        quarter = (row.get('d') or '')[:4] + 'Q' + str((int((row.get('d') or '0630')[4:6]) - 1) // 3 + 1)
    placeholders = ','.join(['%s'] * len(tlist))
    rows = query("""
        SELECT stock_code, stock_name, end_date, quarter,
               COUNT(DISTINCT owner_type) owner_cnt,
               GROUP_CONCAT(DISTINCT owner_type ORDER BY owner_type) owners,
               SUM(hold_mkv) total_mkv
        FROM ads_institution_stock
        WHERE owner_type IN (""" + placeholders + """) AND quarter=%s
        GROUP BY stock_code, stock_name, end_date, quarter
        ORDER BY owner_cnt DESC, total_mkv DESC
        LIMIT 100
    """, tlist + [quarter])
    return {'quarter': quarter, 'rows': rows}


def quarter_to_date(quarter):
    yy = quarter[:2]
    q = quarter[3:]
    return f'20{yy}{["", "0331", "0630", "0930", "1231"][int(q)]}'
