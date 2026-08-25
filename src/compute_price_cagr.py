#!/home/rick/miniconda3/envs/aitrading/bin/python3
"""计算股票画像的股价3年CAGR与业绩股价背离，写入 stock_profiles。

口径（与低估成长策略一致）：
- price_cagr_3y = (最新收盘价 / 3年前收盘价)^(1/3) - 1，价格为前复权(daily_kline_qfq)
- divergence = profit_cagr_3y(净利3年CAGR, stock_profiles已有) - price_cagr_3y
- 单位：百分数值(如 15.3 即 15.3%)

命令行运行：python3 compute_price_cagr.py
"""
import time
import pymysql

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')


def update_price_cagr(conn=None):
    """更新 stock_profiles 的 price_cagr_3y 与 divergence 字段，返回更新数。"""
    close_conn = conn is None
    if conn is None:
        conn = pymysql.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(trade_date) AS d FROM daily_kline_qfq")
        latest = cur.fetchone()[0]
        if not latest:
            return 0

        t0 = time.time()
        cur.execute("""
            SELECT stock_code, close_price FROM (
                SELECT stock_code, close_price,
                       ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
                FROM daily_kline_qfq
                WHERE trade_date <= DATE_SUB(%s, INTERVAL 3 YEAR)
            ) t WHERE t.rn = 1
        """, [str(latest)])
        price_3y = {r[0]: float(r[1]) for r in cur.fetchall()}
        print(f'[price_cagr] 3年前价格快照: {len(price_3y)} 只, 耗时 {time.time()-t0:.1f}s')

        cur.execute("SELECT MAX(data_date) AS d FROM stock_profiles")
        data_date = cur.fetchone()[0]
        if not data_date:
            return 0

        cur.execute("""
            SELECT stock_code, latest_price, profit_cagr_3y
            FROM stock_profiles WHERE data_date = %s
        """, [str(data_date)])
        profiles = cur.fetchall()

        updated = 0
        for code, latest_price, profit_cagr in profiles:
            lp = float(latest_price) if latest_price is not None else None
            p3 = price_3y.get(code)
            price_cagr = None
            if lp and p3 and lp > 0 and p3 > 0:
                price_cagr = ((lp / p3) ** (1 / 3) - 1) * 100
            divergence = None
            if price_cagr is not None and profit_cagr is not None:
                divergence = float(profit_cagr) - price_cagr
            cur.execute(
                "UPDATE stock_profiles SET price_cagr_3y = %s, divergence = %s WHERE stock_code = %s AND data_date = %s",
                [price_cagr, divergence, code, str(data_date)]
            )
            updated += 1
        conn.commit()
        print(f'[price_cagr] 已更新 {updated} 只股票')
        return updated
    finally:
        if close_conn:
            conn.close()


def main():
    update_price_cagr()


if __name__ == '__main__':
    main()