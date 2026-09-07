#!/home/rick/miniconda3/envs/aitrading/bin/python
"""计算 A 股日K线前复权（qfq）数据，写入 daily_kline_qfq 表。

原理：以「最新交易日为基准（因子=1）」，把历史价格按除权除息事件逐级向前折算，
使股价序列连续可比较（用于长周期涨幅/回撤/技术指标计算，避免分红送转造成的跳空失真）。

除权因子：
    每股现金红利  d = cash_per_10 / 10
    送股比例      s = send_ratio / 10
    转增比例      t = trans_ratio / 10
    登记日前收盘  P0 = 除权日前一交易日不复权收盘价
    除权参考价    P1 = (P0 - d) / (1 + s + t)
    本次因子      k = P1 / P0
前复权价 = 不复权价 × Π(该日之后所有事件的 k)

运行: python src/compute_kline_qfq.py
增量: 每次全量重建（价格每日变化，因子随分红事件更新，全量最简单且始终正确）
"""
import time
import bisect
from datetime import date
import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')


def create_tables(cur):
    cur.execute("DROP TABLE IF EXISTS daily_kline_qfq")
    cur.execute("""
        CREATE TABLE daily_kline_qfq (
          id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增ID',
          stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
          trade_date DATE NOT NULL COMMENT '交易日期',
          open_price DECIMAL(10,2) NOT NULL COMMENT '前复权开盘价',
          high_price DECIMAL(10,2) NOT NULL COMMENT '前复权最高价',
          low_price DECIMAL(10,2) NOT NULL COMMENT '前复权最低价',
          close_price DECIMAL(10,2) NOT NULL COMMENT '前复权收盘价',
          volume BIGINT NOT NULL COMMENT '成交量(股)',
          amount DECIMAL(16,2) NOT NULL COMMENT '成交额(元)',
          qfq_factor DECIMAL(12,6) NOT NULL COMMENT '前复权因子(前复权价=不复权价×因子)',
          UNIQUE KEY uk_stock_date (stock_code, trade_date),
          KEY idx_date (trade_date),
          KEY idx_code (stock_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
          COMMENT='A股日K线前复权数据（以最新交易日为基准）'
    """)


def load_events(cur):
    """从 stock_dividend 加载除权除息事件（现金/送/转至少一项有效）"""
    cur.execute("""
        SELECT stock_code, ex_dividend_date, cash_per_10, send_ratio, trans_ratio
        FROM stock_dividend
        WHERE ex_dividend_date IS NOT NULL
          AND (cash_per_10 IS NOT NULL OR send_ratio IS NOT NULL OR trans_ratio IS NOT NULL)
        ORDER BY stock_code, ex_dividend_date
    """)
    events = {}
    for r in cur.fetchall():
        d = float(r['cash_per_10'] or 0) / 10
        s = float(r['send_ratio'] or 0) / 10
        t = float(r['trans_ratio'] or 0) / 10
        if d + s + t <= 0:
            continue
        events.setdefault(r['stock_code'], []).append(
            (r['ex_dividend_date'], d, s, t))
    return events


def compute_stock(code, rows, events):
    """对单只股票计算前复权。

    rows: [(trade_date, open, high, low, close, volume, amount), ...] 升序
    events: [(ex_dividend_date, d, s, t), ...] 升序
    返回: [(stock_code, trade_date, o, h, l, c, volume, amount, factor), ...] 升序
    """
    dates = [r[0] for r in rows]
    resolved = []
    for ex_date, d, s, t in events:
        # 除权日前一交易日（严格 < ex_date 的最后一天）
        idx = bisect.bisect_left(dates, ex_date) - 1
        if idx < 0:
            continue
        p0 = rows[idx][4]
        if not p0 or p0 <= 0:
            continue
        k = ((p0 - d) / (1 + s + t)) / p0
        if k > 0:
            resolved.append((ex_date, k))
    resolved.sort(reverse=True)  # 除权日从新到旧

    cum = 1.0
    ei = 0
    out = []
    for r in reversed(rows):
        td = r[0]
        while ei < len(resolved) and td < resolved[ei][0]:
            cum *= resolved[ei][1]
            ei += 1
        out.append((code, td,
                    round(r[1] * cum, 2), round(r[2] * cum, 2),
                    round(r[3] * cum, 2), round(r[4] * cum, 2),
                    r[5], r[6], round(cum, 6)))
    out.reverse()
    return out


def compute_qfq(progress_cb=None):
    """全量重算前复权K线。progress_cb: 可选回调(msg)"""
    def log(msg):
        if progress_cb:
            progress_cb(msg)

    t0 = time.time()
    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    cur = conn.cursor()

    log('创建 daily_kline_qfq 表...')
    create_tables(cur)
    conn.commit()

    log('加载除权除息事件...')
    events = load_events(cur)
    event_stocks = set(events.keys())
    log(f'有分红送转事件的股票: {len(event_stocks)} 只')

    cur.execute("SELECT DISTINCT stock_code FROM daily_kline ORDER BY stock_code")
    codes = [r['stock_code'] for r in cur.fetchall()]
    total_stocks = len(codes)
    log(f'待处理股票: {total_stocks} 只')

    insert_sql = """INSERT INTO daily_kline_qfq
                    (stock_code, trade_date, open_price, high_price, low_price, close_price, volume, amount, qfq_factor)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""

    total_rows = 0
    stocks_done = 0
    batch = []
    for code in codes:
        cur.execute("""
            SELECT trade_date, open_price, high_price, low_price, close_price, volume, amount
            FROM daily_kline WHERE stock_code = %s ORDER BY trade_date
        """, (code,))
        raw = cur.fetchall()
        if not raw:
            continue
        rows = [(r['trade_date'], float(r['open_price']), float(r['high_price']),
                 float(r['low_price']), float(r['close_price']),
                 int(r['volume']), float(r['amount'])) for r in raw]
        ev = events.get(code, [])
        for rec in compute_stock(code, rows, ev):
            batch.append(rec)
        stocks_done += 1

        if len(batch) >= 5000:
            cur.executemany(insert_sql, batch)
            conn.commit()
            total_rows += len(batch)
            batch = []

        if stocks_done % 500 == 0:
            log(f'进度: {stocks_done}/{total_stocks} 只, 已写入 {total_rows + len(batch)} 条')

    if batch:
        cur.executemany(insert_sql, batch)
        conn.commit()
        total_rows += len(batch)

    elapsed = int(time.time() - t0)
    log(f'完成: {total_rows} 条 / {stocks_done} 只, 耗时 {elapsed}s')
    cur.close()
    conn.close()

    return {
        'rows': total_rows,
        'stocks': stocks_done,
        'event_stocks': len(event_stocks),
        'elapsed_seconds': elapsed,
    }


def main():
    print(compute_qfq(progress_cb=print))


if __name__ == '__main__':
    main()
