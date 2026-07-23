# 强势板块 · 强势个股 选股权统设计

## 一、需求分析

### 1.1 用户目标

从所有行业板块和概念板块中，先选出**相对上证指数涨幅最大**的强势板块，再从强势板块中选出**相对板块涨幅最大**的强势个股。核心链路：

```
全市场板块 → 强势板块排名 → 板块成分股排名 → 强势个股
```

### 1.2 页面规划

| 页面 | 功能 | 入口 |
|------|------|------|
| **Page A: 板块强度排名** | 所有行业+概念板块 vs 上证指数，支持排序、景气度筛选 | 侧边栏「强势板块」 |
| **Page B: 指数K线对比** | 上证指数 + 最多4个板块指数同时K线对比 | Page A 顶部或独立Tab |
| **Page C: 板块成分股** | 点击某板块 → 成分股按相对涨幅排名 + K线对比 | Page A 点击板块行 |
| **Page D: 强势个股跨板比较** | 各板块最强个股一览（涨跌幅热力/排行） | 侧边栏「强势个股」 |

### 1.3 数据需求盘点

#### 已有数据

| 数据 | 状态 | 说明 |
|------|------|------|
| `sector_kline` | ✅ 有 | 1120 个板块指数日K线，2018-至今 |
| `sectors` | ✅ 有 | 605 个板块定义（行业145 / 概念270 / 风格158 / 地区32） |
| `stock_sectors` | ✅ 有 | 股票→板块映射，82K 条 |
| `daily_kline` | ✅ 有 | 8093 只股票日K线，2018-至今 |

#### 缺失数据（需新建）

| 数据 | 说明 | 方案 |
|------|------|------|
| **上证指数 K线** | sh000001 `.day` 文件存在但未导入（被 `classify_file` 归为 skip） | 新建 `index_kline` 表，从 `sh/lday/sh000001.day` 等导入 |
| **主要宽基指数** | 沪深300 (sh000300)、中证500 (sh000905)、上证50 (sh000016) 等 | 同上，一并导入 |
| **行业景气度** | 无现成数据源 | 方案见 §2.2 |
| **sector_kline 中 515 个孤儿代码** | 无对应 sectors 记录（可能是通达信旧代码） | 导入时过滤，只保留能 join sectors 的 |

### 1.4 核心指标定义

| 指标 | 计算方式 |
|------|----------|
| **今日涨幅** | `(close_today - close_yesterday) / close_yesterday * 100` |
| **近30日涨幅** | `(close_today - close_30ago) / close_30ago * 100` |
| **今年以来涨幅 (YTD)** | `(close_today - close_lastyear_end) / close_lastyear_end * 100` |
| **相对上证涨幅** | `板块涨幅 - 上证涨幅`（超额收益） |
| **行业景气度** | 基于板块成分股财务数据的综合评分，分高/中/低三档 |

---

## 二、概要设计

### 2.1 数据层

#### 2.1.1 新建 `index_kline` 表

存储主要指数的日K线，用于与板块对比。

```sql
CREATE TABLE index_kline (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    index_code VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    open_price DECIMAL(10,2) NOT NULL,
    high_price DECIMAL(10,2) NOT NULL,
    low_price DECIMAL(10,2) NOT NULL,
    close_price DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    amount DECIMAL(16,2) NOT NULL,
    UNIQUE KEY uk_code_date (index_code, trade_date),
    KEY idx_date (trade_date)
) ENGINE=InnoDB;
```

**导入源文件：**

| 文件 | index_code | 名称 |
|------|-----------|------|
| `sh/lday/sh000001.day` | 000001 | 上证综指 |
| `sh/lday/sh000016.day` | 000016 | 上证50 |
| `sh/lday/sh000300.day` | 000300 | 沪深300 |
| `sh/lday/sh000905.day` | 000905 | 中证500 |
| `sh/lday/sh000852.day` | 000852 | 中证1000 |

