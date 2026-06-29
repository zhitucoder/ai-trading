# AGENTS.md

## Environment

- Python: conda env `py312` (`/home/rick/miniconda3/envs/py312`)
- Backend deps: `fastapi`, `uvicorn`, `pymysql` (no requirements.txt — install manually if missing)
- Frontend deps: `npm install` in `src/frontend/`

## Commands

```bash
# Backend (port 9000)
cd src/backend && python main.py

# Frontend dev server
cd src/frontend && npm run dev
```

No lint, typecheck, test, or CI configured.

## Architecture

- **Backend** (`src/backend/`): FastAPI app, single endpoint `GET /api/screen`. Raw PyMySQL, no ORM. Reads from MySQL database `ai_trading` (tables: `stocks`, `daily_kline`, `fin_ratios`).
- **Frontend** (`src/frontend/`): Vue 3 SPA, single `App.vue`. No router. Hardcoded API base `http://127.0.0.1:9000` in `App.vue:80`.
- **Course materials** (`lession/`): Markdown lessons and reference docs. Not code.

## DB Config

Env vars: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`. Defaults: `127.0.0.1:3306`, `root`/`aitrading123`, database `ai_trading`.

## Conventions

- Backend runs from `src/backend/` (imports are relative, not package-level)
- Frontend uses `<script setup>` syntax, Options API not used
- All UI text is Chinese
