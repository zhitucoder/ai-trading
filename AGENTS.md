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
  import_sectors.py  ← Tongdaxin sector/板块 import → sectors, stock_sectors tables
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
| `sectors` | 605 | Sector definitions (行业/地区/概念/风格) |
| `stock_sectors` | 82k | Stock → sector mapping |

### Table reliability

pytdx 部分字段索引偏移。详细可靠性评估见 `docs/股票画像与筛选系统_当前架构设计.md`。

**可信字段**：`fin_income`（74-97）、`fin_balance_sheet`（8-73）、`fin_cash_flow`（98-118）、`fin_quarterly`（230-236）

**损坏字段**：`fin_ratios` 索引 ≥ 166 的字段、`fin_extended`（220-337）

**指标计算（绕过损坏字段）：**
- `revenue_growth_rate` = `fin_income` 自连接算同比
- `net_profit_growth_rate` = 同上
- `debt_ratio` = `fin_balance_sheet.总负债 / 总资产 × 100`
- `roe` = `fin_income.净利润 / fin_balance_sheet.净资产 × 100`
- `gross_margin` = `(营收 − 营业成本) / 营收 × 100`

### 金融股 pytdx 财务数据问题

金融企业（证券/银行/保险）的财务报表格式不同，pytdx 固定列索引映射到错误数据项。详见 `docs/股票画像与筛选系统_当前架构设计.md`。

---

## 独立页面报告 API

两个可直接在浏览器打开的 HTML 页面接口，提供股票财务趋势图和六维分析标签页。手机友好。

### 趋势图页面

```
GET /api/report/trend/{stock_code}
```

返回完整的 HTML 页面，包含：
- 营收柱状图（蓝色）
- 净利润折线图（金色）
- 净利增长率虚线（红色）
- 周K线图（绿/红色蜡烛图）
- 图例标注

**示例**：`http://localhost:9000/api/report/trend/600519` → 贵州茅台财务趋势

### 六维分析页面

```
GET /api/report/zxm/{stock_code}
```

**示例**：`http://localhost:9000/api/report/zxm/688578` → 艾力斯六维分析

---

## Screening Strategy Details

详见 `src/app/strategies/` 下各文件：
- `technical.py` — MA多头排列（窗口函数计算）
- `fundamental.py` — 营收/净利/负债率筛选（`fin_income` 自连接算同比）
- `minervini.py` — SEPA趋势模板
- `turnaround.py` — 困境反转
- `volume_surge.py` — 倍量柱

### Combined (`ma_bullish_and_revenue_growth`)
- Performance optimization: **filter by fundamental first** (reduces stock set), then calculate MA only for candidates
- Process in batches of 500 to avoid MySQL IN clause length limits

---

## Git Workflow

- Default branch: `dev` (not `master`)
- Commit → `git push origin dev` when ready
- All development happens on `dev`; `master` is for releases only

---

## 张新民财务分析流程

当用户说 **"张新民分析 xx公司"** 时，按以下规则执行：

### 流程
1. **查数据**：从数据库提取 `fin_income`、`fin_balance_sheet`、`fin_cash_flow`、`fin_quarterly`
2. **搜预告**：网上查2026年中报业绩预告（7月中下旬密集发布），有则补充
3. **写分析**：按六维框架（资产质量/利润质量/现金流/偿债能力/成长性/风险）输出
4. **输出**：写入 `analysis/202607/{公司名}/` 目录

### 参考文档
- **写作规范/排版/封面/表格截图**：`docs/article-format.md`（必读）
- **标签体系/计算公式**：`docs/股票画像标签体系_需求文档.md`
- **现有画像系统架构**：`docs/股票画像与筛选系统_当前架构设计.md`
- **数据库字段可靠性**：见下方 Database → Table reliability

---

## Common Pitfalls

1. **Server dies after shell timeout** → always use `setsid` + redirect
2. **revenue_growth_rate is fraction** → divide user-facing threshold by 100
3. **Screening API returns `stock_code`/`stock_name` in rows but NOT in columns** → frontend renders them as static columns; dynamic columns from API are everything else
4. **No tests, no linting, no typechecking configured** — run nothing beyond `uvicorn` for dev

---

## 公众号发布
- **文章格式规范（必读）**：`docs/article-format.md` — 写作规范、排版要求、表格截图风格、封面规范等全部在此
- **排版命令**：`cd analysis/ && node /home/rick/.claude/skills/wechat-article-typeset/wechat-copy.js "文件名.md" --preset "墨色书香"`
- **配图规则**：所有图片用 base64 data URI 直接嵌入，**不准用 ImgBB 图床**
- **表格处理**：所有表格和结构化代码块都要转为截图（暗调风格），不得保留文本表格
- **封面图**：暗黑调 #1a1a2e，文字居中，保存到 `analysis/images/`
- **文件命名**：从分析文件生成公众号版时，新建 `{公司名}_{专家}财务分析_公众号.md`，**不改动原分析文件**
- 详细发布工作流参见 `docs/wechat-publish.md`
