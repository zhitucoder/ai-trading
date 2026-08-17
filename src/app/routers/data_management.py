import os
import re
import struct
import sys
import threading
from datetime import datetime, date
from fastapi import APIRouter
from pytdx.crawler.history_financial_crawler import HistoryFinancialCrawler
from ..database import get_conn, query
from ...import_financial import FIELD_MAP, safe
from ...import_kline import classify_file

router = APIRouter()

DATA_DIR = '/mnt/d/programs/stock/vipdoc'
RECORD_FMT = '<IIIIIfII'
RECORD_SIZE = 32

_update_lock = threading.Lock()
_ads_lock = threading.Lock()
_dmdl_lock = threading.Lock()
_qfq_lock = threading.Lock()


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


def _get_latest_dates(cursor):
    """获取 daily_kline 和 sector_kline 的最新日期"""
    cursor.execute("SELECT MAX(trade_date) AS d FROM daily_kline")
    row = cursor.fetchone()
    stock_date = row['d'] if row and row['d'] else date(2000, 1, 1)

    cursor.execute("SELECT MAX(trade_date) AS d FROM sector_kline")
    row = cursor.fetchone()
    sector_date = row['d'] if row and row['d'] else date(2000, 1, 1)

    return stock_date, sector_date


@router.get('/data/status')
def data_status():
    kline = query("SELECT MAX(trade_date) AS max_date, COUNT(DISTINCT stock_code) AS stock_count FROM daily_kline")
    kline_row = kline[0] if kline else {}

    qfq = query("SELECT MAX(trade_date) AS max_date, COUNT(DISTINCT stock_code) AS stock_count, COUNT(*) AS row_count FROM daily_kline_qfq")
    qfq_row = qfq[0] if qfq else {}

    sector = query("SELECT MAX(trade_date) AS max_date, COUNT(DISTINCT sector_code) AS sector_count FROM sector_kline")
    sector_kline_row = sector[0] if sector else {}

    fin = query("SELECT MAX(report_date) AS d, COUNT(*) AS cnt FROM fin_income")
    fin_row = fin[0] if fin else {}

    div = query("SELECT MAX(updated_at) AS d, COUNT(DISTINCT stock_code) AS sc, COUNT(*) AS cnt, MAX(report_date) AS rd FROM stock_dividend")
    div_row = div[0] if div else {}

    sector = query("SELECT COUNT(*) AS sc FROM sectors")
    sector_map = query("SELECT COUNT(*) AS mc FROM stock_sectors")
    sector_row = sector[0] if sector else {}
    sector_map_row = sector_map[0] if sector_map else {}
    has_sector = (sector_row.get('sc') or 0) > 0

    ads = query("""
        SELECT
          (SELECT COUNT(*) FROM ads_stock_annual) AS stock_annual,
          (SELECT COUNT(*) FROM ads_stock_latest) AS stock_latest,
          (SELECT COUNT(*) FROM ads_sector_annual) AS sector_annual,
          (SELECT COUNT(*) FROM ads_sector_latest) AS sector_latest,
          (SELECT COUNT(*) FROM ads_stock_fund) AS stock_fund,
          (SELECT MAX(started_at) FROM ads_refresh_log) AS last_run,
          (SELECT status FROM ads_refresh_log ORDER BY id DESC LIMIT 1) AS last_status
    """)
    ads_row = ads[0] if ads else {}

    return {
        'kline': {
            'latest_date': str(kline_row.get('max_date') or ''),
            'stock_count': kline_row.get('stock_count') or 0,
        },
        'qfq': {
            'latest_date': str(qfq_row.get('max_date') or ''),
            'stock_count': qfq_row.get('stock_count') or 0,
            'row_count': qfq_row.get('row_count') or 0,
        },
        'sector_kline': {
            'latest_date': str(sector_kline_row.get('max_date') or ''),
            'sector_count': sector_kline_row.get('sector_count') or 0,
        },
        'financial': {
            'latest_date': str(fin_row.get('d') or ''),
            'record_count': fin_row.get('cnt') or 0,
        },
        'dividend': {
            'latest_update': str(div_row.get('d') or ''),
            'stock_count': div_row.get('sc') or 0,
            'record_count': div_row.get('cnt') or 0,
            'latest_report_date': str(div_row.get('rd') or ''),
        },
        'sector': {
            'status': 'ok' if has_sector else 'pending',
            'sector_count': sector_row.get('sc') or 0,
            'mapping_count': sector_map_row.get('mc') or 0,
            'message': '已同步' if has_sector else '待同步',
        },
        'ads': {
            'stock_annual': ads_row.get('stock_annual') or 0,
            'stock_latest': ads_row.get('stock_latest') or 0,
            'sector_annual': ads_row.get('sector_annual') or 0,
            'sector_latest': ads_row.get('sector_latest') or 0,
            'stock_fund': ads_row.get('stock_fund') or 0,
            'last_run': str(ads_row.get('last_run') or ''),
            'status': ads_row.get('last_status') or 'idle',
        },
    }


