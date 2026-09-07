#!/home/rick/miniconda3/envs/aitrading/bin/python
"""预计算行业景气度指标，写入 sector_prosperity 表。

运行: python src/compute_prosperity.py
"""

import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

SQL = """
SELECT ss.sector_code,
  AVG(CASE WHEN i.operating_revenue > 0 AND prev.operating_revenue > 0
      THEN (i.operating_revenue - prev.operating_revenue) / prev.operating_revenue * 100
      END) AS avg_rev_growth,
  AVG(r.roe) AS avg_roe,
  AVG(CASE WHEN bs.total_assets > 0
      THEN bs.total_liabilities / bs.total_assets * 100
      END) AS avg_debt_ratio
FROM stock_sectors ss
JOIN fin_income i ON ss.stock_code = i.stock_code
  AND i.report_date = (SELECT MAX(report_date) FROM fin_income WHERE stock_code = i.stock_code)
LEFT JOIN fin_income prev ON ss.stock_code = prev.stock_code
  AND prev.report_date = DATE(CONCAT(YEAR(i.report_date) - 1, '-', MONTH(i.report_date), '-', DAY(i.report_date)))
LEFT JOIN fin_ratios r ON ss.stock_code = r.stock_code
  AND r.report_date = i.report_date
LEFT JOIN fin_balance_sheet bs ON ss.stock_code = bs.stock_code
  AND bs.report_date = i.report_date
GROUP BY ss.sector_code
"""

UPSERT = """
INSERT INTO sector_prosperity (sector_code, avg_rev_growth, avg_roe, avg_debt_ratio, score, level, computed_at)
VALUES (%s, %s, %s, %s, %s, %s, NOW())
ON DUPLICATE KEY UPDATE
  avg_rev_growth = VALUES(avg_rev_growth),
  avg_roe = VALUES(avg_roe),
  avg_debt_ratio = VALUES(avg_debt_ratio),
  score = VALUES(score),
  level = VALUES(level),
  computed_at = NOW()
"""


def calc_level(rev_g, roe, debt):
    rev_score = min(max((rev_g - 5) / 30 * 100, 0), 100)
    roe_score = min(max(roe / 20 * 100, 0), 100)
    debt_score = min(max((70 - debt) / 40 * 100, 0), 100)
    score = 0.4 * rev_score + 0.35 * roe_score + 0.25 * debt_score

    if score >= 70:
        level = 'high'
    elif score >= 40:
        level = 'medium'
    else:
        level = 'low'
    return round(score, 2), level


def main():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    try:
        with conn.cursor() as cur:
            print('Computing sector prosperity...')
            cur.execute(SQL)
            rows = cur.fetchall()
            print(f'Got {len(rows)} sectors')

            data = []
            counts = {'high': 0, 'medium': 0, 'low': 0}
            for r in rows:
                rev_g = float(r['avg_rev_growth'] or 0)
                roe = float(r['avg_roe'] or 0)
                debt = float(r['avg_debt_ratio'] or 50)
                score, level = calc_level(rev_g, roe, debt)
                counts[level] += 1
                data.append((r['sector_code'], rev_g, roe, debt, score, level))

            cur.executemany(UPSERT, data)
            conn.commit()
            print(f'Done: high={counts["high"]}, medium={counts["medium"]}, low={counts["low"]}')
            print(f'Updated {len(data)} sectors in sector_prosperity')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