> 通达信 .day 二进制格式与 daily_kline 完全一致（32字节/条），复用 `_parse_day_file` 逻辑。
> **注意**：index_code 不加 exchange 前缀（与 daily_kline/sector_kline 保持一致）。

#### 2.1.2 补充 `sectors` 表

sector_kline 中有 515 个孤儿代码无对应 sectors 记录。处理方案：

- **导入时过滤**：只将 sector_code 能 JOIN sectors 表的数据纳入分析
- **可选**：后续从通达信补充这些代码的名称

#### 2.1.3 行业景气度指标

**方案：基于板块成分股财务数据计算**

从 `fin_income`（营收增长率）+ `fin_balance_sheet`（资产负债率）+ `fin_ratios`（ROE）三个维度综合评分：

```
景气度评分 = w1 × 营收增长评分 + w2 × ROE评分 + w3 × (1 - 负债率评分)

高景气：评分 ≥ 70
中景气：40 ≤ 评分 < 70
低景气：评分 < 40
```

评分规则（每个维度0-100分）：
- **营收增长评分**：板块内成分股营收增长率中位数，映射到 0-100
- **ROE评分**：板块内成分股 ROE 中位数，映射到 0-100
- **负债率评分**：板块内成分股资产负债率中位数，映射到 0-100（负债越低分越高）

**缓存策略**：景气度每日盘后计算一次，存入 `sector_prosperity` 表或直接从 fin 表实时聚合（板块数仅 415 个，实时计算可接受）。

### 2.2 后端 API 设计

#### API-1: 板块强度排名

```
GET /api/strong/sectors
```

**Query 参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `category` | string | `industry` / `concept` / `all`（默认 `all`） |
| `sort_by` | string | `ytd` / `m30` / `today` / `relative_ytd` / `relative_m30` / `relative_today` |
| `sort_order` | string | `desc` / `asc`（默认 `desc`） |
| `prosperity` | string | `high` / `medium` / `low` / `all`（默认 `all`） |

**返回：**

```json
{
  "index": { "code": "000001", "name": "上证综指", "today": 0.52, "m30": 3.1, "ytd": 8.7 },
  "sectors": [
    {
      "sector_code": "880948",
      "sector_name": "人工智能",
      "category": "concept",
      "category_cn": "概念",
      "stock_count": 1062,
      "today": 2.31,
      "m30": 15.6,
      "ytd": 42.3,
      "relative_today": 1.79,
      "relative_m30": 12.5,
      "relative_ytd": 33.6,
      "prosperity": "high",
      "latest_close": 1234.56
    }
  ]
}
```

**SQL 核心逻辑：**

```sql
-- 获取上证指数基准
SELECT close_price FROM index_kline WHERE index_code = '000001' AND trade_date = @latest;
SELECT close_price FROM index_kline WHERE index_code = '000001' AND trade_date = @30ago;
SELECT close_price FROM index_kline WHERE index_code = '000001' AND trade_date = @yearend;

-- 板块涨幅
SELECT s.sector_code, s.sector_name, s.category, s.category_cn,
  sk_latest.close_price as latest_close,
  (sk_latest.close_price / sk_30ago.close_price - 1) * 100 AS m30,
  (sk_latest.close_price / sk_yearend.close_price - 1) * 100 AS ytd
FROM sectors s
JOIN sector_kline sk_latest ON s.sector_code = sk_latest.sector_code AND sk_latest.trade_date = @latest
LEFT JOIN sector_kline sk_30ago ON s.sector_code = sk_30ago.sector_code AND sk_30ago.trade_date = @30ago
LEFT JOIN sector_kline sk_yearend ON s.sector_code = sk_yearend.sector_code AND sk_yearend.trade_date = @yearend
WHERE s.category IN ('industry', 'concept')
  -- prosperity filter if needed
ORDER BY ytd DESC;
```

#### API-2: 指数K线数据

```
GET /api/strong/index-kline
```