@router.post('/data/update-kline')
def update_kline():
    if not _update_lock.acquire(blocking=False):
        return {'status': 'running', 'message': '更新任务已在执行中'}

    try:
        conn = get_conn()
        cursor = conn.cursor()

        stock_latest, sector_latest = _get_latest_dates(cursor)

        stock_sql = """INSERT IGNORE INTO daily_kline
                       (stock_code, trade_date, open_price, high_price, low_price, close_price, volume, amount)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
        sector_sql = """INSERT IGNORE INTO sector_kline
                        (sector_code, trade_date, open_price, high_price, low_price, close_price, volume, amount)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""

        total_stock = 0
        total_sector = 0
        total_errors = 0
        exchanges = []

        for exchange in ['sh', 'sz', 'bj']:
            day_dir = os.path.join(DATA_DIR, exchange, 'lday')
            if not os.path.isdir(day_dir):
                continue

            files = sorted([f for f in os.listdir(day_dir) if f.endswith('.day')])
            stock_batch = []
            sector_batch = []
            skipped = 0

            for fname in files:
                code = fname[2:-4]
                cat = classify_file(exchange, code)
                if cat == 'skip':
                    skipped += 1
                    continue

                since = sector_latest if cat == 'sector' else stock_latest
                try:
                    records = _parse_day_file_after(os.path.join(day_dir, fname), since)
                    if cat == 'sector':
                        sector_batch.extend(records)
                    else:
                        stock_batch.extend(records)
                except Exception:
                    total_errors += 1

            if stock_batch:
                for i in range(0, len(stock_batch), 5000):
                    chunk = stock_batch[i:i + 5000]
                    cursor.executemany(stock_sql, chunk)
                    conn.commit()
            if sector_batch:
                for i in range(0, len(sector_batch), 5000):
                    chunk = sector_batch[i:i + 5000]
                    cursor.executemany(sector_sql, chunk)
                    conn.commit()

            exchanges.append({
                'exchange': exchange,
                'files': len(files),
                'stock_records': len(stock_batch),
                'sector_records': len(sector_batch),
                'skipped': skipped,
            })
            total_stock += len(stock_batch)
            total_sector += len(sector_batch)

        cursor.close()
        conn.close()

        return {
            'status': 'ok',
            'stock_inserted': total_stock,
            'sector_inserted': total_sector,
            'errors': total_errors,
            'exchanges': exchanges,
            'db_latest': {'stock': str(stock_latest), 'sector': str(sector_latest)},
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
    if not _update_lock.acquire(blocking=False):
        return {'status': 'running', 'message': '同步任务已在执行中'}
    try:
        from ...import_sectors import (
            parse_sector_definitions,
            parse_stock_sector_mapping,
            parse_industry_stock_mapping,
        )

        try:
            sectors = parse_sector_definitions()
        except FileNotFoundError:
            return {'status': 'error', 'message': '通达信板块定义文件缺失（T0002/hq_cache/tdxzs.cfg）'}
        except Exception as e:
            return {'status': 'error', 'message': f'板块定义解析失败: {e}'}

        try:
            mappings = parse_stock_sector_mapping()
            industry_mappings = parse_industry_stock_mapping(sectors)
        except FileNotFoundError:
            return {'status': 'error', 'message': '通达信板块映射文件缺失'}
        except Exception as e:
            return {'status': 'error', 'message': f'板块映射解析失败: {e}'}

        all_mappings = mappings + industry_mappings

        sector_stock_count = {}
        for stock_code, sector_code in all_mappings:
            sector_stock_count[sector_code] = sector_stock_count.get(sector_code, 0) + 1
        for code, count in sector_stock_count.items():
            if code in sectors:
                sectors[code]['stock_count'] = count

        conn = get_conn()
        cursor = conn.cursor()

        sector_rows = []
        for s in sectors.values():
            sector_rows.append((
                s['sector_code'], s['sector_name'], s['category'],
                s['category_cn'], s['sub_category'], s['level'],
                s['tdx_industry_code'], s['stock_count'],
            ))

        sector_cat_map = {s['sector_code']: s['category'] for s in sectors.values()}
        batch = []
        for stock_code, sector_code in all_mappings:
            cat = sector_cat_map.get(sector_code, 'unknown')
            batch.append((stock_code, sector_code, cat))

        sector_sql = """INSERT INTO sectors
            (sector_code, sector_name, category, category_cn, sub_category, level, tdx_industry_code, stock_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              sector_name=VALUES(sector_name), category=VALUES(category),
              category_cn=VALUES(category_cn), sub_category=VALUES(sub_category),
              level=VALUES(level), tdx_industry_code=VALUES(tdx_industry_code),
              stock_count=VALUES(stock_count)"""
        map_sql = """INSERT INTO stock_sectors (stock_code, sector_code, category)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE category=VALUES(category)"""

        CHUNK = 5000
        cursor.execute("START TRANSACTION")
        try:
            cursor.execute("DELETE FROM stock_sectors")
            for i in range(0, len(batch), CHUNK):
                cursor.executemany(map_sql, batch[i:i + CHUNK])

            cursor.execute("DELETE FROM sectors")
            for i in range(0, len(sector_rows), CHUNK):
                cursor.executemany(sector_sql, sector_rows[i:i + CHUNK])

            conn.commit()
        except Exception:
            conn.rollback()
            cursor.close()
            conn.close()
            return {'status': 'error', 'message': '板块数据写入失败，已回滚'}

        cursor.close()
        conn.close()

        return {
            'status': 'ok',
            'sector_count': len(sectors),
            'mapping_count': len(all_mappings),
            'message': f'板块分类同步完成（{len(sectors)} 个板块 / {len(all_mappings)} 条映射）',
        }
    finally:
        _update_lock.release()


@router.post('/data/update-dividend')
def update_dividend():
    if not _update_lock.acquire(blocking=False):
        return {'status': 'running', 'message': '更新任务已在执行中'}
    try:
        import subprocess
        from pathlib import Path
        latest = query("SELECT MAX(updated_at) AS d FROM stock_dividend")[0]['d']
        since = latest.date() if latest else date(2021, 1, 1)
        script = Path(__file__).resolve().parent.parent.parent.parent / 'scripts' / 'fetch_dividend.py'
        proc = subprocess.run(
            [sys.executable, str(script), '--since', str(since), '--workers', '8'],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            return {'status': 'error', 'message': proc.stderr[-500:]}
        return {
            'status': 'ok',
            'since': str(since),
            'message': proc.stdout.strip()[-300:],
        }
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'message': '抓取超时（>10分钟）'}
    finally:
        _update_lock.release()


@router.get('/data/ads/status')
def ads_status():
    row = query("""
        SELECT status, total_stocks, computed_stocks, error_stocks,
               started_at, finished_at, message
        FROM ads_refresh_log ORDER BY id DESC LIMIT 1
    """)
    if not row:
        return {'status': 'idle', 'computed': 0, 'total': 0, 'message': '尚未预计算'}
    r = row[0]
    return {
        'status': r.get('status') or 'idle',
        'total': r.get('total_stocks') or 0,
        'computed': r.get('computed_stocks') or 0,
        'errors': r.get('error_stocks') or 0,
        'started_at': str(r.get('started_at') or ''),
        'finished_at': str(r.get('finished_at') or ''),
        'message': r.get('message') or '',
    }


@router.post('/data/update-ads')
def update_ads():
    if not _ads_lock.acquire(blocking=False):
        return {'status': 'running', 'message': '预计算任务已在执行中'}
    from ...compute_ads import compute

    def _run():
        conn = None
        log_id = None
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO ads_refresh_log (status, total_stocks, computed_stocks, error_stocks, started_at)
                VALUES ('running', 0, 0, 0, NOW())
            """)
            conn.commit()
            log_id = cur.lastrowid
            cur.close()

            result = compute(progress_cb=None)

            cur = conn.cursor()
            cur.execute("""
                UPDATE ads_refresh_log SET status='done', total_stocks=%s,
                       computed_stocks=%s, finished_at=NOW(), message=%s WHERE id=%s
            """, (result['stock_latest'], result['stock_latest'],
                  f"个股年度{result['stock_annual']} / 行业年度{result['sector_annual']} / "
                  f"个股快照{result['stock_latest']} / 行业快照{result['sector_latest']} / "
                  f"基金持仓{result['stock_fund']}，耗时{result['elapsed_seconds']}s", log_id))
            conn.commit()
        except Exception as e:
            if conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE ads_refresh_log SET status='error', finished_at=NOW(), message=%s WHERE id=%s
                """, (str(e)[-450:], log_id))
                conn.commit()
        finally:
            if conn:
                conn.close()
            _ads_lock.release()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {'status': 'started', 'message': '分析预计算已启动（后台运行）'}


