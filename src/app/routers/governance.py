"""数据治理 API：数据资产目录 + 数据血缘可视化。

端点：
  GET  /api/governance/tables                      资产列表（分类/搜索/排序）
  GET  /api/governance/tables/suggest              表名自动提示（英文前缀/中文模糊）
  GET  /api/governance/tables/{table}              单表详情
  GET  /api/governance/tables/{table}/columns      列清单（含注释与血缘标记）
  GET  /api/governance/lineage/table/{table}       表级血缘（上游/下游）
  GET  /api/governance/lineage/field/{table}/{col} 字段级血缘（上游字段+公式+下游）
  POST /api/governance/meta/{table}                编辑表级元数据
  POST /api/governance/refresh                     刷新新鲜度缓存

约定：软错误返回 {'error': '...'}；全部复用 database.py 的 query/execute。
"""
import time
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..database import query, query_one, execute

router = APIRouter()

SCHEMA = 'ai_trading'

# ── 新鲜度缓存（32 张表逐表 MAX(date_col)，60s TTL） ──
_FRESH_CACHE = {'ts': 0.0, 'data': {}}
_FRESH_TTL = 60


def _freshness(force=False):
    now = time.time()
    if not force and _FRESH_CACHE['ts'] and now - _FRESH_CACHE['ts'] < _FRESH_TTL:
        return _FRESH_CACHE['data']
    meta = query("SELECT table_name, latest_date_col FROM data_catalog_meta WHERE latest_date_col != ''")
    out = {}
    for m in meta:
        tbl, col = m['table_name'], m['latest_date_col']
        try:
            r = query_one(f"SELECT MAX(`{col}`) v FROM `{tbl}`")
            v = r['v'] if r else None
            out[tbl] = str(v)[:10] if v else ''
        except Exception:
            out[tbl] = ''
    _FRESH_CACHE['ts'] = now
    _FRESH_CACHE['data'] = out
    return out


def _column_counts():
    """一次查询取全库各表列数。"""
    rows = query(
        "SELECT table_name AS table_name, COUNT(*) AS c FROM information_schema.columns "
        "WHERE table_schema=%s GROUP BY table_name", (SCHEMA,))
    return {r['table_name']: r['c'] for r in rows}


def _table_meta_map():
    """data_catalog_meta 全量，用于血缘图补中文名。"""
    return {r['table_name']: r for r in query("SELECT * FROM data_catalog_meta")}


def _comment_of(tbl):
    r = query_one(
        "SELECT table_comment AS table_comment FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
        (SCHEMA, tbl))
    return (r['table_comment'] if r else '') or ''


# ── 资产列表 ──────────────────────────────────────────────
@router.get('/tables')
def list_tables(category: str = '', q: str = '', sort: str = 'table_name'):
    meta = _table_meta_map()
    counts = _column_counts()
    fresh = _freshness()

    rows = query(
        "SELECT TABLE_NAME, TABLE_COMMENT, TABLE_ROWS, UPDATE_TIME "
        "FROM information_schema.tables WHERE table_schema=%s AND TABLE_TYPE='BASE TABLE'", (SCHEMA,))
    out = []
    for r in rows:
        name = r['TABLE_NAME']
        m = meta.get(name, {})
        out.append({
            'table_name': name,
            'table_comment': m.get('table_comment') or r['TABLE_COMMENT'] or '',
            'category': m.get('category', ''),
            'source': m.get('source', ''),
            'refresh_method': m.get('refresh_method', ''),
            'latest_date_col': m.get('latest_date_col', ''),
            'description': m.get('description', ''),
            'row_count': r['TABLE_ROWS'],
            'column_count': counts.get(name, 0),
            'latest_date': fresh.get(name, ''),
            'update_time': str(r['UPDATE_TIME'])[:16] if r['UPDATE_TIME'] else '',
        })
    # 过滤
    if category:
        out = [x for x in out if x['category'] == category]
    if q:
        ql = q.lower()
        out = [x for x in out if ql in x['table_name'].lower() or ql in x['table_comment'].lower()
               or ql in x['category'].lower()]
    # 排序（latest_date 倒序把最新排前面，空值垫底）
    if sort == 'latest_date':
        out.sort(key=lambda x: (x['latest_date'] == '', x['latest_date']), reverse=True)
    elif sort == 'row_count':
        out.sort(key=lambda x: x['row_count'] or 0, reverse=True)
    elif sort == 'category':
        out.sort(key=lambda x: (x['category'], x['table_name']))
    else:
        out.sort(key=lambda x: x['table_name'])
    return {'total': len(out), 'rows': out}


