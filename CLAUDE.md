# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Launch server (MUST use setsid — plain & dies on shell timeout)
setsid /home/rick/miniconda3/envs/aitrading/bin/uvicorn src.app.main:app \
  --host 0.0.0.0 --port 9000 < /dev/null > /tmp/uvicorn.log 2>&1 &

# Batch profile all stocks
python batch_profile.py

# Import data (one-time or catch-up)
python src/import_kline.py        # Tongdaxin .day files → daily_kline
python src/import_financial.py    # Tongdaxin GPCW .dat files → fin_* tables
```

Conda env: `/home/rick/miniconda3/envs/aitrading` (Python 3.12, fastapi, uvicorn, pymysql, pytdx)

No tests, no linter, no type checker configured.

## Architecture

### Application structure

```
src/
  app/                        ← FastAPI backend
    main.py                   ← App entrypoint: creates FastAPI, registers routers, serves SPA
    database.py               ← MySQL connection (pymysql DictCursor, blocking queries)
    init_profiles.py          ← DDL for stock_profiles and profile_refresh_log tables
    profile_batch.py          ← Full-market batch stock profiling (500-at-a-time writes)
    routers/
      screening.py            ← /api/screening/* — strategy listing + execution
      backtest.py             ← /api/kline/*, /api/backtest/*
      profile.py              ← /api/profile/*, /api/profiles/* — single stock + search + batch refresh
      debate.py               ← /api/debate/* — 5-round AI bull/bear debate
      vcp.py                  ← /api/vcp/* — Volatility Contraction Pattern scan
      expert.py               ← /api/expert/* — "Distilled Expert" LLM chat
      data_management.py      ← /api/data/* — K-line + financial data sync from Tongdaxin
    strategies/
      technical.py            ← MA bull arrangement screening
      fundamental.py          ← Financial ratio screening (revenue, profit, debt)
      minervini.py            ← Mark Minervini SEPA screening (EPS, ROE, trend template)
      profile.py              ← Core stock profiling engine (tags, stages S1-S4, scoring)
  import_kline.py             ← Standalone: import daily K-line from .day binary files
  import_financial.py         ← Standalone: import financial data from GPCW .dat files
web/
  index.html                  ← Vue 3 SPA (CDN, no build tool) — all 8 page templates
  app.js                      ← Vue 3 components + routing (single file, ~990 lines)
  style.css                   ← Dark tech theme (~1320 lines)
batch_profile.py              ← CLI entry point for batch stock profiling
lession/                      ← Course materials (12 lessons in Chinese, not application code)
```

### SPA serving pattern

`main.py` registers all `/api/*` routers first, then a catch-all `/{path:path}` route that serves `web/index.html` for any non-file path. **API routes MUST be declared before the catch-all** — ordering is critical.

### Backend patterns

- **All route handlers are synchronous** — pymysql is blocking, no async/await used.
- **No ORM** — all DB access uses raw SQL via `src/app/database.py` helpers: `query(sql, params)` → list of dicts, `query_one(sql, params)` → single dict, `execute(sql, params)` → rowcount.
- **New strategy pattern**: add strategy function in `strategies/`, register in `routers/screening.py` (add to `list_strategies()` response + `if strategy_id == 'foo'` branch in `execute_screening()`), add frontend card in `index.html`.
- **Background tasks** use Python `threading.Thread` (see `profile.py` batch refresh).

### Database (MySQL `ai_trading` at 127.0.0.1:3306)

| Table | Rows | Notes |
|---|---|---|
| `stocks` | 5.5k | Stock code → name mapping |
| `daily_kline` | 10M | Daily OHLCV (2021-01 to 2026-06), indexed on `(stock_code, trade_date, close_price)` |
| `fin_income` / `fin_balance_sheet` / `fin_cash_flow` | 290k each | Raw financial data — trustworthy |
| `fin_ratios` | 290k | Index ≥ 166 fields UNRELIABLE due to pytdx field shifts |
| `fin_quarterly` / `fin_shareholder` / `fin_institution` / `fin_extended` | 290k each | Extended data — partially unreliable |
| `stock_profiles` | 5.5k | Precomputed profiles with JSON, tags, stages, scores |

**Critical**: Never use `fin_ratios` for derived metrics. Compute from raw tables:
- `revenue_growth_rate` = `fin_income` self-join on year-over-year
- `debt_ratio` = `fin_balance_sheet.total_liabilities / total_assets * 100`
- `roe` = `fin_income.net_profit / fin_balance_sheet.total_equity * 100`
- `gross_margin` = `(operating_revenue - operating_cost) / operating_revenue * 100`

These patterns are already implemented in `strategies/profile.py` and `strategies/fundamental.py`.

### Frontend

- **Vue 3 via CDN** (unpkg), no build step — `vue.global.prod.js` loaded in `<head>`.
- **Single HTML file** with all 8 page templates as `<template id="...">` elements.
- **Components registered via `app.component('name', {...})`** in `app.js`, switched by `currentPage` ref using `v-if/v-else-if` chains.
- **Charts**: TradingView's lightweight-charts CDN for K-line rendering.
- **API calls**: raw `fetch()` with no wrapper — every component handles its own loading/error state.

### Key conventions

- **Stock codes**: passed as strings, may include exchange prefix (e.g. `SH600519` or `600519`). Handle both.
- **Date format**: `YYYY-MM-DD` throughout the stack.
- **Git workflow**: default branch is `dev` (not `master`). `master` is release-only.
- **Server lifecycle**: always use `setsid` + stdin/stdout redirect to prevent SIGTERM on shell timeout.