# ── 前复权K线（daily_kline_qfq） ──
@router.get('/data/qfq/status')
def qfq_status():
    status = 'running' if _qfq_lock.locked() else 'idle'
    log_tail = ''
    try:
        from pathlib import Path
        lines = Path('/tmp/qfq_update.log').read_text(encoding='utf-8').strip().split('\n')
        log_tail = '\n'.join(lines[-6:])
    except Exception:
        pass
    return {'status': status, 'log_tail': log_tail}


@router.post('/data/update-qfq')
def update_qfq():
    if not _qfq_lock.acquire(blocking=False):
        return {'status': 'running', 'message': '前复权计算已在执行中'}
    from ...compute_kline_qfq import compute_qfq

    def _run():
        try:
            from pathlib import Path
            with open('/tmp/qfq_update.log', 'w', encoding='utf-8') as f:
                f.write('')
            def wlog(msg):
                with open('/tmp/qfq_update.log', 'a', encoding='utf-8') as f:
                    f.write(msg + '\n')
            result = compute_qfq(progress_cb=wlog)
            wlog(f"完成: {result['rows']} 条 / {result['stocks']} 只，"
                 f"分红股票 {result['event_stocks']} 只，耗时 {result['elapsed_seconds']}s")
        except Exception as e:
            with open('/tmp/qfq_update.log', 'a', encoding='utf-8') as f:
                f.write(f'ERROR: {e}\n')
        finally:
            _qfq_lock.release()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {'status': 'started', 'message': '前复权K线计算已启动（后台运行，约需5-8分钟）'}


