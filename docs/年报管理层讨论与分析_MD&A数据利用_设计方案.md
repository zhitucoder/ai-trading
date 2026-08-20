# 年报「管理层讨论与分析」数据利用 —— 设计方案

> 版本：v1.0 | 日期：2026-08
> 关联：`src/download_reports.py`、`src/app/routers/query.py`、`src/app/routers/screening.py`、`report_pdf` 表
> 数据现状：1319 份 2025 年报 PDF 已入库（`~/workspace/annual_reports/2025/annual/{cninfo|sse|szse}/*.pdf`），`report_pdf` 表有完整 file_path

---

## 一、背景与目标

### 1.1 需求

已下载全市场年报 PDF。年报**第三节「管理层讨论与分析」（MD&A）** 是唯一官方要求公司必须自述的章节，包含：

| MD&A 子节 | 含金量 | 用途 |
|:---|:---|:---|
| 二、报告期内公司所处行业情况 | 行业数据 + 行业判断 | 行业问答的数据源 |
| 十一（一）行业格局和趋势 | 政策 + 产业趋势前瞻 | 未来增长判断 |
| 三、核心竞争力分析 | 地位/市占率/壁垒 | 龙头识别 |
| 十一（二）公司发展战略、（四）发展目标 | 未来方向、业绩目标 | 成长性预判 |
| 产能/资本开支/募投计划 | **明确投入金额** | "政策资金投入"信号 |
| 十一（五）可能面对的风险 | 风险点 | 排雷 |

目标：**利用 MD&A 找出"近年持续增长 + 未来仍有增长空间（政策支持、明确资金投入）"的公司，并在其龙头地位被市场充分定价前发现它们。**

### 1.2 要解决的三个核心问题

1. **问公司**：用户问某家公司 → 直接查该公司 MD&A ✓（简单）
2. **问行业**：MD&A 是每家公司的，行业信息分散在成百上千份年报里，用户不知道查哪家 ✗（需聚合）
3. **opencode/LLM 客户端**：客户端不知道"读哪个 PDF 文件" ✗（需知识索引）

> **核心设计思想**：所有上层客户端（网页、智能问数 Agent、opencode）**永远不直接读 PDF 文件**，而是查询一套**预构建的 MD&A 知识表**（`report_mda` → `stock_mda_ai` → `sector_mda_ai`）。表的键是 `stock_code` / `sector_code`，天然解决"该查哪个"的问题。PDF 只在离线提取时被读一次。

---

## 二、整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│ 离线管线（年报季跑一次，~几小时）                                        │
│                                                                      │
│  report_pdf  →  ①提取 extract_mda.py     →  report_mda 表             │
│  1319 PDF     （pymupdf 定位第三节）        原始MD&A全文+子节JSON        │
│                                ↓                                     │
│                  ②AI蒸馏 compute_mda_ai.py →  stock_mda_ai 表          │
│                  （LLM结构化，每公司一条）    公司级增长信号摘要           │
│                                ↓                                     │
│                  ③行业聚合（同脚本）         →  sector_mda_ai 表        │
│                  板块成员MD&A汇聚+蒸馏        行业级增长信号摘要           │
└──────────────────────────────────────────────────────────────────────┘
                                   ↓
┌──────────────────────────────────────────────────────────────────────┐
│ 在线服务（FastAPI，无LLM调用，毫秒级）                                   │
│                                                                      │
│  routers/mda.py         → GET /api/mda/stock/{code}                  │
│                           GET /api/mda/search?q=政策+投入             │
│                           GET /api/mda/sector?name=白酒              │
│  query.py ReAct 加3个工具 → get_mda / search_mda / get_sector_mda     │
│  screening.py 新策略     → mda_growth（增长信号∩财务∩低位）              │
│  画像页新卡片            → 公司MD&A摘要                               │
└──────────────────────────────────────────────────────────────────────┘
                                   ↑
            任何客户端（网页 / 智能问数 / opencode）都走这两层表