**Query 参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `codes` | string | 逗号分隔的指数/板块代码，最多5个（如 `000001,880948,880301`） |
| `days` | int | 回溯天数，默认 120 |

**返回：**

```json
{
  "series": [
    {
      "code": "000001",
      "name": "上证综指",
      "type": "index",
      "data": [
        { "date": "2026-07-17", "open": 3500.1, "high": 3520.5, "low": 3495.0, "close": 3515.2, "volume": 250000000 }
      ]
    },
    {
      "code": "880948",
      "name": "人工智能",
      "type": "sector",
      "data": [...]
    }
  ]
}
```

#### API-3: 板块成分股排名

```
GET /api/strong/sector-stocks
```

**Query 参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `sector_code` | string | 板块代码（如 `880948`） |
| `sort_by` | string | `relative_ytd` / `relative_m30` / `relative_today` / `change_today` |
| `sort_order` | string | 默认 `desc` |

**返回：**

```json
{
  "sector": { "code": "880948", "name": "人工智能", "today": 2.31, "m30": 15.6, "ytd": 42.3 },
  "index_ref": { "code": "000001", "name": "上证综指", "today": 0.52, "m30": 3.1, "ytd": 8.7 },
  "stocks": [
    {
      "stock_code": "300123",
      "stock_name": "太阳能",
      "today": 5.2,
      "m30": 28.3,
      "ytd": 65.1,
      "relative_today": 4.68,
      "relative_m30": 25.2,
      "relative_ytd": 56.4,
      "sector_relative_ytd": 22.8,
      "latest_price": 45.67
    }
  ]
}
```

**SQL 核心逻辑：**

```sql
-- 成分股涨幅 vs 板块涨幅
SELECT st.stock_code, st.stock_name,
  (dk_latest.close_price / dk_30ago.close_price - 1) * 100 AS m30,
  (dk_latest.close_price / dk_yearend.close_price - 1) * 100 AS ytd
FROM stock_sectors ss
JOIN stocks st ON ss.stock_code = st.stock_code
JOIN daily_kline dk_latest ON st.stock_code = dk_latest.stock_code AND dk_latest.trade_date = @latest
LEFT JOIN daily_kline dk_30ago ON st.stock_code = dk_30ago.stock_code AND dk_30ago.trade_date = @30ago
LEFT JOIN daily_kline dk_yearend ON st.stock_code = dk_yearend.stock_code AND dk_yearend.trade_date = @yearend
WHERE ss.sector_code = @sector_code
  AND ss.category IN ('industry', 'concept')
ORDER BY ytd DESC;
```

#### API-4: 成分股K线对比

```
GET /api/strong/stock-kline
```

**Query 参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `sector_code` | string | 板块代码 |
| `stock_codes` | string | 逗号分隔的股票代码（可选，默认取板块涨幅前5） |
| `days` | int | 回溯天数，默认 120 |

返回格式同 API-2，series 中 type 区分 `sector` / `stock`。

#### API-5: 强势个股跨板比较

```
GET /api/strong/top-stocks
```

**Query 参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `category` | string | `industry` / `concept` / `all` |
| `sort_by` | string | `relative_ytd` / `relative_m30` / `change_today` |
| `top_n` | int | 每板块取前 N 只，默认 3 |

**返回：**

```json
{
  "sectors": [
    {
      "sector_code": "880948",
      "sector_name": "人工智能",
      "sector_ytd": 42.3,
      "stocks": [
        { "stock_code": "300123", "stock_name": "太阳能", "ytd": 65.1, "relative_ytd": 56.4 }
      ]
    }
  ]
}
```

### 2.3 前端页面设计

#### Page A: 板块强度排名

