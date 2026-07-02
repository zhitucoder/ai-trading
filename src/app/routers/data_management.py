import os
import re
import struct
import threading
from datetime import datetime, date
from fastapi import APIRouter
from pytdx.crawler.history_financial_crawler import HistoryFinancialCrawler
from ..database import get_conn, query
from ...import_financial import FIELD_MAP, safe

router = APIRouter()

DATA_DIR = '/mnt/d/programs/stock/vipdoc'
RECORD_FMT = '<IIIIIfII'
RECORD_SIZE = 32

_update_lock = threading.Lock()


def _parse_day_file_after(filepath, since):
    code = os.path.splitext(os.path.basename(filepath))[0][2:]
    records = []
    with open(filepath, 'rb') as f:
        while True:
            data = f.read(RECORD_SIZE)
            if len(data) < RECORD_SIZE:
                break
            dt, o, h, l, c, amt, vol, _ = struct.unpack(RECORD_FMT, data)
            td = datetime.strptime(str(dt), '%Y%m%d').date()
            if td < since:
                continue
            records.append((
                code, td,
                round(o / 100, 2), round(h / 100, 2),
                round(l / 100, 2), round(c / 100, 2),
                vol, round(amt, 2),
            ))
    return records


@router.get('/data/status')
def data_status():
    kline = query("SELECT MAX(trade_date) AS max_date, COUNT(DISTINCT stock_code) AS stock_count FROM daily_kline")
    kline_row = kline[0] if kline else {}

    fin = query("SELECT MAX(report_date) AS d, COUNT(*) AS cnt FROM fin_income")
    fin_row = fin[0] if fin else {}

    return {
        'kline': {
            'latest_date': str(kline_row.get('max_date') or ''),
            'stock_count': kline_row.get('stock_count') or 0,
        },
        'financial': {
            'latest_date': str(fin_row.get('d') or ''),
            'record_count': fin_row.get('cnt') or 0,
        },
        'sector': {'status': 'pending', 'message': '待接入'},
    }


