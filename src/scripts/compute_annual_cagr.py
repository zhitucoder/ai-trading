"""年化增长率(CAGR)计算：从 fin_income 年度数据计算，写入 ads_annual_cagr"""
import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')


def calc_cagr(latest, earliest, years):
    if latest is None or earliest is None or float(earliest) <= 0 or years <= 0:
        return None
    ratio = float(latest) / float(earliest)
    if ratio <= 0:
        return None
    return round((ratio ** (1.0 / years) - 1) * 100, 4)


def compute():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    try:
        stocks = conn.cursor()
        stocks.execute("SELECT stock_code FROM stocks ORDER BY stock_code")
        all_stocks = [r['stock_code'] for r in stocks.fetchall()]

        cur_a = conn.cursor()
        total = len(all_stocks)
        batch = []
        BATCH_SIZE = 500

        for idx, code in enumerate(all_stocks):
            cur_a.execute("""
                SELECT fi.report_date, fi.operating_revenue, fi.parent_net_profit,
                       bs.total_assets
                FROM fin_income fi
                LEFT JOIN fin_balance_sheet bs ON bs.stock_code = fi.stock_code AND bs.report_date = fi.report_date
                WHERE fi.stock_code = %s AND MONTH(fi.report_date) = 12 AND DAY(fi.report_date) = 31
                  AND fi.operating_revenue IS NOT NULL AND fi.operating_revenue > 0
                ORDER BY fi.report_date DESC
                LIMIT 11
            """, [code])
            rows = cur_a.fetchall()

            rev_cagr_3y = rev_cagr_5y = rev_cagr_10y = None
            profit_cagr_3y = profit_cagr_5y = profit_cagr_10y = None
            report_date = None

            if rows and len(rows) >= 2:
                rows_rev = list(reversed(rows))
                latest = rows_rev[-1]
                report_date = latest['report_date']

                def rev_reliable(yr_back):
                    if yr_back < len(rows_rev):
                        r = rows_rev[-(yr_back + 1)]
                        rev = r['operating_revenue']
                        profit = r['parent_net_profit']
                        assets = r.get('total_assets')
                        if rev is None or float(rev) <= 0:
                            return False
                        if profit is not None and abs(float(profit)) > float(rev) * 2:
                            return False
                        if assets is not None and float(assets) > 0 and float(rev) / float(assets) < 0.001:
                            return False
                        return True
                    return True

                rev_cagr_3y = calc_cagr(
                    rows_rev[-1]['operating_revenue'],
                    rows_rev[-3]['operating_revenue'], 3) if len(rows_rev) >= 3 and rev_reliable(0) and rev_reliable(2) else None
                rev_cagr_5y = calc_cagr(
                    rows_rev[-1]['operating_revenue'],
                    rows_rev[-5]['operating_revenue'], 5) if len(rows_rev) >= 5 and rev_reliable(0) and rev_reliable(4) else None
                rev_cagr_10y = calc_cagr(
                    rows_rev[-1]['operating_revenue'],
                    rows_rev[-10]['operating_revenue'], 10) if len(rows_rev) >= 10 and rev_reliable(0) and rev_reliable(9) else None

                profit_cagr_3y = calc_cagr(
                    rows_rev[-1]['parent_net_profit'],
                    rows_rev[-3]['parent_net_profit'], 3) if len(rows_rev) >= 3 else None
                profit_cagr_5y = calc_cagr(
                    rows_rev[-1]['parent_net_profit'],
                    rows_rev[-5]['parent_net_profit'], 5) if len(rows_rev) >= 5 else None
                profit_cagr_10y = calc_cagr(
                    rows_rev[-1]['parent_net_profit'],
                    rows_rev[-10]['parent_net_profit'], 10) if len(rows_rev) >= 10 else None

            if report_date:
                batch.append((code, str(report_date), rev_cagr_3y, rev_cagr_5y, rev_cagr_10y,
                              profit_cagr_3y, profit_cagr_5y, profit_cagr_10y))

            if len(batch) >= BATCH_SIZE or idx == total - 1:
                w = conn.cursor()
                w.executemany("""
                    REPLACE INTO ads_annual_cagr
                    (stock_code, report_date, rev_cagr_3y, rev_cagr_5y, rev_cagr_10y,
                     profit_cagr_3y, profit_cagr_5y, profit_cagr_10y)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, batch)
                conn.commit()
                batch.clear()

            if (idx + 1) % 1000 == 0:
                print(f"  processed {idx + 1}/{total}")

        print(f"Done. {total} stocks processed.")

    finally:
        conn.close()


if __name__ == '__main__':
    compute()
