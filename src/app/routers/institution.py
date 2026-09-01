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
def institution_overview(owner_type: str, group_name: str = None):
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
    latest_date = latest.get('end_date')
    top = []
    if latest_date:
        top = query("""
            SELECT stock_code, stock_name, holder_cnt, total_hold,
                   hold_float_ratio, close_price, hold_mkv
            FROM ads_institution_stock WHERE """ + where + """ AND end_date = %s
            ORDER BY hold_mkv DESC LIMIT 20
        """, params + [latest_date])
    return {'owner_type': owner_type, 'group_name': group_name,
            'latest': latest, 'trend': trend, 'top': top, 'latest_date': latest_date}


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
