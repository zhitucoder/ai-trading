from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from database import get_db

app = FastAPI(title='ai-trading 选股系统')

import uvicorn

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


class StockResult(BaseModel):
    stock_code: str
    stock_name: str
    price: float
    ma5: float
    ma10: float
    ma20: float
    ma60: float
    ma120: float
    revenue_growth: float
    net_profit_growth: float
    debt_ratio: float


class ScreenResponse(BaseModel):
    total: int
    stocks: list[StockResult]


@app.get('/api/screen', response_model=ScreenResponse)
def screen(
    ma_bullish: bool = Query(True, description='均线多头排列 MA5>MA10>MA20>MA60>MA120'),
    min_revenue_growth: Optional[float] = Query(20, description='营收增长率下限(%)'),
    min_net_profit_growth: Optional[float] = Query(None, description='净利润增长率下限(%)'),
    max_debt_ratio: Optional[float] = Query(50, description='资产负债率上限(%)'),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    with get_db() as conn:
        cur = conn.cursor()

        fin_where = ["r.revenue_growth_rate > %s"]
        fin_params = [min_revenue_growth / 100]
        if min_net_profit_growth is not None:
            fin_where.append("r.net_profit_growth_rate > %s")
            fin_params.append(min_net_profit_growth / 100)
        if max_debt_ratio is not None:
            fin_where.append("r.debt_ratio < %s")
            fin_params.append(max_debt_ratio)

        cur.execute(f"""
            SELECT r.stock_code,
                   r.revenue_growth_rate,
                   r.net_profit_growth_rate,
                   r.debt_ratio
            FROM fin_ratios r
            INNER JOIN (
                SELECT stock_code, MAX(report_date) AS max_date
                FROM fin_ratios GROUP BY stock_code
            ) latest ON r.stock_code = latest.stock_code
                    AND r.report_date = latest.max_date
            WHERE {' AND '.join(fin_where)}
        """, fin_params)
        fin_rows = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}

        if not fin_rows:
            return ScreenResponse(total=0, stocks=[])

        cur.execute("SELECT stock_code, stock_name FROM stocks")
        names = dict(cur.fetchall())

        stock_codes = list(fin_rows.keys())

        results = []
        for code in stock_codes:
            rg, npg, dr = fin_rows[code]
            if dr is None or dr < 0 or dr > 200:
                continue
            cur.execute("""
                SELECT close_price FROM daily_kline
                WHERE stock_code = %s
                ORDER BY trade_date DESC
                LIMIT 120
            """, (code,))
            closes = [r[0] for r in cur.fetchall()]
            closes.reverse()
            if len(closes) < 120:
                continue

            def ma(n):
                return round(sum(closes[-n:]) / n, 2)

            m5, m10, m20, m60, m120 = ma(5), ma(10), ma(20), ma(60), ma(120)

            if ma_bullish and not (m5 > m10 > m20 > m60 > m120):
                continue

            results.append(StockResult(
                stock_code=code,
                stock_name=names.get(code, ''),
                price=closes[-1],
                ma5=m5, ma10=m10, ma20=m20,
                ma60=m60, ma120=m120,
                revenue_growth=round(rg * 100, 2) if rg else 0,
                net_profit_growth=round(npg * 100, 2) if npg else 0,
                debt_ratio=round(dr, 2) if dr else 0,
            ))

        total = len(results)
        return ScreenResponse(
            total=total,
            stocks=results[offset:offset + limit],
        )

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=9000)