# ── 表名自动提示 ──────────────────────────────────────────
@router.get('/tables/suggest')
def suggest_tables(q: str = ''):
    q = (q or '').strip()
    if not q:
        return {'rows': []}
    ql = f'%{q}%'
    rows = query(
        "SELECT table_name, table_comment, category FROM data_catalog_meta "
        "WHERE table_name LIKE %s OR table_comment LIKE %s OR category LIKE %s "
        "ORDER BY (table_name LIKE %s) DESC, table_name LIMIT 8",
        (ql, ql, ql, f'{q}%'))
    return {'rows': rows}


# ── 单表详情 ──────────────────────────────────────────────
@router.get('/tables/{table}')
def table_detail(table: str):
    meta = query_one("SELECT * FROM data_catalog_meta WHERE table_name=%s", (table,))
    t = query_one(
        "SELECT TABLE_ROWS, TABLE_COMMENT FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name=%s", (SCHEMA, table))
    if not t:
        return {'error': f'table {table} not found'}
    fresh = _freshness()
    up = query_one(
        "SELECT COUNT(DISTINCT source_table) c FROM data_lineage WHERE target_table=%s", (table,))
    down = query_one(
        "SELECT COUNT(DISTINCT target_table) c FROM data_lineage WHERE source_table=%s", (table,))
    logs = []
    if table.startswith('ads_'):
        logs = query(
            "SELECT status, total_stocks, computed_stocks, error_stocks, started_at, finished_at, message "
            "FROM ads_refresh_log ORDER BY id DESC LIMIT 3")
    return {
        'table_name': table,
        'table_comment': (meta['table_comment'] if meta else '') or t['TABLE_COMMENT'] or '',
        'category': meta['category'] if meta else '',
        'source': meta['source'] if meta else '',
        'refresh_method': meta['refresh_method'] if meta else '',
        'latest_date_col': meta['latest_date_col'] if meta else '',
        'description': meta['description'] if meta else '',
        'row_count': t['TABLE_ROWS'],
        'latest_date': fresh.get(table, ''),
        'upstream_count': up['c'],
        'downstream_count': down['c'],
        'recent_logs': logs,
    }


# ── 列清单 ────────────────────────────────────────────────
@router.get('/tables/{table}/columns')
def table_columns(table: str):
    cols = query(
        "SELECT column_name AS column_name, column_comment AS column_comment, data_type AS data_type, "
        "is_nullable AS is_nullable, column_key AS column_key "
        "FROM information_schema.columns WHERE table_schema=%s AND table_name=%s "
        "ORDER BY ordinal_position", (SCHEMA, table))
    if not cols:
        return {'error': f'table {table} not found'}
    # 每列是否有血缘边
    edges = query(
        "SELECT target_column, COUNT(*) c FROM data_lineage "
        "WHERE target_table=%s AND target_column != '' GROUP BY target_column", (table,))
    edge_map = {r['target_column']: r['c'] for r in edges}
    return {'table': table, 'rows': [
        {'column_name': c['column_name'],
         'column_comment': c['column_comment'] or '',
         'data_type': c['data_type'],
         'nullable': c['is_nullable'],
         'key': c['column_key'],
         'has_lineage': edge_map.get(c['column_name'], 0) > 0}
        for c in cols]}


