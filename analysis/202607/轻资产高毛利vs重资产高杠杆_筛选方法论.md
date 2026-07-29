# 轻资产高毛利 vs 重资产高杠杆：用数据筛选两类公司

> 分析日期：2026年7月 | 数据来源：ai_trading 数据库 2025年报

---

## 一、为什么要区分这两类

财务报表分析的起点不是算比率，而是看清企业的资产结构——它决定了企业赚钱的方式和风险的特征。

- **轻资产高毛利**：赚钱靠技术/品牌/IP，不需要大量资本投入。代表：茅台、艾力斯、新易盛
- **重资产高杠杆**：赚钱靠产能/规模，需要不断投钱买设备建工厂。代表：中芯国际、博俊科技、金石资源

两类公司的财务指标差异极大，不能用同一套标准评价。

---

## 二、筛选指标

### 2.1 关键指标定义

| 指标 | 公式 | 说明 |
|:---|:---|:---|
| 固定资产/总资产 | 固定资产÷总资产 | 衡量资产轻重 |
| 有息负债率 | (短期借款+长期借款)÷总资产 | 衡量杠杆水平 |
| 毛利率 | (营收−营业成本)÷营收 | 衡量产品或服务的溢价能力 |
| OCF/净利润 | 经营现金流÷净利润 | 衡量利润的现金含金量 |

### 2.2 分类阈值

**轻资产高毛利型：**
- 固定资产/总资产 < 15%
- 毛利率 > 40%
- 有息负债率 < 10%（越低越好）
- OCF/净利润 > 0.7

**重资产高杠杆型：**
- 固定资产/总资产 > 30%
- 有息负债率 > 15%
- 毛利率 < 30%
- OCF/净利润 < 1.0（越低说明资金占用越严重）

---

## 三、数据库筛选SQL

### 3.1 筛选轻资产高毛利公司

```sql
SELECT
    k.stock_code,
    s.stock_name,
    ROUND(k.operating_revenue / 1e8, 1) AS rev_亿,
    ROUND((k.operating_revenue - k.operating_cost) / k.operating_revenue * 100, 1) AS gross_margin_pct,
    ROUND(b.fixed_assets / b.total_assets * 100, 1) AS fa_ratio_pct,
    ROUND(COALESCE((b.short_term_borrow + b.long_term_borrow) / b.total_assets * 100, 0), 1) AS debt_ratio_pct,
    ROUND(c.op_cash_flow / k.net_profit, 2) AS ocf_to_np
FROM fin_income k
JOIN stocks s ON k.stock_code = s.stock_code
JOIN fin_balance_sheet b ON k.stock_code = b.stock_code AND b.report_date = '2025-12-31'
JOIN fin_cash_flow c ON k.stock_code = c.stock_code AND c.report_date = '2025-12-31'
WHERE k.report_date = '2025-12-31'
  AND k.operating_revenue > 1e9
  AND b.fixed_assets / b.total_assets < 0.15
  AND (k.operating_revenue - k.operating_cost) / k.operating_revenue > 0.40
  AND COALESCE((b.short_term_borrow + b.long_term_borrow) / b.total_assets * 100, 0) < 10
  AND k.net_profit > 0
ORDER BY gross_margin_pct DESC;
```

### 3.2 筛选重资产高杠杆公司

```sql
SELECT
    k.stock_code,
    s.stock_name,
    ROUND(k.operating_revenue / 1e8, 1) AS rev_亿,
    ROUND((k.operating_revenue - k.operating_cost) / k.operating_revenue * 100, 1) AS gross_margin_pct,
    ROUND(b.fixed_assets / b.total_assets * 100, 1) AS fa_ratio_pct,
    ROUND(COALESCE((b.short_term_borrow + b.long_term_borrow) / b.total_assets * 100, 0), 1) AS debt_ratio_pct,
    ROUND(c.op_cash_flow / k.net_profit, 2) AS ocf_to_np
FROM fin_income k
JOIN stocks s ON k.stock_code = s.stock_code
JOIN fin_balance_sheet b ON k.stock_code = b.stock_code AND b.report_date = '2025-12-31'
JOIN fin_cash_flow c ON k.stock_code = c.stock_code AND c.report_date = '2025-12-31'
WHERE k.report_date = '2025-12-31'
  AND k.operating_revenue > 1e9
  AND b.fixed_assets / b.total_assets > 0.30
  AND COALESCE((b.short_term_borrow + b.long_term_borrow) / b.total_assets * 100, 0) > 15
  AND (k.operating_revenue - k.operating_cost) / k.operating_revenue < 0.30
  AND k.net_profit > 0
ORDER BY fa_ratio_pct DESC;
```

---

## 四、实际筛选结果

### 4.1 轻资产高毛利公司（基于数据库2025年报）

| 股票 | 营收(亿) | 毛利率 | 固资/资产 | 有息负债率 | OCF/净利 |
|:---|:---:|:---:|:---:|:---:|:---:|
| **贵州茅台** | 1,688 | **91.2%** | 7.4% | 0% | 0.72x |
| **艾力斯** | 52 | **96.8%** | 6.5% | 0% | 1.06x |
| **新易盛** | 248 | **47.8%** | 13.0% | 0% | 0.81x |
| **盛美上海** | 68 | **48.3%** | 9.7% | 8.4% | 0.17x |
| **寒武纪** | 65 | **55.2%** | 2.8% | 0% | -0.24x |

