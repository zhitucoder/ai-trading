#!/usr/bin/env python3
"""Fetch dividend data for all A-shares from East Money datacenter API.
Writes to stock_dividend table.

Usage:
  python3 scripts/fetch_dividend.py [--resume] [--workers 8] [--limit N]
"""

import sys
import time
import json
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'aitrading123',
    'database': 'ai_trading',
    'charset': 'utf8mb4',
    'cursorclass': DictCursor,
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://emweb.securities.eastmoney.com/',
}

API_URL = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
REPORT_NAME = 'RPT_SHAREBONUS_DET'
MAX_WORKERS = 8
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
PAGE_SIZE = 100


def get_db():
    return pymysql.connect(**DB_CONFIG)


def get_all_stock_codes(db):
    with db.cursor() as cur:
        cur.execute("""
            SELECT stock_code FROM stocks
            WHERE stock_code REGEXP '^(6|0|3)[0-9]{5}$'
            ORDER BY stock_code
        """)
        return [row['stock_code'] for row in cur.fetchall()]


def get_already_fetched(db):
    with db.cursor() as cur:
        cur.execute("SELECT DISTINCT stock_code FROM stock_dividend")
        return {row['stock_code'] for row in cur.fetchall()}


def fetch_one_stock(symbol_code, since=None):
    """Fetch all dividend records for one stock from East Money datacenter API.

    since: 增量模式 —— 仅拉取除息日/预案公告日 ≥ since 的记录（UPSERT 覆盖实现幂等更新）。
    """
    records = []
    page = 1
    while True:
        flt = f'(SECURITY_CODE="{symbol_code}")'
        if since:
            flt += f'(EX_DIVIDEND_DATE >= \'{since}\' OR PLAN_NOTICE_DATE >= \'{since}\')'
        params = {
            'reportName': REPORT_NAME,
            'columns': 'ALL',
            'filter': flt,
            'pageNumber': str(page),
            'pageSize': str(PAGE_SIZE),
            'sortColumns': 'REPORT_DATE',
            'sortTypes': '-1',
        }
        r = requests.get(API_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        d = r.json()
        if not d.get('success') or not d.get('result'):
            break
        rows = d['result'].get('data') or []
        if not rows:
            break
        for row in rows:
            rec = _to_record(symbol_code, row)
            if rec:
                records.append(rec)
        total_pages = d['result'].get('pages', 1)
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.05)
    return records


def _to_record(code, row):
    report_date = _date(row.get('REPORT_DATE'))
    if not report_date:
        return None
    eps = _num(row.get('BASIC_EPS'))
    cash_per_10 = _num(row.get('PRETAX_BONUS_RMB'))
    bonus = round(cash_per_10 / 10, 6) if cash_per_10 is not None else None
    payout = None
    if bonus is not None and eps is not None and eps > 0:
        payout = round(bonus / eps * 100, 4)

    return {
        'stock_code': code,
        'report_date': report_date,
        'assign_progress': str(row.get('ASSIGN_PROGRESS') or ''),
        'plan_profile': str(row.get('IMPL_PLAN_PROFILE') or '') or None,
        'cash_per_10': cash_per_10,
        'bonus_per_share': bonus,
        'total_cash': _num(row.get('TOTAL_CASH')) if row.get('TOTAL_CASH') else None,
        'send_ratio': _num(row.get('BONUS_IT_RATIO')) if row.get('BONUS_IT_RATIO') else None,
        'trans_ratio': _num(row.get('IT_RATIO')) if row.get('IT_RATIO') else None,
        'dividend_yield': _num(row.get('DIVIDENT_RATIO')) if row.get('DIVIDENT_RATIO') else None,
        'payout_ratio': payout,
        'eps': eps,
        'plan_notice_date': _date(row.get('PLAN_NOTICE_DATE')),
        'equity_record_date': _date(row.get('EQUITY_RECORD_DATE')),
        'ex_dividend_date': _date(row.get('EX_DIVIDEND_DATE')),
        'notice_date': _date(row.get('NOTICE_DATE')),
        'is_mid_year': 1 if report_date.month in (3, 6, 9) else 0,
    }


def _date(val):
    if not val:
        return None
    s = str(val)[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _num(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def write_records(db, records):
    if not records:
        return
    sql = """
        INSERT INTO stock_dividend
        (stock_code, report_date, assign_progress, plan_profile, cash_per_10,
         bonus_per_share, total_cash, send_ratio, trans_ratio, dividend_yield,
         payout_ratio, eps, plan_notice_date, equity_record_date, ex_dividend_date,
         notice_date, is_mid_year, source)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'eastmoney')
        ON DUPLICATE KEY UPDATE
            assign_progress=VALUES(assign_progress),
            plan_profile=VALUES(plan_profile),
            cash_per_10=VALUES(cash_per_10),
            bonus_per_share=VALUES(bonus_per_share),
            total_cash=VALUES(total_cash),
            send_ratio=VALUES(send_ratio),
            trans_ratio=VALUES(trans_ratio),
            dividend_yield=VALUES(dividend_yield),
            payout_ratio=VALUES(payout_ratio),
            eps=VALUES(eps),
            plan_notice_date=VALUES(plan_notice_date),
            equity_record_date=VALUES(equity_record_date),
            ex_dividend_date=VALUES(ex_dividend_date),
            notice_date=VALUES(notice_date),
            is_mid_year=VALUES(is_mid_year),
            source=VALUES(source)
    """
    vals = [tuple(r[k] for k in (
        'stock_code', 'report_date', 'assign_progress', 'plan_profile', 'cash_per_10',
        'bonus_per_share', 'total_cash', 'send_ratio', 'trans_ratio', 'dividend_yield',
        'payout_ratio', 'eps', 'plan_notice_date', 'equity_record_date', 'ex_dividend_date',
        'notice_date', 'is_mid_year')) for r in records]
    with db.cursor() as cur:
        cur.executemany(sql, vals)
    db.commit()


def process_one_stock(symbol_code, since=None):
    try:
        records = fetch_one_stock(symbol_code, since)
        return symbol_code, records, None
    except Exception as e:
        return symbol_code, [], str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', action='store_true', help='Skip already-fetched stocks')
    parser.add_argument('--workers', type=int, default=MAX_WORKERS)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--codes', help='Comma-separated stock codes (test)')
    parser.add_argument('--since', help='增量模式: 只抓除息日/预案公告日 >= 该日期(YYYY-MM-DD)的记录')
    args = parser.parse_args()

    db = get_db()
    if args.codes:
        all_codes = [c.strip() for c in args.codes.split(',')]
    else:
        all_codes = get_all_stock_codes(db)
        if args.resume:
            already = get_already_fetched(db)
            all_codes = [c for c in all_codes if c not in already]
            print(f'Resume: {len(already)} skipped, {len(all_codes)} remaining')
    if args.limit > 0:
        all_codes = all_codes[:args.limit]

    total = len(all_codes)
    print(f'Total stocks: {total}')
    ok = fail = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(process_one_stock, c, args.since): c for c in all_codes}
        for i, fut in enumerate(as_completed(futs), 1):
            code, records, err = fut.result()
            if err:
                fail += 1
                print(f'[{i}/{total}] {code}: FAIL {err}', flush=True)
            else:
                write_records(db, records)
                ok += 1
                print(f'[{i}/{total}] {code}: {len(records)} records', flush=True)

    print(f'\nDone: ok={ok} fail={fail} elapsed={time.time()-t0:.0f}s')
    db.close()


if __name__ == '__main__':
    main()