```
┌──────────────────────────────────────────────────────────────┐
│  强势板块排名                            [行业] [概念] [全部] │
│  景气度筛选: [全部] [高景气] [中景气] [低景气]                │
├──────────────────────────────────────────────────────────────┤
│  上证综指 000001  今日 +0.52%  30日 +3.10%  YTD +8.70%      │
├────┬──────────┬──────┬────────┬────────┬────────┬──────┬────┤
│ #  │ 板块名称  │ 类型  │ 成分股 │ 今日   │ 30日   │ YTD  │景气│
├────┼──────────┼──────┼────────┼────────┼────────┼──────┼────┤
│  1 │ 人工智能  │ 概念  │ 1062   │ +2.31% │+15.6% │+42.3%│ 高 │
│  2 │ 机器人    │ 概念  │ 1198   │ +1.85% │+12.3% │+38.1%│ 高 │
│  3 │ 煤炭      │ 行业  │  45    │ +0.92% │ +8.7% │+25.6%│ 中 │
│  ...                                                              │
└────┴──────────┴──────┴────────┴────────┴────────┴──────┴────┘
│  ↑ 点击表头排序（支持相对涨幅列排序）                             │
│  ↑ 点击板块行 → 进入 Page C 成分股页面                           │
└──────────────────────────────────────────────────────────────┘
```

**交互细节：**

- 默认按 YTD 相对上证涨幅降序排列
- 表头可点击切换排序维度（今日/30日/YTD，绝对/相对）
- 板块名称列旁显示相对上证的超额收益（绿色/红色箭头）
- 景气度用色块标注（绿=高、黄=中、灰=低）
- 点击任意板块行 → 跳转 Page C

#### Page B: 指数K线对比

```
┌──────────────────────────────────────────────────────────────┐
│  指数K线对比                                                  │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ 对比标的: [上证综指 ✓] [沪深300] [中证500]           │     │
│  │           [+ 添加板块指数]  (最多5个)                │     │
│  │ 周期: [1月] [3月] [6月] [1年] [全部]                 │     │
│  └─────────────────────────────────────────────────────┘     │
│  ┌─────────────────────────────────────────────────────┐     │
│  │                                                     │     │
│  │          K线图（lightweight-charts）                  │     │
│  │    多条叠加线，不同颜色区分                            │     │
│  │    底部成交量柱状图                                   │     │
│  │                                                     │     │
│  └─────────────────────────────────────────────────────┘     │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ 标的      │ 今日    │ 30日    │ YTD     │ 相对上证  │     │
│  │ 上证综指  │ +0.52%  │ +3.10%  │ +8.70%  │   —      │     │
│  │ 沪深300   │ +0.61%  │ +3.80%  │+10.20%  │ +1.50%   │     │
│  │ 中证500   │ +0.45%  │ +2.10%  │ +6.30%  │ -2.40%   │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

**交互细节：**

- 上证综指默认选中且不可移除（基准线）
- 可添加板块指数到对比（从板块列表搜索选择）
- K线图用 lightweight-charts 叠加渲染，每条线不同颜色
- 图表下方数据表同步显示各标的涨跌幅
- 支持鼠标悬浮显示某一日期各标的的精确数值

#### Page C: 板块成分股排名

```
┌──────────────────────────────────────────────────────────────┐
│  ← 返回板块排名    人工智能 (880948) 概念板块                 │
│  板块今日 +2.31%  30日 +15.6%  YTD +42.3%   景气度: 高       │
├──────────────────────────────────────────────────────────────┤
│  上证综指基准: 今日 +0.52%  30日 +3.10%  YTD +8.70%          │
├────┬────────┬────────┬────────┬────────┬────────┬───────────┤
│ #  │ 代码   │ 名称   │ 现价   │ 今日   │ 30日   │ YTD(相对) │
├────┼────────┼────────┼────────┼────────┼────────┼───────────┤
│  1 │ 300123 │ 太阳能  │ 45.67  │ +5.20% │+28.3% │ +56.4%   │
│  2 │ 002456 │ 欧菲光  │ 12.34  │ +4.10% │+22.1% │ +48.7%   │
│  ...                                                          │
└────┴────────┴────────┴────────┴────────┴────────┴───────────┘