**共同特征：**
- 固定资产占比 < 15%（没有大量厂房设备投入）
- 毛利率 > 40%（产品有溢价能力）
- 有息负债率接近0（不需要借钱）
- 现金充裕

**但它们内部也有差异：**

艾力斯毛利率97%最高，但营收52亿规模最小——单一产品风险。
新易盛毛利率48%，营收248亿——规模最大、弹性最强。
盛美上海毛利率48%，但OCF/净利仅0.17x——利润含金量低，和同行差距大。
寒武纪OCF为负——刚扭亏，现金流还需验证。

### 4.2 重资产高杠杆公司

| 股票 | 营收(亿) | 毛利率 | 固资/资产 | 有息负债率 | OCF/净利 |
|:---|:---:|:---:|:---:|:---:|:---:|
| **金石资源** | 39 | 17.8% | **39.4%** | **39.0%** | 0.37x |
| **博俊科技** | 58 | 26.1% | **32.9%** | **20.7%** | 0.51x |
| **中芯国际** | 673 | 21.6% | **37.1%** | **20.1%** | 2.79x |

**共同特征：**
- 固定资产占比 > 30%（大量资金沉淀在厂房设备）
- 有息负债率 > 15%（借钱扩产是常态）
- 毛利率 < 30%（产品溢价能力有限）

---

## 五、混合型公司（介于两者之间）

很多公司无法简单归于任何一类，它们有自己独特的财务特征：

| 股票 | 营收(亿) | 毛利率 | 固资/资产 | 有息负债率 | OCF/净利 | 特点 |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| **中际旭创** | 382 | 42.0% | 15.6% | 1.8% | 0.94x | 高毛利低杠杆，但固资接近15% |
| **天孚通信** | 52 | 54.0% | 17.3% | 0% | 0.93x | 高毛利近零杠杆，固资略高于15% |
| **香农芯创** | 353 | 4.0% | 0.6% | 18.6% | 2.07x | 极轻资产，但有息负债率高 |
| **帝科股份** | 181 | 9.1% | 5.8% | 28.3% | -3.32x | 轻资产但高杠杆+亏损 |

**中际旭创**的固定资产/总资产15.6%，非常接近15%的阈值——它的资产"轻"和光模块行业相关（组装测试设备为主），但规模上去后固定资产自然增加。仍属于高毛利、低杠杆的优质类型。

**香农芯创**是一个特例——固定资产仅0.6%（分销商模式），但短期借款高（有息负债率18.6%），因为分销商需要借钱垫付采购款。它的"高杠杆"不是用来建工厂，而是用来做营运资金。

**帝科股份**是最危险的类型——轻资产（固定资产5.8%）、高杠杆（28.3%）、还亏损（OCF/净利-3.32x）。轻资产但没有定价权，高杠杆但没有利润来覆盖利息成本。

---

## 六、两类公司的投资逻辑差异

| 维度 | 轻资产高毛利 | 重资产高杠杆 |
|:---|:---|:---|
| 护城河来源 | 技术/品牌/专利/配方 | 规模/产能/客户关系 |
| 增长驱动 | 产品升级/提价/市占率提升 | 资本开支/产能扩张 |
| 利润弹性 | 营收增长直接转化为利润 | 折旧高，利润增长慢于营收 |
| 现金流特征 | OCF/净利通常 > 0.8 | OCF/净利通常 < 0.6 |
| 最大风险 | 技术迭代/竞品替代 | 产能过剩/债务违约 |
| 行业代表 | 白酒、创新药、光模块、芯片设计 | 晶圆代工、矿业、汽车零部件 |

**轻资产高毛利公司**：买的是"赚钱机器"。增长来自产品溢价和市占率提升，不需要大量资本投入。这类公司适合用ROE和毛利率来评价。

**重资产高杠杆公司**：买的是"产能+周期"。增长来自产能扩张和行业景气度，需要不断投入资本。这类公司适合用产能利用率、OCF和负债率来评价。在行业上行期弹性大，但在下行期风险集中。

---

## 七、用这套框架看今天的分析标的

基于今天的分析，可以从"轻vs重、毛利vs杠杆"两个维度画一个四象限：

```
                  高毛利
                    ↑
                    |
    盛美上海   ·   |   ·  中际旭创
    寒武纪     ·   |   ·  天孚通信
    艾力斯     ·   |   ·  百济神州
                    |
 轻资产 ←——————+——————→ 重资产
                    |
    香农芯创   ·   |   ·  博俊科技
    帝科股份   ·   |   ·  中芯国际
    合康新能   ·   |   ·  金石资源
                    |
                  低毛利
```

- **右上角（轻资产+高毛利）**——最佳模式：艾力斯、新易盛、贵州茅台
- **右下角（轻资产+低毛利）**——需要警惕：香农芯创、合康新能
- **左上角（重资产+高毛利）**——极少见，有护城河：中际旭创、天孚通信
- **左下角（重资产+低毛利）**——需要跟踪周期：中芯国际、博俊科技、金石资源

---

> 数据来源：ai_trading 数据库 fin_income、fin_balance_sheet、fin_cash_flow（2025年报）
> 分析框架：AI蒸馏专家"战略视角财务报表分析"框架
> 阈值为经验值，根据行业特征可调整。不构成投资建议。
