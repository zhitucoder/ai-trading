# AGENTS.md

## Project: AI Trading System

Stock analysis system: screening, backtesting, stock profiling, AI bull/bear debate.

---

## Repo Structure

```
src/
  app/               ← FastAPI application
    main.py          ← Entrypoint: FastAPI app + SPA catch-all
    database.py      ← MySQL connection (pymysql, DictCursor)
    routers/
      screening.py   ← /api/screening/* endpoints
    strategies/
      technical.py   ← MA bull arrangement screening
      fundamental.py ← Financial ratio screening
  import_kline.py    ← Tongdaxin daily K-line import → daily_kline table
  import_financial.py ← Tongdaxin financial data import → 8 fin_* tables
web/
  index.html         ← Vue 3 SPA (CDN, no build tool)
  app.js             ← Vue components
  style.css          ← Dark tech theme
lession/             ← Course materials (not code)
```

---

## Quick Start

### Launch server
```bash
cd /home/rick/workspace/ai-trading
setsid /home/rick/miniconda3/envs/aitrading/bin/uvicorn src.app.main:app \
  --host 0.0.0.0 --port 9000 < /dev/null > /tmp/uvicorn.log 2>&1 &
```
**Must use `setsid` + `disown`/redirect** — plain `&` gets killed when the shell session times out.

### Conda env
- Path: `/home/rick/miniconda3/envs/aitrading`
- Python 3.12, packages: fastapi, uvicorn, pymysql, pytdx

---

## Architecture Rules

### SPA serving
- `main.py` declares all `/api/*` routes first, then a catch-all `/{path:path}` serves `web/index.html`.
- **API routes MUST come before the catch-all**, otherwise the catch-all hijacks API requests.

### Adding a new screening strategy
1. Create strategy function in `strategies/` — must accept params and return list of dicts
2. Register in `routers/screening.py`:
   - Add entry to `list_strategies()` response
   - Add `if strategy_id == 'foo'` branch in `execute_screening()`
3. Frontend: add a card in `index.html` template under the matching tab

---

## Database (MySQL)

- Host: `127.0.0.1:3306`, database: `ai_trading`, user: `root`, password: `aitrading123`
- Connection config in `src/app/database.py`

### Key tables

| Table | Rows | Purpose |
|---|---|---|
| `stocks` | 5.5k | Stock code → name mapping |
| `daily_kline` | 10M | Daily OHLCV (2021-01 to 2026-06) |
| `fin_ratios` | 290k | Financial ratios per report quarter |
| `fin_income` | 290k | Income statement per quarter |
| 6 more `fin_*` | 290k each | Balance sheet, cash flow, etc. |

### Table reliability (pytdx field index shifts)

pytdx 财务数据的字段索引发生过偏移。索引 ≤ 97 的字段（利润表、资产负债表）正确；
索引 ≥ 166 的比率类字段大面积损坏。以下是各表的详细可靠性评估。

#### Table-level summary

| Table | Field indices | Reliability | Why |
|---|---|---|---|
| `stocks` | — | ✅ **Trustworthy** | Manually maintained code→name |
| `daily_kline` | — | ✅ **Trustworthy** | Direct import from .day binary |
| `fin_balance_sheet` | 8–73 | ✅ **Trustworthy** | Balance equation holds (TA−TL−TE=0) |
| `fin_income` | 74–97 | ✅ **Trustworthy** | 收入/成本/利润合理，税率匹配 |
| `fin_cash_flow` | 98–118 | ✅ **Trustworthy** | 相邻索引范围，与 income/BS 一致 |
| `fin_quarterly` | 230–236 | ✅ **Trustworthy** | 单季数据与 fin_income 吻合 |
| `fin_ratios` | 1–6 (roe, eps, bps) | ✅ **Trustworthy** | 低索引字段，与原始数据计算一致 |
| `fin_ratios` | 166–194 | ❌ **UNRELIABLE** | 字段索引偏移，数据来自错误列 |
| `fin_ratios` | 220–229 (ebit, ebitda, CAGR) | ⚠️ **Partially broken** | `revenue_cagr_3y` 永远为 NULL（FIELD_MAP 命名不匹配），`net_profit_cagr_3y` 有值但未知可靠性 |
| `fin_ratios` | 282–283 (pe_ttm, market_cap) | ❌ **Always NULL** | 已知 pytdx 索引不匹配 |
| `fin_extended` | 220–337 | ❌ **UNRELIABLE** | `rd_expense` 全为 NULL, `rev_ttm` 字段错位，`fcf` 全为 NULL |