│  ┌─────────────────────────────────────────────────────┐     │
│  │  成分股K线对比                                       │     │
│  │  [人工智能(板块指数)] [太阳能] [欧菲光] [+ 添加]    │     │
│  │  ┌─────────────────────────────────────────────┐   │     │
│  │  │  K线图：板块指数 + 选中成分股叠加对比         │   │     │
│  │  └─────────────────────────────────────────────┘   │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

**交互细节：**

- 成分股默认按 YTD 相对板块涨幅降序
- 点击成分股行 → 添加到 K线对比图
- K线图默认显示板块指数 + 涨幅最高的 2 只成分股
- 可勾选/取消成分股来切换对比标的

#### Page D: 强势个股跨板比较

```
┌──────────────────────────────────────────────────────────────┐
│  强势个股跨板比较                      [行业] [概念] [全部]   │
│  每板块Top: [3] [5] [10]    排序: [YTD] [30日] [今日]        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ 人工智能 (YTD +42.3%) ─────────────────────────┐       │
│  │  1. 太阳能 300123  +65.1%  ████████████████      │       │
│  │  2. 欧菲光 002456  +48.7%  █████████████         │       │
│  │  3. 科大讯飞 002230 +45.2%  ████████████          │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌─ 机器人 (YTD +38.1%) ───────────────────────────┐       │
│  │  1. 汇川技术 300124  +82.3%  ████████████████████│       │
│  │  2. 绿的谐波 688017  +71.5%  █████████████████    │       │
│  │  ...                                              │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌─ 煤炭 (YTD +25.6%) ────────────────────────────┐       │
│  │  ...                                              │       │
│  └──────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
```

**交互细节：**

- 按板块分组，每组展示板块内 Top N 强势股
- 涨幅用条形图可视化（横向 bar）
- 点击个股 → 跳转到已有的「股票画像」页面

### 2.4 技术方案

#### 后端文件结构

```
src/app/
  routers/
    strong.py              ← 新建：强势板块/个股 API
  strategies/
    strong_sector.py       ← 新建：板块强度计算逻辑
```

#### 前端文件结构

```
web/
  index.html              ← 新增 template: strong-tpl, strong-stocks-tpl
  app.js                  ← 新增 Vue 组件: strong-page, strong-stocks-page
  style.css               ← 新增板块排名/热力样式
```

#### 侧边栏导航

在 `pages` 数组中新增：

```javascript
{ id: 'strong', label: '强势板块', icon: '▲' },
{ id: 'strong_stocks', label: '强势个股', icon: '★' },
```

### 2.5 性能考量

| 问题 | 方案 |
|------|------|
| 415 个板块 × 3 个时间点 = ~1245 次K线查询 | 单次 SQL 批量 JOIN（见 API-1 SQL），MySQL 执行 < 2s |
| 1062 只成分股 × 3 个时间点 | 单次 SQL，受益于 `(stock_code, trade_date)` 索引 |
| 行业景气度实时计算 | 415 板块 × 成分股 fin 表聚合，可接受；或每日缓存 |
| K线图渲染 5 条叠加 | lightweight-charts 原生支持多 series，无性能问题 |

### 2.6 实施优先级

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **P0** | 新建 `index_kline` 表 + 导入上证综指等 5 个指数 | import 脚本 |
| **P0** | API-1 板块强度排名 + Page A | index_kline + sector_kline + sectors |
| **P0** | API-2 指数K线对比 + Page B | index_kline |
| **P1** | API-3 成分股排名 + Page C | daily_kline + stock_sectors |
| **P1** | API-4 成分股K线对比（Page C 内嵌） | daily_kline |
| **P2** | 行业景气度计算 + 景气度筛选 | fin_income + fin_balance_sheet |
| **P2** | API-5 强势个股跨板 + Page D | 全部数据 |