# ── 定期报告下载（年报/季报） ──
_reports_lock = threading.Lock()


@router.get('/data/reports/status')
def reports_status():
    rows = query("""
        SELECT source, report_year, report_period, COUNT(*) AS cnt,
               COALESCE(SUM(file_size), 0) AS total_bytes
        FROM report_pdf GROUP BY source, report_year, report_period
        ORDER BY report_year DESC, source, report_period
    """)
    return {
        'running': _reports_lock.locked(),
        'groups': rows,
        'total_files': sum(r['cnt'] for r in rows),
        'total_bytes': sum(r['total_bytes'] for r in rows),
    }


@router.post('/data/update-reports')
def update_reports(source: str = 'cninfo', period: str = 'annual', interval: float = 5.0):
    if not _reports_lock.acquire(blocking=False):
        return {'status': 'running', 'message': '报告下载已在执行中'}
    import subprocess
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent.parent / 'download_reports.py'

    def _run():
        log_path = Path('/tmp/report_download_api.log')
        try:
            with open(log_path, 'w') as f:
                subprocess.run(
                    [sys.executable, str(script), '--source', source, '--period', period,
                     '--interval', str(interval)],
                    stdout=f, stderr=subprocess.STDOUT, timeout=60 * 60 * 12,
                )
        except subprocess.TimeoutExpired:
            pass
        finally:
            _reports_lock.release()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {'status': 'started', 'source': source, 'period': period,
            'message': f'报告下载已启动（{source}·{period}，后台运行）'}