```

**为什么不直接把 1319 份 PDF 全文塞给 LLM / 每次现场提取？**
- MD&A 一节 5~20 页，全文检索和问答逐份读 PDF 是秒级到分钟级延迟，不可用
- LLM 现场蒸馏 1319 份要十几块钱/每次，预计算一次成本几元，之后查询零成本
- 预计算符合本项目 `ads_*` 表的既有模式（离线算好、在线秒查）

---

## 三、数据模型

### 3.1 `report_mda` —— 原始提取表（每公司×每年度一条）

```sql
CREATE TABLE report_mda (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  stock_code     VARCHAR(10)  NOT NULL COMMENT '股票代码',
  report_year    SMALLINT     NOT NULL COMMENT '报告年度',
  source         VARCHAR(20)  DEFAULT 'cninfo' COMMENT 'PDF来源',
  file_path      VARCHAR(512) DEFAULT NULL COMMENT '年报PDF路径',
  section_title  VARCHAR(100) DEFAULT NULL COMMENT '识别到的章节标题',
  page_start     SMALLINT     DEFAULT NULL COMMENT '第三节起始PDF页',
  page_end       SMALLINT     DEFAULT NULL COMMENT '第三节结束PDF页',
  mda_text       MEDIUMTEXT   COMMENT '第三节全文（约3k~20k字）',
  subsections    JSON         COMMENT '{“一”: “…”, “二”: “…”, …} 按中文数字小节拆分',
  extract_status VARCHAR(20)  DEFAULT 'ok' COMMENT 'ok / failed / section_not_found',
  extract_time   DATETIME     DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_stock_year (stock_code, report_year, source),
  KEY idx_status (extract_status),
  FULLTEXT KEY ft_mda (mda_text)         -- search_mda 用
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**提取算法**（`src/extract_mda.py`，pymupdf）：

```
1. 从 report_pdf 取 (stock_code, file_path)，全部走已存在的路径，不自己找文件
2. 读目录页：定位“第三节 管理层讨论与分析” → 得到正文起始页码
3. 从起始页顺序读，直到出现“第四节 公司治理” 或 “第四节 公司治理、环境和社会” 停
4. 全文中按正则 ^[一二三四五六七八九十]+、 拆分小节 → subsections JSON
5. 容错：目录页找不到“第三节”时，退化扫描全文找 “管理层讨论与分析” 页眉
   仍失败 → extract_status='section_not_found'（2019 前旧格式年报/个别非标格式）
6. 只入库，不动 PDF
```

**预计**：1319 份 × ~2 秒/份（pymupdf 很快，主要是 IO）≈ 1 小时以内，多线程可压缩到 15 分钟。

### 3.2 `stock_mda_ai` —— 公司级增长信号（AI 蒸馏，每公司×最新年度一条）

```sql
CREATE TABLE stock_mda_ai (
  stock_code       VARCHAR(10)  PRIMARY KEY,
  stock_name       VARCHAR(50)  DEFAULT NULL,
  report_year      SMALLINT     NOT NULL,
  industry         VARCHAR(100) DEFAULT NULL COMMENT '行业（取 sectors.industry[0]）',
  industry_view    VARCHAR(500) DEFAULT NULL COMMENT '公司对行业景气的判断（原文浓缩）',
  policy_signals   JSON         COMMENT '[{policy, scope, detail, amount}] 政策名称/层级/内容/投入金额',
  company_position VARCHAR(500) DEFAULT NULL COMMENT '地位/市占率/龙头/壁垒表述',
  growth_drivers   JSON         COMMENT '未来增长驱动点列表',
  capacity_plan    VARCHAR(1000) DEFAULT NULL COMMENT '产能扩张/资本开支/募投计划（含金额）',
  guidance         VARCHAR(500) DEFAULT NULL COMMENT '下一年度经营目标/业绩指引',
  risks            VARCHAR(1000) DEFAULT NULL COMMENT '管理层提示风险',
  signal_score     TINYINT      DEFAULT 0 COMMENT '-3~+3：增长信号强度（正=政策+扩产+龙头）',
  evidence         TEXT         COMMENT '关键证据原文摘录（可追溯）',
  ai_model         VARCHAR(50)  DEFAULT NULL,
  updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_stock_year (stock_code, report_year),
  KEY idx_score (signal_score),
  KEY idx_industry (industry)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**Prompt 输入**（全部本地可信，不联网）：
- `report_mda.subsections`（重点：行业情况、行业格局和趋势、核心竞争力、发展战略、发展目标、风险）
- 行业板块、近 3 年营收/净利及增速（`ads_stock_annual`）、最新市值/PE/股息率（`ads_stock_latest`）

**Prompt 输出约束**：严格 JSON，`signal_score` 按规则打分——明确国家/产业政策 + 明确金额 + 龙头表述 + 扩产计划 各加权重，管理层承认需求下滑/只字不提前景 则降分。失败重试 2 次。

**成本估算**：输入约 4~6k token/公司，输出约 0.5k；1319 家总输入约 700 万 token。按 DeepSeek 量级价格约几元~十几元人民币（具体以 .env 配置为准），远低于每次现场蒸馏。

### 3.3 `sector_mda_ai` —— 行业级增长信号（解决"问行业"）

```sql
CREATE TABLE sector_mda_ai (
  sector_code     VARCHAR(20)  PRIMARY KEY,
  sector_name     VARCHAR(100) NOT NULL,
  category        VARCHAR(20)  DEFAULT 'industry',
  member_count    SMALLINT     DEFAULT 0 COMMENT '参与聚合的年报数',
  industry_trend  VARCHAR(1000) DEFAULT NULL COMMENT '行业趋势共识（多公司MD&A交汇）',
  policy_signals  JSON         COMMENT '行业级政策信号（跨公司合并去重）',
  stated_growth   VARCHAR(1000) DEFAULT NULL COMMENT '各公司对行业增长的判断汇总',
  leaders         JSON         COMMENT '公认龙头名单（多份年报同时提及“龙头/第一”）',
  signal_score    TINYINT      DEFAULT 0 COMMENT '行业增长信号强度',
  updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**聚合逻辑**：`sectors(行业) → stock_sectors(成分股) → report_mda(stock_code IN 成员) → 取各公司“行业情况/行业格局和趋势”子节 → 拼接后 LLM 蒸馏成行业级一条**。行业名从板块表带出，用户只输行业名即可，无需知道哪家公司。

> 这就是"问行业不知道查哪家公司"的答案：**系统内部用 `sector_code → 成员股票 → MD&A` 自动展开聚合**，对用户完全透明。

---

## 四、在线服务设计

### 4.1 新路由 `src/app/routers/mda.py`（注册进 main.py）

| 接口 | 功能 | 典型问题 |
|:---|:---|:---|
| `GET /api/mda/stock/{code}?summary=1` | 单公司 MD&A（summary=1 返回 AI 摘要，=0 返回原文子节） | "看看 600519 的年报怎么说" |
| `GET /api/mda/search?q=扩产+投入&limit=50` | `report_mda` FULLTEXT 关键词检索，返回命中公司+片段 | "哪些公司年报提到明确资金投入" |
| `GET /api/mda/sector?name=白酒` | 行业级 AI 摘要 + 龙头 + 政策 | "白酒行业未来趋势怎样" |
| `GET /api/mda/top?score=2` | 按 signal_score 倒序，联合 ads 数据 | "增长信号最强的公司列表" |
| `POST /api/mda/extract` | 后台触发离线提取（进度见 status） | 数据管理页一键更新 |
| `POST /api/mda/compute-ai` | 后台触发 AI 蒸馏 | 同上 |

### 4.2 智能问数（`query.py`）加 3 个 ReAct 工具

| 工具 | 输入 | 行为 |
|:---|:---|:---|
| `get_mda(stock_code)` | 6 位代码 | 返回 `stock_mda_ai` 摘要，可带原文引用 |
| `search_mda(keyword)` | 关键词 | FULLTEXT 检索，返回公司列表 |
| `get_sector_mda(name)` | 行业/板块名 | 查 `sector_mda_ai`，无则自动聚合 |

同步更新 `TOOLS_DESC` 与工具列表。这样：

- "分析一下 600519 的管理层展望" → `get_mda`
- "哪些公司年报提到了'低空经济'和具体投入" → `search_mda`
- "光伏行业今年各家年报怎么说行业前景" → `get_sector_mda('光伏')`

### 4.3 筛选策略 `src/app/strategies/mda_growth.py`（新卡片）

`screen_mda_growth()` = 三条件叠加，**定性信号 + 量化验证 + 位置过滤**：

```
1. 定性信号：stock_mda_ai.signal_score >= 1（政策+扩产+龙头任一）
2. 量化验证：ads_stock_annual 近N年营收/净利连续正增长（N 参数 3~7 可调）
             ∩ ads_stock_latest 最新净利/营收同比为正
3. 位置过滤（避免“已飞升”）：
   - 现价距 120 日/250 日最高回撤 > X%（默认 15%）
   - 或 PE_TTM 处于自身近 5 年 < 50% 分位（用 daily_kline + pe_ttm 现算）
输出：stock_code, name, 行业, signal_score, 连续增长年数, 回撤幅度, PE分位, evidence(政策原文摘录)
```

注册：`list_strategies()` 增一项 + `execute_screening()` 增 `if strategy_id == 'mda_growth'` 分支 + `web/index.html` 加卡片。完全沿用"Adding a new screening strategy"流程。

### 4.4 个股画像页加 MD&A 卡片

`/api/profile/{code}` 响应追加 `mda` 字段（取 `stock_mda_ai`），画像页头部下方渲染"管理层展望"卡片：政策信号 / 扩产计划 / 下年目标 / 风险，降级策略同 `stock_intro`（无数据不显示）。

---

## 五、opencode 客户端怎么用（回答"我不知道查哪个文件"）

**opencode 不需要知道文件。** 新增表就是知识索引，`AGENTS.md` 补一段说明即可：

```
## 年报 MD&A 知识表（问公司/行业/增长信号一律查表，不要读PDF）

- report_mda    原始第三节全文 + 子节JSON（关键词检索用 FULLTEXT）
- stock_mda_ai  每公司 AI 蒸馏：行业判断/政策信号/龙头地位/扩产计划/目标/风险/增长评分
- sector_mda_ai 每行业 AI 聚合：行业趋势共识/行业政策/龙头名单/行业评分

使用模式：
- 问某公司 → SELECT * FROM stock_mda_ai WHERE stock_code='600519'
- 找增长信号强、股价未飞升 → SELECT ... JOIN ads_stock_latest（见 mda_growth 策略）
- 问行业 → SELECT * FROM sector_mda_ai WHERE sector_name LIKE '%白酒%'
- 关键词筛选 → SELECT ... WHERE MATCH(mda_text) AGAINST('低空经济 投入' IN BOOLEAN MODE)
```

opencode 直接 `SELECT` 这些表，或 curl 本地 `http://localhost:9000/api/mda/*`。**文件路径只存在于 `report_mda.file_path`，正常流程没人需要关心它。**

> 这与你已掌握的"总股本取 `stock_shares_dfcf`"是同一套路：`ads_*` 预计算表 = 权威知识源，客户端只查表。

---

## 六、实施步骤

| 步骤 | 内容 | 涉及文件 | 耗时 |
|:---|:---|:---|:---|
| 1 | 安装 pymupdf（已装 1.28.2） | 环境 | — |
| 2 | 建 3 张表 + FULLTEXT 索引 | `src/extract_mda.py` 内 CREATE | — |
| 3 | 提取脚本：目录页定位 → 子节拆分 → 入库，断点续跑 | `src/extract_mda.py`（新） | ~1h |
| 4 | 抽查 5~10 份结果质量（含一家 ST、一家金融股） | 手动 | 30min |
| 5 | AI 蒸馏脚本：逐公司 LLM → `stock_mda_ai`，`--workers 8 --resume` 断点续跑 | `src/compute_mda_ai.py`（新） | ~1h + 几元token |
| 6 | 行业聚合：板块成员 MD&A 拼接 → LLM → `sector_mda_ai` | 同脚本 `--mode sector` | ~10min |
| 7 | 路由 `mda.py` + 注册 main.py | `src/app/routers/mda.py`（新） | 半天 |
| 8 | ReAct 3 工具 + TOOLS_DESC | `src/app/routers/query.py` | 半天 |
| 9 | 筛选策略 `mda_growth` + 注册 + 前端卡片 | `strategies/mda_growth.py`、`screening.py`、`index.html` | 半天 |
| 10 | 画像页 MD&A 卡片 | `profile.py`、`web/` | 半天 |
| 11 | AGENTS.md 补充知识表说明 | `AGENTS.md` | 10min |

---

## 七、风险与注意事项

1. **公司自述有宣传成分**：MD&A 是管理层写的，行业景气判断可能偏乐观。**只作为线索，不作为结论**——最终必须叠加 `ads_*` 量化数据交叉验证（策略第 2 步就是干这个）
2. **未来展望非承诺**：年报里明确声明"前瞻性陈述不构成实质承诺"，`guidance` 字段只用于对比次年实际完成情况
3. **政策金额要甄别**："明确投入"分两层——国家/行业规划的总投入（行业级机会）vs 公司自身的资本开支计划（公司级机会），`policy_signals.amount` 需带 `scope` 字段区分
4. **金融/个别旧格式年报**：2019 年及之前部分公司章节结构不同，`section_not_found` 占比需统计，不影响新数据
5. **每年更新节奏**：年报 4 月底披露完毕 → 每年 5 月重跑 extract + compute-ai 即可；次年数据未出时只比对上一年 `guidance`
6. **FULLTEXT 中文分词**：MySQL 默认分词对中文关键词按字切分，`search_mda` 用 `IN BOOLEAN MODE` 引号包裹短语即可；长尾效果不佳时可改用简单 n-gram 或先跑 `stock_mda_ai` 的结构化字段
7. **token 成本可控**：1319 家公司一次性蒸馏约几元~十几元量级；`--resume` 保证中断不重算
