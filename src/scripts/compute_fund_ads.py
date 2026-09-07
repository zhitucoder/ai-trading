#!/home/rick/miniconda3/envs/aitrading/bin/python
"""公募基金持仓预计算：生成 ads_fund_stock_change / ads_fund_sector_flow / ads_fund_stock_trend。

基于 ads_stock_fund 预聚合表，只分析 Q2/Q4 完整数据。
运行: python src/compute_fund_ads.py
"""
import time
from datetime import date
import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')


def _drop_table(cur, name):
    cur.execute(f"DROP TABLE IF EXISTS {name}")


def create_tables(cur):
    for t in ('ads_fund_stock_change', 'ads_fund_sector_flow', 'ads_fund_stock_trend'):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
    cur.execute("""
        CREATE TABLE ads_fund_stock_change (
          id INT AUTO_INCREMENT PRIMARY KEY,
          stock_code VARCHAR(10) NOT NULL,
          end_date VARCHAR(8) NOT NULL COMMENT '当前季度截止日',
          prev_end_date VARCHAR(8) NOT NULL COMMENT '上季度截止日',
          quarter CHAR(6) COMMENT '当前季度标签',
          fund_count INT COMMENT '当前基金数',
          prev_fund_count INT COMMENT '上季度基金数',
          fund_count_change INT COMMENT '基金数变化',
          total_amount BIGINT COMMENT '当前持仓股数',
          prev_total_amount BIGINT COMMENT '上季度持仓股数',
          amount_change BIGINT COMMENT '持仓股数变化',
          amount_change_pct DECIMAL(10,2) COMMENT '持仓变化率(%)',
          total_mkv DECIMAL(20,2) COMMENT '当前持仓市值',
          prev_total_mkv DECIMAL(20,2) COMMENT '上季度持仓市值',
          mkv_change DECIMAL(20,2) COMMENT '市值变化',
          active_count INT COMMENT '当前主动基金数',
          passive_count INT COMMENT '当前被动基金数',
          active_ratio DECIMAL(5,2) COMMENT '主动基金占比(%)',
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_stock_date (stock_code, end_date),
          KEY idx_end_date (end_date),
          KEY idx_change_pct (amount_change_pct)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE ads_fund_sector_flow (
          id INT AUTO_INCREMENT PRIMARY KEY,
          sector_type VARCHAR(20) NOT NULL COMMENT 'industry/concept/region',
          sector_name VARCHAR(50) NOT NULL COMMENT '板块名称',
          end_date VARCHAR(8) NOT NULL COMMENT '季度截止日',
          quarter CHAR(6),
          stock_count INT COMMENT '板块内股票数',
          total_fund_count INT COMMENT '板块内基金持仓总次数',
          total_mkv DECIMAL(20,2) COMMENT '板块基金总持仓市值',
          prev_total_mkv DECIMAL(20,2) COMMENT '上季度板块总持仓市值',
          mkv_change DECIMAL(20,2) COMMENT '市值变化',
          mkv_change_pct DECIMAL(10,2) COMMENT '市值变化率(%)',
          avg_fund_count DECIMAL(10,1) COMMENT '平均每只股票被多少基金持有',
          `signal` CHAR(1) COMMENT 'A=加速流入 B=减速流出 C=减速流入 D=加速流出',
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_sector_date (sector_type, sector_name, end_date),
          KEY idx_end_date (end_date),
          KEY idx_signal (`signal`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE ads_fund_stock_trend (
          id INT AUTO_INCREMENT PRIMARY KEY,
          stock_code VARCHAR(10) NOT NULL,
          latest_end_date VARCHAR(8) COMMENT '最新季度',
          trend_score INT COMMENT '趋势得分(-4~+4)',
          trend_label VARCHAR(20) COMMENT '持续看好/偏好看好/中性/偏好看空/持续看空',
          increase_quarters INT COMMENT '增持季度数(0~4)',
          decrease_quarters INT COMMENT '减持季度数',
          consecutive_increase INT COMMENT '当前连续增持季度数',
          latest_change_pct DECIMAL(10,2) COMMENT '最新季度变化率(%)',
          fund_count INT COMMENT '当前基金数',
          total_mkv DECIMAL(20,2) COMMENT '当前持仓市值',
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_stock (stock_code),
          KEY idx_trend_score (trend_score)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def compute_stock_change(conn):
    """计算个股季度环比变化"""
    print("[1/3] computing ads_fund_stock_change ...")
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE ads_fund_stock_change")

    # 获取所有双季度（Q2/Q4）的 end_date，按时间排序
    cur.execute("""
        SELECT DISTINCT end_date, quarter
        FROM ads_stock_fund
        WHERE end_date LIKE '%0630' OR end_date LIKE '%1231'
        ORDER BY end_date
    """)
    quarters = cur.fetchall()

    # 构建 end_date -> prev_end_date 映射
    quarter_map = {}
    for i in range(1, len(quarters)):
        quarter_map[quarters[i]['end_date']] = {
            'prev_end_date': quarters[i-1]['end_date'],
            'quarter': quarters[i]['quarter']
        }

    total = 0
    for end_date, info in quarter_map.items():
        prev_end_date = info['prev_end_date']
        quarter = info['quarter']

        cur.execute("""
            INSERT INTO ads_fund_stock_change
              (stock_code, end_date, prev_end_date, quarter,
               fund_count, prev_fund_count, fund_count_change,
               total_amount, prev_total_amount, amount_change, amount_change_pct,
               total_mkv, prev_total_mkv, mkv_change,
               active_count, passive_count, active_ratio)
            SELECT
              a.stock_code,
              a.end_date,
              %s AS prev_end_date,
              %s AS quarter,
              a.fund_count,
              b.fund_count AS prev_fund_count,
              a.fund_count - b.fund_count AS fund_count_change,
              a.total_amount,
              b.total_amount AS prev_total_amount,
              a.total_amount - b.total_amount AS amount_change,
              CASE WHEN b.total_amount > 0
                THEN ROUND((a.total_amount - b.total_amount) / b.total_amount * 100, 2)
                ELSE NULL END AS amount_change_pct,
              a.total_mkv,
              b.total_mkv AS prev_total_mkv,
              a.total_mkv - b.total_mkv AS mkv_change,
              a.active_count,
              a.passive_count,
              CASE WHEN a.fund_count > 0
                THEN ROUND(a.active_count / a.fund_count * 100, 2)
                ELSE 0 END AS active_ratio
            FROM ads_stock_fund a
            JOIN ads_stock_fund b
              ON a.stock_code = b.stock_code AND b.end_date = %s
            WHERE a.end_date = %s
        """, (prev_end_date, quarter, prev_end_date, end_date))
        affected = cur.rowcount
        total += affected
        conn.commit()
        print(f"  {quarter}: {affected} rows")

    print(f"  total: {total} rows")


def compute_sector_flow(conn):
    """计算板块资金流向"""
    print("[2/3] computing ads_fund_sector_flow ...")
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE ads_fund_sector_flow")

    # 获取双季度列表
    cur.execute("""
        SELECT DISTINCT end_date, quarter
        FROM ads_stock_fund
        WHERE end_date LIKE '%0630' OR end_date LIKE '%1231'
        ORDER BY end_date
    """)
    quarters = cur.fetchall()

    quarter_map = {}
    for i in range(1, len(quarters)):
        quarter_map[quarters[i]['end_date']] = {
            'prev_end_date': quarters[i-1]['end_date'],
            'quarter': quarters[i]['quarter']
        }

    total = 0
    for end_date, info in quarter_map.items():
        prev_end_date = info['prev_end_date']
        quarter = info['quarter']

        for cat in ('industry', 'concept'):
            cur.execute("""
                INSERT INTO ads_fund_sector_flow
                  (sector_type, sector_name, end_date, quarter,
                   stock_count, total_fund_count, total_mkv,
                   prev_total_mkv, mkv_change, mkv_change_pct,
                   avg_fund_count, `signal`)
                SELECT
                  %s AS sector_type,
                  cur.sector_name,
                  %s AS end_date,
                  %s AS quarter,
                  cur.stock_count,
                  cur.total_fund_count,
                  cur.total_mkv,
                  COALESCE(prev.prev_total_mkv, 0) AS prev_total_mkv,
                  cur.total_mkv - COALESCE(prev.prev_total_mkv, 0) AS mkv_change,
                  CASE WHEN COALESCE(prev.prev_total_mkv, 0) > 0
                    THEN ROUND((cur.total_mkv - prev.prev_total_mkv) / prev.prev_total_mkv * 100, 2)
                    ELSE NULL END AS mkv_change_pct,
                  cur.avg_fund_count,
                  NULL AS `signal`
                FROM (
                  SELECT s.sector_name,
                         COUNT(DISTINCT a.stock_code) AS stock_count,
                         SUM(a.fund_count) AS total_fund_count,
                         SUM(a.total_mkv) AS total_mkv,
                         ROUND(AVG(a.fund_count), 1) AS avg_fund_count
                  FROM ads_stock_fund a
                  JOIN stock_sectors ss ON a.stock_code = ss.stock_code
                  JOIN sectors s ON ss.sector_code = s.sector_code
                  WHERE a.end_date = %s AND s.category = %s
                  GROUP BY s.sector_name
                ) cur
                LEFT JOIN (
                  SELECT s.sector_name,
                         SUM(a.total_mkv) AS prev_total_mkv
                  FROM ads_stock_fund a
                  JOIN stock_sectors ss ON a.stock_code = ss.stock_code
                  JOIN sectors s ON ss.sector_code = s.sector_code
                  WHERE a.end_date = %s AND s.category = %s
                  GROUP BY s.sector_name
                ) prev ON cur.sector_name = prev.sector_name
            """, (cat, end_date, quarter, end_date, cat, prev_end_date, cat))
            total += cur.rowcount
        conn.commit()
        print(f"  {quarter}: done")

    # 计算信号字段（分步：先建临时表，再更新）
    cur.execute("""
        CREATE TEMPORARY TABLE tmp_signal AS
        SELECT f1.id,
          CASE
            WHEN f1.mkv_change > 0 AND f2.mkv_change > 0
                 AND f1.mkv_change > f2.mkv_change THEN 'A'
            WHEN f1.mkv_change > 0 AND f2.mkv_change > 0 THEN 'B'
            WHEN f1.mkv_change < 0 AND f2.mkv_change < 0
                 AND f1.mkv_change < f2.mkv_change THEN 'D'
            WHEN f1.mkv_change < 0 AND f2.mkv_change < 0 THEN 'C'
            WHEN f1.mkv_change > 0 THEN 'A'
            WHEN f1.mkv_change < 0 THEN 'D'
            ELSE 'B'
          END AS new_signal
        FROM ads_fund_sector_flow f1
        JOIN ads_fund_sector_flow f2
          ON f1.sector_type = f2.sector_type
          AND f1.sector_name = f2.sector_name
          AND f2.end_date = (
            SELECT MAX(end_date) FROM ads_fund_sector_flow
            WHERE sector_type = f1.sector_type
              AND sector_name = f1.sector_name
              AND end_date < f1.end_date
          )
    """)
    cur.execute("""
        UPDATE ads_fund_sector_flow f1
        JOIN tmp_signal t ON f1.id = t.id
        SET f1.`signal` = t.new_signal
    """)
    cur.execute("DROP TEMPORARY TABLE tmp_signal")
    conn.commit()
    print(f"  signals updated, total: {total} rows")


def compute_stock_trend(conn):
    """计算个股趋势评分"""
    print("[3/3] computing ads_fund_stock_trend ...")
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE ads_fund_stock_trend")

    # 获取最近5个双季度的 end_date
    cur.execute("""
        SELECT DISTINCT end_date, quarter
        FROM ads_stock_fund
        WHERE end_date LIKE '%0630' OR end_date LIKE '%1231'
        ORDER BY end_date DESC
        LIMIT 5
    """)
    quarters = cur.fetchall()
    if len(quarters) < 2:
        print("  not enough quarters, skip")
        return

    latest_end = quarters[0]['end_date']

    # 获取所有股票
    cur.execute("SELECT DISTINCT stock_code FROM ads_stock_fund")
    stocks = [row['stock_code'] for row in cur.fetchall()]

    # 构建每只股票的季度数据
    stock_data = {}
    for sc in stocks:
        cur.execute("""
            SELECT end_date, fund_count, total_mkv, total_amount
            FROM ads_stock_fund
            WHERE stock_code = %s AND end_date IN (%s,%s,%s,%s,%s)
            ORDER BY end_date
        """, (sc, *[q['end_date'] for q in quarters]))
        rows = cur.fetchall()
        stock_data[sc] = rows

    # 计算趋势
    batch = []
    for sc, rows in stock_data.items():
        if len(rows) < 2:
            continue

        # 计算每个季度的变化
        changes = []
        for i in range(1, len(rows)):
            prev_amount = rows[i-1]['total_amount']
            curr_amount = rows[i]['total_amount']
            if prev_amount and prev_amount > 0:
                changes.append(curr_amount > prev_amount)
            else:
                changes.append(None)

        # 增持/减持季度数
        valid_changes = [c for c in changes if c is not None]
        increase_quarters = sum(1 for c in valid_changes if c)
        decrease_quarters = sum(1 for c in valid_changes if not c)

        # 连续增持（从最近往回数）
        consecutive = 0
        for c in reversed(valid_changes):
            if c:
                consecutive += 1
            else:
                break

        # 趋势评分
        score = 0
        if increase_quarters >= 3:
            score = 3
        elif increase_quarters == 2:
            score = 1
        elif increase_quarters == 1:
            score = -1
        else:
            score = -3

        if consecutive >= 2:
            score += 1
        elif decrease_quarters >= 2:
            score -= 1

        # 趋势标签
        if score >= 3:
            label = '持续看好'
        elif score >= 1:
            label = '偏好看好'
        elif score >= -1:
            label = '中性'
        elif score >= -3:
            label = '偏好看空'
        else:
            label = '持续看空'

        # 最新季度变化
        latest_row = rows[-1]
        prev_row = rows[-2] if len(rows) >= 2 else None
        latest_change = None
        if prev_row and prev_row['total_amount'] and prev_row['total_amount'] > 0:
            latest_change = round((latest_row['total_amount'] - prev_row['total_amount']) / prev_row['total_amount'] * 100, 2)

        batch.append((
            sc, latest_end, score, label,
            increase_quarters, decrease_quarters, consecutive,
            latest_change,
            latest_row['fund_count'],
            latest_row['total_mkv']
        ))

    # 批量插入
    cur.executemany("""
        INSERT INTO ads_fund_stock_trend
          (stock_code, latest_end_date, trend_score, trend_label,
           increase_quarters, decrease_quarters, consecutive_increase,
           latest_change_pct, fund_count, total_mkv)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          latest_end_date=VALUES(latest_end_date),
          trend_score=VALUES(trend_score),
          trend_label=VALUES(trend_label),
          increase_quarters=VALUES(increase_quarters),
          decrease_quarters=VALUES(decrease_quarters),
          consecutive_increase=VALUES(consecutive_increase),
          latest_change_pct=VALUES(latest_change_pct),
          fund_count=VALUES(fund_count),
          total_mkv=VALUES(total_mkv)
    """, batch)
    conn.commit()
    print(f"  total: {len(batch)} rows")


def main():
    t0 = time.time()
    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    try:
        cur = conn.cursor()
        create_tables(cur)
        conn.commit()
        print("tables created.")

        compute_stock_change(conn)
        compute_sector_flow(conn)
        compute_stock_trend(conn)
    finally:
        conn.close()
    print(f"\ndone in {time.time()-t0:.1f}s")


if __name__ == '__main__':
    main()