# ═══════════ 达摩达兰估值 ═══════════

@router.get('/dmdl/valuation')
def dmdl_valuation(min_score: int = 0, stage: str = '', min_cap: float = 0,
                   eq_quality: str = 'A,B', stock_code: str = '', limit: int = 50):
    if stock_code:
        # 按代码查：直接查 static+mkt（绕过视图的C级过滤，保证任意股票可查）
        return query("""
            SELECT s.stock_code, s.stock_name, s.life_stage, s.earnings_quality, s.risk_penalty,
                   s.roic, s.wacc, s.roic_minus_wacc,
                   m.trade_date, m.market_cap, m.pe_ttm, m.pb,
                   ROUND(s.val_low/1e8,2) AS intrinsic_low,
                   ROUND(s.val_final/1e8,2) AS intrinsic_value,
                   ROUND(s.val_high/1e8,2) AS intrinsic_high,
                   ROUND((s.val_final/1e8/NULLIF(m.market_cap,0)-1)*100,2) AS margin_of_safety,
                   GREATEST(0, ROUND(
                      (CASE WHEN s.val_final/1e8 > m.market_cap THEN 50 ELSE 0 END)
                    + (CASE WHEN s.roic_minus_wacc > 0 THEN 20 ELSE 0 END)
                    + (CASE WHEN s.roic > 0.10 THEN 15 ELSE 0 END)
                    + (CASE WHEN s.roic_minus_wacc > 0.05 THEN 15 ELSE 0 END)
                    - COALESCE(s.risk_penalty,0), 0)) AS score,
                   sv.sector_name, sv.pe_median, sv.pb_median
            FROM ads_dmdl_static s
            JOIN ads_dmdl_mkt_daily m ON m.stock_code = s.stock_code
              AND m.trade_date = (SELECT MAX(trade_date) FROM ads_dmdl_mkt_daily)
            LEFT JOIN ads_dmdl_sector_val sv ON sv.sector_code = (
                SELECT ss.sector_code FROM stock_sectors ss
                JOIN sectors se ON ss.sector_code=se.sector_code
                WHERE ss.stock_code=s.stock_code AND se.category='industry'
                  AND se.level<=1 AND se.sector_name NOT LIKE 'TDX%%' LIMIT 1)
              AND sv.trade_date = m.trade_date
            WHERE s.stock_code = %s
            LIMIT 1
        """, (stock_code,))
    where = ["m.market_cap >= %s"]
    params = [min_cap]
    where.append("FIND_IN_SET(s.earnings_quality, %s)")
    params.append(eq_quality)
    if min_score > 0:
        where.append("score >= %s")
        params.append(min_score)
    if stage:
        where.append("s.life_stage = %s")
        params.append(stage)
    sql = f"""
        SELECT s.stock_code, s.stock_name, s.life_stage, s.earnings_quality, s.risk_penalty,
               s.roic, s.wacc, s.roic_minus_wacc,
               m.trade_date, m.market_cap, m.pe_ttm, m.pb,
               v.intrinsic_low, v.intrinsic_value, v.intrinsic_high,
               v.margin_of_safety, v.score,
               v.sector_name, v.pe_median, v.pb_median
        FROM v_dmdl_valuation v
        JOIN ads_dmdl_static s ON s.stock_code = v.stock_code
        JOIN ads_dmdl_mkt_daily m ON m.stock_code = v.stock_code AND m.trade_date = v.trade_date
        WHERE {' AND '.join(where)}
        ORDER BY v.score DESC, v.margin_of_safety DESC
        LIMIT %s
    """
    params.append(limit)
    return query(sql, params)


