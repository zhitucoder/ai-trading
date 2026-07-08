# AI Trading System 系统架构

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                  用户层 (Browser)                        │
│            浏览器访问 http://host:9000                   │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────┐
│              前端 SPA  (Vue 3 · CDN · 无构建工具)        │
│  ┌──────────┬──────────┬──────────┬──────────┐         │
│  │  选股    │  回测     │  个股画像 │ AI 辩论  │         │
│  │ screening│ backtest │  profile │  debate  │         │
│  └──────────┴──────────┴──────────┴──────────┘         │
│  ┌──────────┬──────────┬──────────┐                     │
│  │  VCP     │ 蒸馏专家  │ 数据管理  │                     │
│  │  vcp     │  expert  │ data_mgmt│                     │
│  └──────────┴──────────┴──────────┘                     │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP REST API (JSON)
┌──────────────────────▼──────────────────────────────────┐
│             后端 API 层  (FastAPI · uvicorn)              │
│                                                         │
│  ┌──────────┬──────────┬──────────┬──────────┐         │
│  │  选股    │  回测     │  画像     │  AI 辩论  │         │
│  │ /screening│ /backtest│ /profile │ /debate  │         │
│  ├──────────┼──────────┼──────────┼──────────┤         │
│  │  VCP     │ 蒸馏专家  │ 数据管理  │ 健康检查  │         │
│  │ /vcp     │ /expert  │ /data    │ /health  │         │
│  └──────────┴──────────┴──────────┴──────────┘         │
└──────────────────────┬──────────────────────────────────┘
                       │ 查询/写入
┌──────────────────────▼──────────────────────────────────┐
│           策略与分析引擎  (Strategies)                    │
│                                                         │
│  ┌──────────────┬──────────────┬──────────────┐        │
│  │ 技术面       │ 基本面       │ 形态         │        │
│  │ technical.py│ fundamental.py│ minervini.py │        │
│  ├──────────────┼──────────────┼──────────────┤        │
│  │ 个股画像     │ 反转          │              │        │
│  │ profile.py  │ turnaround.py│              │        │
│  └──────────────┴──────────────┴──────────────┘        │
└──────────────────────┬──────────────────────────────────┘
                       │ SQL
┌──────────────────────▼──────────────────────────────────┐
│             数据存储层  (MySQL · ai_trading)              │
│                                                         │
│  ┌──────────────┬──────────────┬──────────────┐        │
│  │ stocks       │ daily_kline  │ fin_income    │        │
│  │ (5.5k 股票)  │ (10M K线)     │ (29万行)      │        │
│  ├──────────────┼──────────────┼──────────────┤        │
│  │ fin_balance  │ fin_cash_flow│ fin_ratios    │        │
│  │ (29万行)      │ (29万行)      │ (29万行)      │        │
│  ├──────────────┼──────────────┼──────────────┤        │
│  │ sectors      │ stock_sectors│ 其他 fin_*     │        │
│  │ (605 板块)   │ (8.2万映射)    │              │        │
│  └──────────────┴──────────────┴──────────────┘        │
└──────────────────────┬──────────────────────────────────┘
                       │ 导入
┌──────────────────────▼──────────────────────────────────┐
│             数据导入层  (通达信 · pytdx)                  │
│                                                         │
│  import_kline.py  → daily_kline 表                      │
│  import_financial.py → 8 张 fin_* 表                    │
│  import_sectors.py → sectors + stock_sectors             │
│  import_shares.py → shares 表                            │
└─────────────────────────────────────────────────────────┘
```

## 分层说明

### 1. 用户层
浏览器直接访问 `http://host:9000`，SPA 路由由前端处理。

### 2. 前端 SPA (`web/`)
Vue 3 SPA，所有依赖通过 CDN 加载，无需构建工具。

