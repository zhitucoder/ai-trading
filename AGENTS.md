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
| `fund_basic` | 17k | 公募基金列表 |
| `fund_portfolio` | 15M | 公募基金持仓（季报，Tushare） |

### 分析预计算表（ads_*，必用）

**行业/个股分析（六维/俯瞰）一律从 `ads_*` 表取数**，不要每次现算派生指标。统一脚本 `src/compute_ads.py` 生成，数据管理页「分析预计算」卡片一键更新（`POST /api/data/update-ads`，后台运行，进度见 `/api/data/ads/status`）。

| 表 | Rows | 内容 |
|---|---|---|
| `ads_stock_annual` | 84k | 每股票×每年度财务（营收/成本/毛利/核心利润/净利/资产/负债/净现金/OCF/ROE/同比） |
| `ads_stock_latest` | 5.5k | 每股票最新快照（市值/PE_TTM/股息率/最新营收净利同比/最新年报指标） |
| `ads_sector_annual` | 14k | 每板块×每年度汇总（总营收/总净利/平均毛利/平均ROE/负债率/同比） |
| `ads_sector_latest` | 559 | 每板块最新快照（总市值/最新汇总/同比） |

**基金持仓分析预计算表**（`src/compute_fund_ads.py` 生成，仅用 Q2/Q4 完整数据）：

| 表 | Rows | 内容 |
|---|---|---|
| `ads_fund_stock_change` | 49k | 每股票×每双季度环比（基金数/持仓股数/市值变化/主动被动比） |
| `ads_fund_sector_flow` | 4k | 每板块×每双季度资金流向（净流入/变化率/A-D信号） |
| `ads_fund_stock_trend` | 6k | 每股票趋势评分（-4~+4，增持季度数，连续增持） |

**ads_* 关键口径**：
- `core_profit`（核心利润）= 营收 − 成本 − 销售费用 − 管理费用；`core_margin` = 核心利润/营收
- `net_cash`（净现金）= 现金 + 交易性金融资产 − 短期借款 − 长期借款
- `net_cash_ratio`（净现比）= 经营现金流 / 归母净利
- 市值/PE：`总股本` 取 `stock_shares_dfcf.total_shares`（同"总股本数据"规则）
- `pe_ttm` = 市值 / TTM归母净利（最新报告期累计 + 上年年报 − 上年同期累计）
- 数据损坏行已排除/截断（负费用行、极端比值 ±99999 截断），可直接使用

**重要**：`fin_*` 原始表有损坏字段，派生指标一律以 `ads_*` 为准；若某字段在 `ads_*` 中缺失（如金融股），再回查 `fin_*` 可信字段。

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

### 总股本数据（必守）

**总股本数据一律以 `stock_shares_dfcf` 表为准**（数据来源：东方财富F10接口，`source='dfcf'`）。

- **禁止**使用 `fin_balance_sheet.share_capital` 字段计算股本/市值——pytdx 该字段对部分公司（尤其 A+H 股）不可靠（例：中国海油 600938 该字段为 751.8 亿股，实际总股本 475.3 亿股）
- **禁止**使用旧 `stock_shares` 表（sina/em/manual 源）计算股本——旧表存在缺失（1080 只）与错误（如 600938=500亿股错误值）
- 计算市值/PE/PB 时：`总股本` 取 `stock_shares_dfcf.total_shares`，`流通股本` 取 `float_shares`
- 若需核实股本：用 `basic_eps` 交叉验证（归母净利 ÷ EPS = 总股本），或查询东方财富 F10 股本结构
- 下载/更新脚本：`src/import_shares_dfcf.py`（可断点续传：`python import_shares_dfcf.py 起始序号 结束序号`）

**股本字段口径**：`total_shares`=总股本、`float_shares`=无限售流通、`float_a_shares`=流通A股、`float_h_shares`=流通H股、`limited_shares`=限售股

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
4. **输出**：写入 `analysis/20260729/{公司名}/` 目录

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

## 公募基金持仓数据更新

fund_portfolio 数据按季度更新，Q1/Q3 仅前10大重仓，**Q2/Q4 为完整持仓**。

### 数据完整性检查

```sql
SELECT end_date, COUNT(*) as rows, COUNT(DISTINCT ts_code) as funds,
       ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT ts_code), 1) as avg_holdings
FROM fund_portfolio
WHERE end_date LIKE '%0630' OR end_date LIKE '%1231'
GROUP BY end_date ORDER BY end_date;
-- Q2/Q4 完整数据：avg_holdings ≈ 95-100
-- Q1/Q3 仅前10：avg_holdings ≈ 10-12
```

### 更新流程（当新季度数据不完整时）

```bash
# 1. 删除不完整季度数据
python -c "
import pymysql
conn = pymysql.connect(host='127.0.0.1', port=3306, user='root', password='aitrading123', database='ai_trading')
cur = conn.cursor()
cur.execute(\"DELETE FROM fund_portfolio WHERE end_date = '20260630'\")  # 改成目标季度
print(f'deleted: {cur.rowcount} rows')
conn.commit()
conn.close()
"

# 2. 从 Tushare 重新拉取
python src/import_fund_tushare.py --start 20260630  # 改成目标季度

# 3. 重建 ads_stock_fund（基金持仓聚合表）
python src/compute_ads.py

# 4. 重建基金分析预计算表
python src/compute_fund_ads.py
```

---

## 公众号发布
- **文章格式规范（必读）**：`docs/article-format.md` — 写作规范、排版要求、表格截图风格、封面规范等全部在此
- **排版命令**：`cd analysis/ && node /home/rick/.claude/skills/wechat-article-typeset/wechat-copy.js "文件名.md" --preset "墨色书香"`
- **配图规则**：所有图片用 base64 data URI 直接嵌入，**不准用 ImgBB 图床**
- **表格处理**：所有表格和结构化代码块都要转为截图（暗调风格），不得保留文本表格
- **封面图**：暗黑调 #1a1a2e，文字居中，保存到 `analysis/images/`
- **文件命名**：从分析文件生成公众号版时，新建 `{公司名}_{专家}财务分析_公众号.md`，**不改动原分析文件**
- 详细发布工作流参见 `docs/wechat-publish.md`