#### Verified trustworthy fields

直接从原始表计算，不使用 `fin_ratios`：

| 指标 | 正确计算方式 |
|---|---|
| `revenue_growth_rate` | `fin_income` 自连接：`(current_rev − prev_year_rev) / prev_year_rev * 100` |
| `net_profit_growth_rate` | `fin_income` 自连接：`(current_profit − prev_year_profit) / prev_year_profit * 100` |
| `debt_ratio` | `fin_balance_sheet`：`total_liabilities / total_assets * 100` |
| `current_ratio` | `fin_balance_sheet`：`current_assets / current_liabilities` |
| `roe` | `fin_income.net_profit / fin_balance_sheet.total_equity * 100` |
| `gross_margin` | `(operating_revenue − operating_cost) / operating_revenue * 100` from fin_income |
| `net_margin` | `fin_income.net_profit / fin_income.operating_revenue * 100` |

#### Code references

- **Profile module** (`strategies/profile.py`): ✅ 全部指标从原始表计算，不使用 `fin_ratios`
- **Screening module** (`strategies/fundamental.py`, `routers/screening.py`): ✅ 已修复，从 `fin_income` / `fin_balance_sheet` 计算
- **Pre-2026-07 screening code**: ❌ 使用损坏的 `fin_ratios` 字段，需手动迁移

### Indexes
- `daily_kline`: `(stock_code, trade_date, close_price)` — covering index for MA calculations
- `daily_kline`: `(trade_date)`, `(stock_code)` — standalone

---

## Screening Strategy Details

### MA Bullish (`ma_bullish`)
- Uses MySQL window functions (`AVG() OVER ... ROWS BETWEEN N PRECEDING AND CURRENT ROW`)
- Default periods: `5,10,20,60` (configurable, comma-separated)
- Condition: MA5 > MA10 > MA20 > MA60 (configurable list, sorted asc)
- Date window: 70 days before latest trade date

### Fundamental All (`fundamental_all`)
- All 3 conditions simultaneously: revenue_growth > threshold, net_profit_growth > threshold, debt_ratio < threshold
- Joins `fin_ratios` + `fin_income` for operating_revenue/net_profit
- Always filters `debt_ratio >= 0` to exclude junk data

## Backtest API (`src/app/routers/backtest.py`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/kline/{stock_code}?days=N` | GET | OHLCV data for charting |
| `/api/kline_range/{stock_code}?start_date=&end_date=` | GET | K-line in date range |
| `/api/backtest/position` | POST | User-defined trades → P&L |
| `/api/backtest/ma` | POST | MA crossover backtest |

### Position backtest
- Body: `{"stock_code":"600519","trades":[{"date":"...","direction":"buy","shares":100,"price":1500}]}`
- Trade dates auto-mapped to nearest trading day
- Average cost basis P&L calculation
- Returns: daily_pnl[] + summary (total_invested, return, max_drawdown)

### MA crossover backtest
- Query params: `stock_code, start_date, end_date, short_ma, long_ma, total_capital`
- Golden cross (short MA ↑ above long MA) → Buy; Death cross → Sell
- Buy: max affordable 100-share lots from available cash; skip if < 1 hand
- Sell: liquidate entire position
- Uses lightweight-charts CDN for frontend K-line rendering

---

### Combined (`ma_bullish_and_revenue_growth`)
- Performance optimization: **filter by fundamental first** (reduces stock set), then calculate MA only for candidates
- Process in batches of 500 to avoid MySQL IN clause length limits

---

## Git Workflow

- Default branch: `dev` (not `master`)
- Commit → `git push origin dev` when ready
- All development happens on `dev`; `master` is for releases only

---

## Common Pitfalls

1. **Server dies after shell timeout** → always use `setsid` + redirect
2. **revenue_growth_rate is fraction** → divide user-facing threshold by 100
3. **Screening API returns `stock_code`/`stock_name` in rows but NOT in columns** → frontend renders them as static columns; dynamic columns from API are everything else
4. **No tests, no linting, no typechecking configured** — run nothing beyond `uvicorn` for dev