@router.get('/dmdl/stock/{code}')
def dmdl_stock(code: str):
    row = query("""
        SELECT s.stock_code, s.stock_name, s.report_date, s.life_stage,
               s.roic, s.wacc, s.roic_minus_wacc, s.earnings_quality, s.risk_penalty,
               s.norm_profit_5y, s.ttm_profit, s.growth_rate,
               s.val_eps_normal, s.val_dcf, s.val_bv,
               s.val_low, s.val_high, s.val_final,
               m.trade_date, m.close_price, m.market_cap, m.pe_ttm, m.pb,
               v.intrinsic_low, v.intrinsic_value, v.intrinsic_high,
               v.margin_of_safety, v.score,
               v.sector_name, v.pe_median, v.pb_median
        FROM ads_dmdl_static s
        LEFT JOIN ads_dmdl_mkt_daily m ON m.stock_code = s.stock_code
          AND m.trade_date = (SELECT MAX(trade_date) FROM ads_dmdl_mkt_daily)
        LEFT JOIN v_dmdl_valuation v ON v.stock_code = s.stock_code
        WHERE s.stock_code = %s
    """, (code,))
    if not row:
        return {'status': 'error', 'message': f'未找到 {code}'}
    return row[0]


@router.get('/dmdl/sector-val')
def dmdl_sector_val():
    return query("""
        SELECT sector_code, sector_name, trade_date, stock_count,
               sector_pe, sector_pb, pe_median, pe_pctl_low, pe_pctl_high,
               pb_median, pb_pctl_low, pb_pctl_high, fair_pe, fair_pb
        FROM ads_dmdl_sector_val
        WHERE trade_date = (SELECT MAX(trade_date) FROM ads_dmdl_sector_val)
        ORDER BY stock_count DESC
    """)


@router.get('/dmdl/status')
def dmdl_status():
    static = query("SELECT COUNT(*) c, MAX(updated_at) d FROM ads_dmdl_static")
    mkt = query("SELECT COUNT(*) c, MAX(trade_date) d FROM ads_dmdl_mkt_daily")
    sector = query("SELECT COUNT(*) c, MAX(trade_date) d FROM ads_dmdl_sector_val")
    view = query("SELECT COUNT(*) c FROM v_dmdl_valuation")
    return {
        'static': {'count': static[0]['c'] if static else 0, 'updated': str(static[0]['d']) if static else ''},
        'mkt': {'count': mkt[0]['c'] if mkt else 0, 'latest_date': str(mkt[0]['d']) if mkt else ''},
        'sector': {'count': sector[0]['c'] if sector else 0, 'latest_date': str(sector[0]['d']) if sector else ''},
        'valuation_view': {'count': view[0]['c'] if view else 0},
    }


@router.post('/dmdl/update')
def dmdl_update():
    if not _dmdl_lock.acquire(blocking=False):
        return {'status': 'running', 'message': '估值预计算任务已在执行中'}
    from ...compute_dmdl import compute_static, compute_mkt, compute_sector_val
    import pymysql
    from ..database import get_conn

    def _run():
        conn = get_conn()
        try:
            log_path = Path('/tmp/dmdl_update.log')
            with open(log_path, 'w') as f:
                f.write('')
            def wlog(msg):
                with open(log_path, 'a') as f:
                    f.write(msg + '\n')
            wlog('静态估值重算...')
            compute_static(conn, wlog)
            wlog('市值快照更新...')
            td = compute_mkt(conn, wlog)
            wlog('行业基准更新...')
            compute_sector_val(conn, wlog, td)
            cur = conn.cursor()
            cur.execute(open('/home/rick/workspace/ai-trading/src/compute_dmdl.py', encoding='utf-8')
                        .read().split('VIEW_SQL = """')[1].split('"""')[0])
            conn.commit()
            wlog('视图已刷新')
        except Exception as e:
            with open('/tmp/dmdl_update.log', 'a') as f:
                f.write(f'ERROR: {e}\n')
        finally:
            conn.close()
            _dmdl_lock.release()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {'status': 'started', 'message': '达摩达兰估值预计算已启动（后台运行）'}


@router.get('/dmdl/update/status')
def dmdl_update_status():
    if _dmdl_lock.locked():
        status = 'running'
    else:
        status = 'idle'
    log_tail = ''
    try:
        from pathlib import Path
        lines = Path('/tmp/dmdl_update.log').read_text(encoding='utf-8').strip().split('\n')
        log_tail = '\n'.join(lines[-5:])
    except Exception:
        pass
    return {'status': status, 'log_tail': log_tail}
