"""全市场画像批量计算模块"""
import json
from datetime import date
from src.app.database import query, execute
from src.app.strategies.profile import generate_profile, IND_TAGS_DEF, BIZ_TAGS_DEF

BATCH_SIZE = 500

TAG_COLUMNS = sorted(
    [f'tag_{k.split(".")[1]}' for k in IND_TAGS_DEF] +
    [f'tag_{k.split(".")[1]}' for k in BIZ_TAGS_DEF]
)


def _active_tag_ids(result):
    ids = set()
    for t in result.get('ind_tags', []):
        ids.add(t['id'])
    for t in result.get('biz_tags', []):
        ids.add(t['id'])
    return ids


def _to_profile_row(result, report_date, fin_report_date):
    ids = _active_tag_ids(result)
    row = {
        'stock_code': result['code'],
        'stock_name': result['name'],
        'trade_date': result['date'],
        'stage_id': result['stage']['id'],
        'stage_confidence': result['stage']['confidence'],
        'tech_score': result['scores']['tech'],
        'fund_score': result['scores']['fund'],
        'latest_price': result['latest_price'],
        'price_change_pct': result['price_change_pct'],
        'revenue_growth': result.get('fin_data', {}).get('revenue_growth_rate'),
        'net_profit_growth': result.get('fin_data', {}).get('net_profit_growth_rate'),
        'debt_ratio': result.get('fin_data', {}).get('debt_ratio'),
        'data_date': str(report_date),
        'fin_report_date': str(fin_report_date) if fin_report_date else None,
        'profile_json': json.dumps(result, ensure_ascii=False),
    }
    for col in TAG_COLUMNS:
        tag_id = f'{col[4:]}'  # remove 'tag_' prefix, e.g. 'high_growth'
        # Try biz.* first, then ind.*
        row[col] = f'biz.{tag_id}' in ids or f'ind.{tag_id}' in ids
    return row


def _batch_insert(rows, conn):
    if not rows:
        return
    cols = (
        ['stock_code', 'stock_name', 'trade_date',
         'stage_id', 'stage_confidence', 'tech_score', 'fund_score',
         'latest_price', 'price_change_pct',
         'revenue_growth', 'net_profit_growth', 'debt_ratio',
         'data_date', 'fin_report_date', 'profile_json']
        + TAG_COLUMNS
    )
    placeholders = ', '.join(['%s'] * len(cols))
    col_names = ', '.join(cols)
    values = []
    for row in rows:
        values.append(tuple(row[c] for c in cols))
    sql = f"INSERT IGNORE INTO stock_profiles ({col_names}) VALUES ({placeholders})"
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    conn.commit()


def _update_progress_log(log_id, computed, total, errors, status='running', conn=None):
    sql = """UPDATE profile_refresh_log
             SET computed_stocks = %s, error_stocks = %s,
                 status = %s
             WHERE id = %s"""
    params = [computed, errors, status, log_id]
    if status in ('done', 'failed'):
        sql = """UPDATE profile_refresh_log
                 SET computed_stocks = %s, error_stocks = %s,
                     status = %s, finished_at = NOW()
                 WHERE id = %s"""
    execute(sql, params)


def run_batch(report_date=None):
    """全量计算画像并写入 stock_profiles。report_date 为 K 线数据截止日期"""
    import pymysql
    from pymysql.cursors import DictCursor

    DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                     password='aitrading123', database='ai_trading',
                     charset='utf8mb4')

    stocks = query("SELECT stock_code FROM stocks ORDER BY stock_code")
    if not stocks:
        return
    total = len(stocks)
    trade_date = str(report_date or date.today())

    fin_report = query("SELECT MAX(report_date) AS d FROM fin_ratios")
    fin_report_date = fin_report[0]['d'] if fin_report else None

    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    try:
        execute("INSERT INTO profile_refresh_log (started_at, status, total_stocks, trade_date, fin_report_date) "
                "VALUES (NOW(), 'running', %s, %s, %s)",
                [total, trade_date, str(fin_report_date) if fin_report_date else None])

        computed = 0
        errors = 0
        batch_rows = []

        for s in stocks:
            result = generate_profile(s['stock_code'])
            computed += 1
            if 'error' not in result:
                batch_rows.append(_to_profile_row(result, trade_date, fin_report_date))
            else:
                errors += 1

            if len(batch_rows) >= BATCH_SIZE:
                _batch_insert(batch_rows, conn)
                batch_rows.clear()

        if batch_rows:
            _batch_insert(batch_rows, conn)

        execute("DELETE FROM stock_profiles WHERE data_date < DATE_SUB(%s, INTERVAL 2 DAY)", [trade_date])

        log_entry = query("SELECT MAX(id) AS max_id FROM profile_refresh_log")
        if log_entry and log_entry[0]['max_id']:
            execute("UPDATE profile_refresh_log SET status='done', finished_at=NOW() WHERE id = %s",
                    [log_entry[0]['max_id']])

        return {'total': total, 'computed': computed, 'errors': errors}
    finally:
        conn.close()
