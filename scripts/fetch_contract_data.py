#!/home/rick/miniconda3/envs/aitrading/bin/python3
"""
Fetch 合同负债(CONTRACT_LIAB) and 合同资产(CONTRACT_ASSET) for ALL A-shares
from East Money API. Writes to fin_contract_bs table.

Usage: python3 fetch_contract_data.py [--resume]
"""

import sys
import time
import json
import argparse
import traceback
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
import pymysql
from bs4 import BeautifulSoup

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'aitrading123',
    'database': 'ai_trading',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://emweb.securities.eastmoney.com/',
}

MIN_DATE = '2021-01-01'
MAX_WORKERS = 8
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2


def get_db():
    return pymysql.connect(**DB_CONFIG)


def get_all_stock_codes(db):
    """Get SH/SZ stock codes from our db."""
    with db.cursor() as cur:
        cur.execute("""
            SELECT stock_code FROM stocks 
            WHERE stock_code REGEXP '^(6|0|3)[0-9]{5}$'
            ORDER BY stock_code
        """)
        return [row[0] for row in cur.fetchall()]


def get_already_fetched(db):
    """Get codes we already have data for (for resume)."""
    with db.cursor() as cur:
        cur.execute("SELECT DISTINCT stock_code FROM fin_contract_bs")
        return {row[0] for row in cur.fetchall()}


def fetch_company_type(symbol_code_with_exchange):
    """Get company type from East Money page. Pass 'SH600150' or 'SZ000001'."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            url = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index"
            params = {"type": "web", "code": symbol_code_with_exchange.lower()}
            r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            soup = BeautifulSoup(r.text, 'html.parser')
            elem = soup.find(attrs={"id": "hidctype"})
            if elem is None:
                raise ValueError("hidctype not found in page")
            return elem["value"]
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def fetch_contract_data(symbol_code):
    """
    Fetch balance sheet data for one stock from East Money.
    Returns list of dicts with contract-related fields.
    """
    exchange = 'SH' if symbol_code.startswith('6') else 'SZ'
    symbol_with_exchange = f"{exchange}{symbol_code}"
    
    try:
        company_type = fetch_company_type(symbol_with_exchange)
    except Exception as e:
        print(f"  [SKIP] {symbol_code}: cannot get company type - {e}")
        return []

    # Fetch available dates
    all_dates = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            url_dates = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/zcfzbDateAjaxNew"
            params_dates = {"companyType": company_type, "reportDateType": "0", "code": symbol_with_exchange}
            r = requests.get(url_dates, params=params_dates, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            data_json = r.json()
            all_dates = [d["REPORT_DATE"] for d in data_json["data"]]
            if all_dates:
                break
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"  [SKIP] {symbol_code}: cannot get dates - {e}")
            return []

    # Filter to last 5 years
    recent_dates = [d for d in all_dates if d >= MIN_DATE]
    if not recent_dates:
        return []

    # Batch dates (5 per request)
    date_batches = [",".join(recent_dates[i:i+5]) for i in range(0, len(recent_dates), 5)]

    records = []
    for batch in date_batches:
        for attempt in range(MAX_RETRIES + 1):
            try:
                url_data = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/zcfzbAjaxNew"
                params_data = {
                    "companyType": company_type,
                    "reportDateType": "0",
                    "reportType": "1",
                    "dates": batch,
                    "code": symbol_with_exchange,
                }
                r = requests.get(url_data, params=params_data, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                result = r.json()
                if "data" not in result:
                    break
                for row in result["data"]:
                    records.append({
                        'stock_code': symbol_code,
                        'report_date': row['REPORT_DATE'][:10],
                        'contract_liab': _num(row.get('CONTRACT_LIAB')),
                        'contract_asset': _num(row.get('CONTRACT_ASSET')),
                        'advance_receivables': _num(row.get('ADVANCE_RECEIVABLES')),
                        'total_assets': _num(row.get('TOTAL_ASSETS')),
                        'total_liabilities': _num(row.get('TOTAL_LIABILITIES')),
                    })
                break  # success
            except Exception as e:
                if attempt < MAX_RETRIES:
                    time.sleep(2 * (attempt + 1))
                    continue
                print(f"  [WARN] {symbol_code}: batch error after {MAX_RETRIES+1} tries - {e}")
                break

    return records


def _num(val):
    """Convert value to float or None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def write_records(db, records):
    """Batch insert records into fin_contract_bs."""
    if not records:
        return
    with db.cursor() as cur:
        sql = """
            INSERT INTO fin_contract_bs 
            (stock_code, report_date, contract_liab, contract_asset, 
             advance_receivables, total_assets, total_liabilities, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'eastmoney')
            ON DUPLICATE KEY UPDATE
                contract_liab=VALUES(contract_liab),
                contract_asset=VALUES(contract_asset),
                advance_receivables=VALUES(advance_receivables),
                total_assets=VALUES(total_assets),
                total_liabilities=VALUES(total_liabilities)
        """
        vals = [(r['stock_code'], r['report_date'], r['contract_liab'],
                 r['contract_asset'], r['advance_receivables'],
                 r['total_assets'], r['total_liabilities']) for r in records]
        cur.executemany(sql, vals)
    db.commit()


def process_one_stock(symbol_code):
    """Process a single stock: fetch + return records."""
    try:
        records = fetch_contract_data(symbol_code)
        return symbol_code, records, None
    except Exception as e:
        return symbol_code, [], str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', action='store_true', help='Skip already-fetched stocks')
    parser.add_argument('--workers', type=int, default=MAX_WORKERS)
    parser.add_argument('--limit', type=int, default=0, help='Max stocks to process (for testing)')
    args = parser.parse_args()

    db = get_db()
    all_codes = get_all_stock_codes(db)

    if args.resume:
        already = get_already_fetched(db)
        all_codes = [c for c in all_codes if c not in already]
        print(f"Resume mode: {len(already)} stocks skipped, {len(all_codes)} remaining")

    if args.limit > 0:
        all_codes = all_codes[:args.limit]

    total = len(all_codes)
    print(f"Total stocks to process: {total}")
    print(f"Workers: {args.workers}")
    print(f"Date filter: >= {MIN_DATE}")
    print(f"Started at: {datetime.now()}")
    print("-" * 60)

    t0 = time.time()
    done = 0
    errors = 0
    total_records = 0
    batch_records = []
    batch_size = 100  # Write every 100 stocks

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_one_stock, code): code for code in all_codes}
        for future in as_completed(futures):
            code, records, error = future.result()
            done += 1
            total_records += len(records)
            batch_records.extend(records)

            if error:
                errors += 1
                status = f"ERR({error[:40]})"
            elif not records:
                status = "no-data"
            else:
                status = f"ok({len(records)}q)"

            elapsed = time.time() - t0
            rate = done / elapsed * 60 if elapsed > 0 else 0
            pct = done / total * 100
            print(f"  [{done}/{total} {pct:.0f}%] {code} {status} | {rate:.0f}/min | {total_records} records")

            # Periodic batch write
            if len(batch_records) >= batch_size:
                write_records(db, batch_records)
                print(f"  >>> Written {len(batch_records)} records to DB")
                batch_records = []

    # Final write
    if batch_records:
        write_records(db, batch_records)
        print(f"  >>> Written {len(batch_records)} records to DB (final)")

    elapsed = time.time() - t0
    print("-" * 60)
    print(f"Finished at: {datetime.now()}")
    print(f"Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"Processed: {done}/{total} stocks")
    print(f"Errors: {errors}")
    print(f"Total records: {total_records}")

    db.close()


if __name__ == '__main__':
    main()
