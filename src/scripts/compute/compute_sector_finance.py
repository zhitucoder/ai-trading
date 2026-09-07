#!/home/rick/miniconda3/envs/aitrading/bin/python
import pymysql
DB = dict(host='127.0.0.1', port=3306, user='root', password='aitrading123',
          database='ai_trading', charset='utf8mb4')

def main():
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS ads_sector_finance")
    cur.execute("""
        CREATE TABLE ads_sector_finance (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sector_code VARCHAR(10) NOT NULL,
            report_date DATE NOT NULL,
            total_revenue DECIMAL(20,2),
            total_net_profit DECIMAL(20,2),
            revenue_growth DECIMAL(10,4),
            net_profit_growth DECIMAL(10,4),
            UNIQUE KEY uk_sector_date (sector_code, report_date),
            KEY idx_sector (sector_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        INSERT INTO ads_sector_finance (sector_code, report_date, total_revenue, total_net_profit)
        SELECT ss.sector_code, fq.report_date,
               ROUND(SUM(fq.q_revenue), 2),
               ROUND(SUM(fq.q_parent_net_profit), 2)
        FROM stock_sectors ss
        JOIN fin_quarterly fq ON ss.stock_code = fq.stock_code
        WHERE ss.category = 'industry'
        GROUP BY ss.sector_code, fq.report_date
        HAVING SUM(fq.q_revenue) > 0
    """)
    conn.commit()
    print(f'Inserted {cur.rowcount} base rows')

    cur.execute("""
        UPDATE ads_sector_finance cur
        JOIN ads_sector_finance prev ON cur.sector_code = prev.sector_code
            AND prev.report_date = DATE_SUB(cur.report_date, INTERVAL 1 YEAR)
        SET cur.revenue_growth = ROUND((cur.total_revenue - prev.total_revenue) / prev.total_revenue * 100, 2),
            cur.net_profit_growth = ROUND((cur.total_net_profit - prev.total_net_profit) / prev.total_net_profit * 100, 2)
        WHERE prev.total_revenue > 0
    """)
    conn.commit()
    print(f'YoY growth: {cur.rowcount} rows')

    cur.execute("SELECT COUNT(DISTINCT sector_code), COUNT(*) FROM ads_sector_finance")
    r = cur.fetchone()
    print(f'Done: {r[0]} sectors, {r[1]} rows')
    conn.close()

if __name__ == '__main__':
    main()
