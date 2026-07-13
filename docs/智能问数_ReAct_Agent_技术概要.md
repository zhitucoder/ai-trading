# 智能问数：LangChain ReAct Agent 技术概要

> 基于 LangChain + LangGraph 的 ReAct 智能问数引擎，用自然语言查询 A 股数据。

---

## 一、什么是 ReAct

ReAct = **Reasoning + Acting**，由 Shunyu Yao 等人于 2022 年提出。

核心思想：让 LLM 在**推理**和**行动**之间交替循环，而不是一步生成答案。

```
Thought: 用户问茅台股价，我需要查代码和行情
Action: query_database("SELECT ... WHERE stock_name LIKE '%茅台%'")
Observation: 600519
Thought: 找到了代码，现在查最新股价
Action: get_kline_data("600519", 5)
Observation: [{date: ..., close: 1204.98}, ...]
Thought: 数据齐了，生成回答
Final Answer: 贵州茅台最新收盘价 1204.98元...
```

**为什么需要 ReAct 而不是直接问 LLM？**
- LLM 训练数据有截止日期，不知道最新股价
- LLM 不会 SQL，无法查询数据库
- ReAct 让 LLM 把问题拆解成可执行的步骤，每步调用真实工具

---

## 二、系统架构

```
┌────────────────────────────────────────────────────┐
│                   前端 (Vue 3)                       │
│  聊天界面 → POST /api/query/ask ← 渲染Markdown/表格/图 │
└─────────────────────┬──────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────┐
│              FastAPI Router: query.py                │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │        LangGraph create_react_agent           │   │
│  │                                               │   │
│  │  System Prompt: 工具描述 + 回答规则 + 最新日期    │   │
│  │                                               │   │
│  │  Loop: Thought → Action → Observation → ...   │   │
│  │                     ↓                         │   │
│  │           5 个内置工具 (见下方)                 │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  LLM: ChatOpenAI(deepseek-v4-flash)                 │
│  LangGraph: create_react_agent                      │
└─────────────────────┬──────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
    ┌──────┐    ┌──────────┐   ┌────────┐
    │MySQL │    │ DuckDuckGo│  │ Ollama │
    │8.0   │    │ 搜索     │   │(备用)  │
    └──────┘    └──────────┘   └────────┘
```

---

## 三、工具设计

每个工具是一个 `@tool` 装饰的 Python 函数，LLM 根据场景自动选择调用：

| 工具 | 功能 | 典型触发场景 |
|------|------|-------------|
| `query_database(sql)` | 执行 SELECT SQL | "营收>20%的股票"、"有哪些板块" |
| `get_stock_code_from_name(name)` | 中文名称→6位代码 | "茅台"、"比亚迪" |
| `get_stock_name_from_code(code)` | 6位代码→中文名称 | "600519"、"000858" |
| `get_kline_data(code, days)` | OHLCV K线数据 | "股价多少"、"走势" |
| `search_web(query)` | 网络搜索 | "最新新闻"、"实时行情" |

### 安全约束
- `query_database` 只允许 `SELECT`/`WITH`/`SHOW` 语句，拒绝写操作
- 使用参数化查询防止注入

---

## 四、Agent 执行流程

```
1. 用户输入 → 构建 messages[]
2. create_react_agent.invoke()
3. LLM 输出 Action: 选择工具 + 参数
4. 执行工具 → 返回 Observation
5. LLM 根据 Observation 决定：
   → 继续：Thought → Action (循环)
   → 完成：Final Answer
6. 提取 Final Answer → format_agent_response()
7. 检测表格 → 拆分为 sections[{type, data}]
8. 检测股票代码 → 自动附加 K线图数据
9. 返回 {answer, sections} → 前端渲染
```

### 循环次数控制
- 默认无限制，但每个工具调用有 60s 超时
- 实践中通常 2-4 轮 Reasoning-Acting 循环即可完成

---

## 五、响应结构化处理

Agent 输出的是纯文本（Markdown），后端在后处理中拆分为结构化 sections：

```python
sections = [
    {"type": "text", "content": "文本回答..."},
    {"type": "table", "data": {"headers": [...], "rows": [[...]]}},
    {"type": "chart", "data": [{ohlcv}...], "stock_name": "茅台"},
]
```

前端根据 `type` 分别渲染：
- **text**: Markdown 转 HTML（粗体/代码/代码块）
- **table**: `<table>` 带正负值颜色
- **chart**: lightweight-charts K线图 + 成交量柱

---

## 六、关键依赖

```
langchain          1.3.13    核心框架
langgraph          1.2.9     ReAct Agent (create_react_agent)
langchain-openai   1.3.5     DeepSeek API 调用
duckduckgo_search  8.1       联网搜索
lightweight-charts 4.2.0     前端K线图 (CDN)
```

---

## 七、与专家系统的区别

| 维度 | 蒸馏专家 (expert.py) | 智能问数 (query.py) |
|------|--------------------|-------------------|
| 角色 | 巴菲特/利弗莫尔等人格 | 数据分析助手 |
| 回答方式 | 基于固定数据模板 + LLM | ReAct 自主查询数据库 |
| 数据获取 | 后端预取固定指标 | Agent 按需调用工具 |
| 灵活性 | 只能分析指定股票 | 任意数据库查询 |
| 图表 | 无 | 自动检测并附加 K线图 |
| 网络搜索 | 无 | 集成 DuckDuckGo |

---

## 八、使用示例

### ① 查询股价
```
Q: 贵州茅台最近股价多少？
→ 搜索网络获取实时行情
→ 查询数据库K线
→ 返回文本 + 表格 + K线图
```

### ② 财务筛选
```
Q: 筛选营收增长>20%且ROE>15%的股票
→ query_database("SELECT ... WHERE revenue_growth > 20 AND roe > 15")
→ 返回表格结果
```

### ③ 板块查询
```
Q: 有哪些板块？
→ query_database("SELECT name FROM sectors")
→ 返回板块列表
```

### ④ 综合查询
```
Q: 帮我分析盐湖股份的基本面
→ 搜索网络查最新消息
→ 查询数据库拿财务数据
→ 综合回答
```

---

## 九、已知限制

1. **联网搜索不稳定**：DuckDuckGo 在国内可能被限，搜索结果质量不定
2. **SQL 生成依赖模型能力**：DeepSeek v4 Flash 对复杂 SQL（多表 JOIN / 窗口函数）的生成偶有错误
3. **无流式输出**：当前为一次性响应，Agent 思考过程用户不可见
4. **历史上下文有限**：只保留最近 6 轮对话

---

## 十、扩展方向

- [ ] **流式输出**：SSE 推送 Agent 思考过程，用户可见 Thought→Action→Observation
- [ ] **图表多样性**：支持饼图、柱状图（Chart.js）
- [ ] **更多工具**：财报 PDF 解析、公告查询、北向资金
- [ ] **记忆持久化**：跨会话记忆用户偏好股票
- [ ] **多 Agent 协作**：分析师 + 风控 + 数据工程师并行工作