@router.post('/data/update-kline')
def update_kline():
    if not _update_lock.acquire(blocking=False):
        return {'status': 'running', 'message': '更新任务已在执行中'}

    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT MAX(trade_date) AS d FROM daily_kline")
        row = cursor.fetchone()
        db_latest = row['d'] if row and row['d'] else date(2000, 1, 1)
        since = db_latest

        total_inserted = 0
        total_errors = 0
        exchanges = []

        for exchange in ['sh', 'sz', 'bj']:
            day_dir = os.path.join(DATA_DIR, exchange, 'lday')
            if not os.path.isdir(day_dir):
                continue

            files = sorted([f for f in os.listdir(day_dir) if f.endswith('.day')])
            batch = []
            for fname in files:
                try:
                    records = _parse_day_file_after(os.path.join(day_dir, fname), since)
                    batch.extend(records)
                except Exception:
                    total_errors += 1

            if not batch:
                exchanges.append({'exchange': exchange, 'files': len(files), 'new_records': 0})
                continue

            sql = """INSERT IGNORE INTO daily_kline
                     (stock_code, trade_date, open_price, high_price, low_price, close_price, volume, amount)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""

            CHUNK = 5000
            for i in range(0, len(batch), CHUNK):
                chunk = batch[i:i + CHUNK]
                cursor.executemany(sql, chunk)
                conn.commit()

            exchanges.append({'exchange': exchange, 'files': len(files), 'candidates': len(batch)})
            total_inserted += len(batch)

        cursor.close()
        conn.close()

        return {
            'status': 'ok',
            'total_inserted': total_inserted,
            'errors': total_errors,
            'exchanges': exchanges,
            'db_latest': str(db_latest),
        }
    finally:
        _update_lock.release()


@router.post('/data/update-financial')
def update_financial():
    if not _update_lock.acquire(blocking=False):
        return {'status': 'running', 'message': '更新任务已在执行中'}
    try:
        fin_tables = {
            'fin_balance_sheet': ['cash', 'trading_fa', 'accounts_receivable',
                'inventory', 'current_assets', 'fixed_assets', 'intangible_assets',
                'goodwill', 'noncurrent_assets', 'total_assets', 'short_term_borrow',
                'accounts_payable', 'current_liabilities', 'long_term_borrow',
                'noncurrent_liabilities', 'total_liabilities', 'share_capital',
                'capital_surplus', 'surplus_reserve', 'retained_profit',
                'minority_interest', 'total_equity'],
            'fin_income': ['operating_revenue', 'operating_cost', 'selling_expense',
                'admin_expense', 'finance_expense', 'asset_impairment',
                'investment_income', 'operating_profit', 'non_op_income',
                'total_profit', 'income_tax', 'net_profit', 'parent_net_profit',
                'minority_pnl'],
            'fin_cash_flow': ['op_cash_inflow', 'op_cash_outflow', 'op_cash_flow',
                'invest_cash_inflow', 'invest_cash_outflow', 'invest_cash_flow',
                'finance_cash_inflow', 'finance_cash_outflow', 'finance_cash_flow',
                'cash_net_change', 'free_cash_flow'],
            'fin_ratios': ['roe', 'roe_weighted', 'roe_diluted', 'gross_margin',
                'net_margin', 'debt_ratio', 'current_ratio', 'quick_ratio',
                'inventory_turnover', 'basic_eps', 'diluted_eps', 'bps',
                'revenue_growth_rate', 'net_profit_growth_rate',
                'op_profit_growth_rate', 'total_asset_growth_rate',
                'nav_growth_rate', 'ebit', 'ebitda', 'revenue_cagr_3y',
                'net_profit_cagr_3y', 'pe_ttm', 'market_cap'],
            'fin_quarterly': ['q_revenue', 'q_operating_profit',
                'q_parent_net_profit', 'q_deducted_net_profit',
                'q_op_cash_flow', 'q_invest_cash_flow', 'q_finance_cash_flow'],
            'fin_shareholder': ['total_shares', 'float_shares', 'holders',
                'holders_prev', 'top10_ratio'],
            'fin_institution': ['fund_hold_shares', 'fund_hold_ratio',
                'qfii_hold_shares', 'social_security_hold', 'insurance_hold',
                'northbound_hold', 'northbound_ratio'],
            'fin_extended': ['rd_expense', 'operating_revenue_ttm',
                'net_profit_ttm', 'op_cash_flow_ttm', 'long_term_equity',
                'capital_reserve_ps', 'free_cash_flow', 'ocf_ps'],
        }
        all_fin_cols = {c for cols in fin_tables.values() for c in cols}
        field_idx = {}
        for k, v in FIELD_MAP.items():
            if v[0] in all_fin_cols:
                field_idx[v[0]] = k

        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT MAX(report_date) AS d FROM fin_income")
        row = cursor.fetchone()
        db_latest = row['d'] if row and row['d'] else date(2000, 1, 1)
        db_latest_str = db_latest.strftime('%Y%m%d')

        cw_dir = '/mnt/d/programs/stock/vipdoc/cw'
        dat_files = sorted(
            f for f in os.listdir(cw_dir)
            if re.match(r'gpcw20\d{6}\.dat$', f)
            and os.path.getsize(os.path.join(cw_dir, f)) > 100
            and f[4:12] > db_latest_str
        )

        if not dat_files:
            cursor.close()
            conn.close()
            return {'status': 'ok', 'total_inserted': 0, 'files': [],
                    'db_latest': str(db_latest), 'message': '财务数据已是最新'}

        total = 0
        processed = []
        BATCH = 1000

        for fname in dat_files:
            fpath = os.path.join(cw_dir, fname)
            date_str = fname[4:12]
            rdate = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            try:
                crawler = HistoryFinancialCrawler()
                with open(fpath, 'rb') as f:
                    data = crawler.parse(download_file=f)
                df = crawler.to_df(data)
                if df is None or df.empty:
                    processed.append({'file': fname, 'records': 0, 'error': 'empty'})
                    continue
                row_count = 0
                for table_name, col_names in fin_tables.items():
                    rows = []
                    for code_val, row_data in df.iterrows():
                        vals = {'stock_code': code_val, 'report_date': rdate}
                        for cn in col_names:
                            idx = field_idx.get(cn)
                            if idx is None:
                                vals[cn] = None
                            else:
                                raw = row_data.get(f'col{idx}')
                                vals[cn] = safe(raw)
                        rows.append(vals)
                    for i in range(0, len(rows), BATCH):
                        batch = rows[i:i + BATCH]
                        cols = ['stock_code', 'report_date'] + col_names
                        ph = ', '.join([f'%({c})s' for c in cols])
                        sql = f"INSERT IGNORE INTO {table_name} ({', '.join(cols)}) VALUES ({ph})"
                        cursor.executemany(sql, batch)
                        conn.commit()
                    row_count += len(rows)

                total += row_count
                processed.append({'file': fname, 'records': row_count})
            except Exception as e:
                processed.append({'file': fname, 'records': 0, 'error': str(e)})

        cursor.close()
        conn.close()

        return {
            'status': 'ok',
            'total_inserted': total,
            'files': processed,
            'db_latest': str(db_latest),
        }
    finally:
        _update_lock.release()


@router.post('/data/update-sector')
def update_sector():
    return {'status': 'ok', 'message': '板块分类同步功能待接入'}