| 页面 | 对应功能 | 文件 |
|------|---------|------|
| 选股 | 技术面/基本面/组合选股 | `web/app.js` |
| 回测 | 持仓回测 / MA 金叉死叉 | `web/app.js` |
| 个股画像 | 全方位财务/技术分析 | `web/app.js` |
| AI 辩论 | 多空双方 AI 辩论 | `web/app.js` |
| VCP | 波动收缩模式识别 | `web/app.js` |
| 蒸馏专家 | AI 专家观点生成 | `web/app.js` |
| 数据管理 | 导入/查看数据状态 | `web/app.js` |

### 3. 后端 API (`src/app/`)
FastAPI 应用，按功能模块划分路由。

| 路由 | 功能 | 入口文件 |
|------|------|---------|
| `/api/screening/*` | 选股策略执行 | `routers/screening.py` |
| `/api/backtest/*` | 回测计算 | `routers/backtest.py` |
| `/api/profile/*` | 个股画像 | `routers/profile.py` |
| `/api/debate/*` | AI 多空辩论 | `routers/debate.py` |
| `/api/vcp/*` | VCP 形态识别 | `routers/vcp.py` |
| `/api/expert/*` | 蒸馏专家观点 | `routers/expert.py` |
| `/api/data/*` | 数据管理 | `routers/data_management.py` |
| `/api/health` | 健康检查 | `main.py` |

跨域已开放，适合本地部署和 API 调试。

### 4. 策略与分析引擎 (`src/app/strategies/`)
纯计算逻辑，不直接暴露 HTTP 接口，被 router 层调用。

| 策略模块 | 用途 |
|---------|------|
| `technical.py` | MA 多头排列选股 |
| `fundamental.py` | 财务指标选股（营收增长/利润增长/负债率） |
| `minervini.py` | Mark Minervini 选股策略（SEPA） |
| `profile.py` | 个股画像指标计算 |
| `turnaround.py` | 困境反转识别 |

### 5. 数据存储 (MySQL)
数据库 `ai_trading`，主要表结构：

| 表 | 行数 | 用途 |
|----|------|------|
| `stocks` | 5.5k | 股票代码→名称映射 |
| `daily_kline` | 10M | 日线 OHLCV（2021-2026） |
| `fin_income` | 290k | 利润表 |
| `fin_balance_sheet` | 290k | 资产负债表 |
| `fin_cash_flow` | 290k | 现金流量表 |
| `fin_ratios` | 290k | 财务比率（部分字段有偏移问题） |
| `fin_quarterly` | 290k | 单季数据 |
| `sectors` | 605 | 板块定义 |
| `stock_sectors` | 82k | 股票→板块映射 |

**注意**：`fin_ratios` 表中索引 ≥ 166 的字段因 pytdx 索引偏移已损坏，所有比率计算从原始表（`fin_income` / `fin_balance_sheet`）自行推导。

### 6. 数据导入 (`src/import_*.py`)
定时/手动运行的 Python 脚本，通过 pytdx 从通达信导入数据：

```
import_kline.py      → daily_kline (日线)
import_financial.py  → fin_* (财务)
import_sectors.py    → sectors / stock_sectors (板块)
import_shares.py     → shares (股本)
```

## 请求流程示例

以 **选股** 为例：

```
用户点击"选股" → SPA 调 /api/screening/execute?strategy=ma_bullish
  → FastAPI 路由解析参数
  → strategies/technical.py 执行计算
    → database.py query() 查 daily_kline
    → MySQL 窗口函数算 MA
  → 返回 JSON [{stock_code, stock_name, ...}]
  → SPA 渲染表格
```

## 部署方式

```bash
# 启动服务（必须 setsid，否则 shell 超时后进程被杀）
setsid /home/rick/miniconda3/envs/aitrading/bin/uvicorn src.app.main:app \
  --host 0.0.0.0 --port 9000 < /dev/null > /tmp/uvicorn.log 2>&1 &
```

## 架构原则

1. **SPA 优先**：API 路由声明在 catch-all 之前，避免 SPA 路由劫持 API 请求
2. **计算隔离**：策略模块纯计算，不直接接触 HTTP 或 DB 连接
3. **数据可靠性**：关键指标从原始表计算，不使用已损坏的 fin_ratios 字段
4. **前端轻量**：Vue 3 + CDN，零构建，开箱即用
