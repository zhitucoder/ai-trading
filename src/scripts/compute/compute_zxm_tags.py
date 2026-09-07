import sys
sys.path.insert(0, '/home/rick/workspace/ai-trading')
import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

TAG_COLS = [
    'stock_code', 'stock_name', 'report_date', 'data_date',
    'asset_type', 'asset_weight', 'cash_status', 'inventory_risk', 'contract_liab_tag',
    'hematopoiesis', 'hematopoiesis_ratio', 'leverage', 'debt_ratio',
    'margin_level', 'core_profit_margin', 'profit_source', 'minority_ratio', 'profit_status',
    'match_fa_rev', 'match_fa_rev_ratio',
    'match_rev_profit', 'match_rev_profit_ratio',
    'match_profit_ocf', 'match_profit_ocf_ratio',
    'cashflow_type', 'ocf_to_np', 'fcf_status',
    'growth_rate', 'growth_quality',
    'risk_flags', 'overall_rating', 'pattern_label',
]


def run():
    from src.app.zxm_tags import compute_tags
    from datetime import date

    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    try:
        stocks = conn.cursor()
        stocks.execute("SELECT stock_code FROM stocks ORDER BY stock_code")
        all_stocks = [r['stock_code'] for r in stocks.fetchall()]
        total = len(all_stocks)
        today = str(date.today())

        batch = []
        errors = 0

        for idx, code in enumerate(all_stocks):
            try:
                tags = compute_tags(code)
                if tags is None:
                    continue
                row = {c: tags.get(c) for c in TAG_COLS if c in tags}
                row['data_date'] = today
                for c in TAG_COLS:
                    if c not in row:
                        row[c] = None
                batch.append(row)
            except Exception as e:
                errors += 1

            if len(batch) >= 500 or idx == total - 1:
                w = conn.cursor()
                placeholders = ', '.join(['%s'] * len(TAG_COLS))
                cols = ', '.join(TAG_COLS)
                values = []
                for r in batch:
                    values.append(tuple(r.get(c) for c in TAG_COLS))
                sql = f"REPLACE INTO zxm_stock_tags ({cols}) VALUES ({placeholders})"
                w.executemany(sql, values)
                conn.commit()
                batch.clear()

            if (idx + 1) % 1000 == 0:
                print(f"  {idx + 1}/{total}, errors={errors}")

        print(f"Done. {total} stocks, {errors} errors")
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    run()