# ── 表级血缘 ──────────────────────────────────────────────
@router.get('/lineage/table/{table}')
def table_lineage(table: str):
    if not query_one("SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                     (SCHEMA, table)):
        return {'error': f'table {table} not found'}
    meta = _table_meta_map()
    # 上游：以本表为 target 的所有边去重 source_table，附带关系摘要
    ups = query(
        "SELECT source_table, target_column, transform, formula, note FROM data_lineage "
        "WHERE target_table=%s ORDER BY source_table, target_column", (table,))
    upstream_map = {}
    for e in ups:
        key = e['source_table']
        item = upstream_map.setdefault(key, {'table': key, 'table_comment': '', 'edges': []})
        if not item['table_comment']:
            m = meta.get(key)
            item['table_comment'] = (m['table_comment'] if m else '') or _comment_of(key)
        if e['target_column']:  # 仅汇总字段级边，控制体积
            item['edges'].append({'target_column': e['target_column'], 'transform': e['transform'],
                                  'formula': e['formula'], 'note': e['note']})
    # 下游：以本表为 source 的所有边去重 target_table
    downs = query(
        "SELECT DISTINCT target_table FROM data_lineage WHERE source_table=%s AND target_column=''", (table,))
    downstream = []
    for d in downs:
        tt = d['target_table']
        m = meta.get(tt)
        downstream.append({'table': tt, 'table_comment': (m['table_comment'] if m else '') or _comment_of(tt)})
    return {
        'table': table,
        'table_comment': (meta.get(table, {}).get('table_comment') or _comment_of(table)),
        'upstream': list(upstream_map.values()),
        'downstream': downstream,
    }


# ── 字段级血缘 ────────────────────────────────────────────
@router.get('/lineage/field/{table}/{column}')
def field_lineage(table: str, column: str):
    ups = query(
        "SELECT source_table, source_column, transform, formula, note FROM data_lineage "
        "WHERE target_table=%s AND target_column=%s", (table, column))
    downs = query(
        "SELECT target_table, target_column FROM data_lineage "
        "WHERE source_table=%s AND source_column=%s", (table, column))
    meta = _table_meta_map()
    col_meta = query_one(
        "SELECT column_comment AS column_comment FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s AND column_name=%s", (SCHEMA, table, column))
    upstream = []
    for u in ups:
        sm = meta.get(u['source_table'])
        upstream.append({
            'source_table': u['source_table'],
            'source_comment': (sm['table_comment'] if sm else '') or _comment_of(u['source_table']),
            'source_field': u['source_column'],
            'transform': u['transform'],
            'formula': u['formula'],
            'note': u['note'],
        })
    downstream = []
    for d in downs:
        dm = meta.get(d['target_table'])
        downstream.append({'target_table': d['target_table'],
                           'target_comment': (dm['table_comment'] if dm else '') or _comment_of(d['target_table']),
                           'target_field': d['target_column']})
    return {
        'table': table,
        'field': column,
        'field_comment': col_meta['column_comment'] if col_meta else '',
        'upstream': upstream,
        'downstream': downstream,
    }


# ── 编辑表级元数据 ────────────────────────────────────────
class MetaBody(BaseModel):
    table_comment: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None


@router.post('/meta/{table}')
def update_meta(table: str, body: MetaBody):
    cur = query_one("SELECT * FROM data_catalog_meta WHERE table_name=%s", (table,))
    if not cur:
        return {'error': f'table {table} not found'}
    if body.table_comment is not None:
        cur['table_comment'] = body.table_comment
    if body.category is not None:
        cur['category'] = body.category
    if body.source is not None:
        cur['source'] = body.source
    if body.description is not None:
        cur['description'] = body.description
    execute(
        "UPDATE data_catalog_meta SET table_comment=%s, category=%s, source=%s, description=%s "
        "WHERE table_name=%s",
        (cur['table_comment'], cur['category'], cur['source'], cur['description'], table))
    return {'status': 'ok', 'table_name': table}


# ── 刷新新鲜度缓存 ────────────────────────────────────────
@router.post('/refresh')
def refresh_governance():
    fresh = _freshness(force=True)
    counts = _column_counts()
    return {
        'status': 'ok',
        'table_count': len(counts),
        'lineage_edges': query_one("SELECT COUNT(*) c FROM data_lineage")['c'],
        'freshness': fresh,
    }
