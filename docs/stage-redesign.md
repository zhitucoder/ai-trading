# 股票四阶段（S1-S4）量化标准重构设计

> 设计目标：基于 Mark Minervini SEPA 方法论，重构 `compute_stage()` 计算逻辑
> 当前状态：现有逻辑过于宽松（S2 仅需 7 条简单条件）、S1/S3 判定模糊、置信度缺乏区分度

---

## 一、Minervini 四阶段核心定义

| 阶段 | Minervini 描述 | 量化目标 |
|------|---------------|---------|
| **S1 打底蓄势** | 下跌后横盘整理，MA由跌转平，成交量萎缩，价格在窄幅区间震荡 | 识别底部形态 + 均线走平 + 量缩 |
| **S2 突围加速** | 放量突破底部，价格>50日>150日>200日MA，RS强势，连续higher highs/lows | MA多头排列 + 突破特征 + 相对强度 |
| **S3 见顶派发** | 大幅上涨后波动加剧，量价背离，MA开始走平或下弯 | 高波动 + 高位震荡 + 派发信号 |
| **S4 衰败下跌** | 价格<200日MA，MA下行，lower highs/lows，RS弱势 | 空头排列 + 新低 + 弱势确认 |

---

## 二、当前实现问题清单

| 问题 | 当前代码 | 问题说明 |
|------|---------|---------|
| S2 条件过松 | 7 条条件全部满足即 S2 | 未要求 VCP 收缩形态、未要求放量突破、未要求 RS 强度 |
| S1 是兜底 | `else {stage='S1',confidence=50}` | 只要不满足其他条件就是 S1，没有主动判断底部形态 |
| S3 仅看波动率 | `recent_volatility > past * 1.5` | 忽略量价背离、高位分布、MA 走平等关键信号 |
| S4 条件模糊 | 仅检查 MA200 下方比例 | 缺少确认下降趋势的连续信号 |
| 置信度无意义 | S2=min(95,...) S4=75 S3=60 S1=50 | 固定值，无法区分"强 S2"和"弱 S2" |
| 未使用 RS | 完全没有相对强度指标 | Minervini 最核心的指标缺失 |
| 未使用成交量 | 仅用于计算均线 | 突破需要放量验证 |

---

## 三、重新设计的量化框架

### 3.1 核心指标计算

所有阶段共享以下基础指标：

```python
# 均线
ma20  = SMA(close, 20)
ma50  = SMA(close, 50)
ma150 = SMA(close, 150)
ma200 = SMA(close, 200)

# 价格位置
above_ma50  = close > ma50
above_ma150 = close > ma150
above_ma200 = close > ma200
pct_off_52w_high = (close - 52w_high) / 52w_high
pct_off_52w_low  = (close - 52w_low) / 52w_low

# 相对强度 (RS)
rs_score = percentile_rank(price_return_12m, all_stocks)  # 0-99
rs_line  = ratio_chart(stock_price / index_price)         # 相对线

# 成交量比
vol_ratio_50 = volume / SMA(volume, 50)   # 最近日成交量 / 50日均量
vol_ratio_10 = volume / SMA(volume, 10)

# 波动率
atr_20   = ATR(high, low, close, 20)
atr_50   = ATR(high, low, close, 50)
volatility_ratio = atr_20 / atr_50

# VCP (波动收缩)
vcp_count = count_contractions(high, low, 20)  # 最近20日波动收缩次数
vcp_tightness = (high_max - low_min) / close   # 收缩幅度
```

### 3.2 S2 判定（突围加速期）

**核心思想：Minervini 的趋势模板 + VCP + 突破确认**

必须满足以下**所有**条件（12条）：

```python
S2_CRITERIA = [
    # ── 趋势模板（核心7条）──
    "close > ma150 AND close > ma200",          # 价格在长期均线上方
    "ma150 > ma200",                             # 长期均线多头
    "ma200_20d_ago < ma200_now",                 # 200日MA向上（20天对比）
    "close > ma50",                              # 价格在短期均线上方
    "ma50 > ma150 AND ma50 > ma200",             # 短期均线在长期上方
    "close >= 52w_low * 1.30",                   # 从52周低点上涨至少30%
    "close >= 52w_high * 0.75",                  # 距离52周高点不超过25%

    # ── 突破确认 ──
    "vol_ratio_50 >= 1.5",                       # 放量（当前量 > 50日均量50%）
    "vcp_count >= 2",                            # 最近20日至少出现2次波动收缩
    "rs_score >= 70",                            # 相对强度排名前30%

    # ── 趋势健康 ──
    "recent_20d_high > prev_20d_high",           # 最近20日高点高于前20日高点（higher high）
    "recent_20d_low > prev_20d_low",             # 最近20日低点高于前20日低点（higher low）
]
```

**置信度** = 满足条件的数量 / 12 × 100 + 额外加分

```python
extra = 0
if rs_score >= 90: extra += 10      # RS 顶级
if vol_ratio_50 >= 2.0: extra += 5  # 巨量突破
if vcp_tightness < 0.1: extra += 5  # 极度收缩后突破
confidence = min(99, met_count / 12 * 100 + extra)
```

### 3.3 S1 判定（打底蓄势期）

**核心思想：底部形态识别，主动判断而非兜底**

```python
S1_CRITERIA = [
    # ── 底部形态 ──
    "close < ma200 OR (close < ma50)",                # 价格在均线附近或下方
    "ma200_slope_60d BETWEEN -0.05 AND 0.05",         # 200日MA走平（60天内变化<5%）
    "52w_range_ratio < 0.35",                          # 52周振幅 < 35%（窄幅震荡）
    "vol_ratio_50 < 1.0",                              # 成交量低于均量（缩量）

    # ── 底部内部结构 ──
    "recent_30d_amplitude < recent_30d_amplitude_max * 0.5",  # 波动收窄
    "close > 52w_low * 1.05",                          # 已脱离最低点
    "close < 52w_high * 0.85",                         # 距离高点还有空间
]
```

**置信度**: 满足条件越多 → 底部形态越清晰

```python
confidence = met_count / len(S1_CRITERIA) * 80 + 10
```

**注意**：S1 优先级低于 S2。如果同时满足 S1 和 S2 条件 → S2。

### 3.4 S3 判定（见顶派发期）

**核心思想：经历大幅上涨后的高位异常信号**

```python
S3_CRITERIA = [
    # ── 前期大涨（S3的前提条件）──
    "close > 52w_high * 0.90",                         # 接近52周高点
    "return_12m > 50",                                  # 过去1年涨幅>50%

    # ── 异常信号 ──
    "volatility_ratio > 1.5",                           # 波动率放大
    "vol_ratio_50 < 0.7 AND close < ma20",              # 缩量下跌（派发）
    "ma50_slope_20d < -0.01",                           # 50日MA开始下弯
    "close < ma50 AND close < ma20",                    # 跌破短期均线
    "recent_20d_high < prev_20d_high",                  # 更低的高点
]
```

**优先级规则**：S3 仅当也满足 **前期大涨条件** 时才判定。

### 3.5 S4 判定（衰败下跌期）

**核心思想：确认的下降趋势**

```python
S4_CRITERIA = [
    # ── 下降趋势 ──
    "close < ma200",                                           # 在200日MA下方
    "pct_below_ma200_50d >= 0.6",                              # 过去50天60%时间在MA200下方
    "ma200_slope_60d < -0.02",                                 # 200日MA下行
    "close < 52w_low * 1.10",                                  # 接近52周低点

    # ── 弱势确认 ──
    "rs_score < 30",                                            # RS 弱势
    "ma50 < ma150 AND ma50 < ma200",                            # 均线空头
    "recent_20d_low < prev_20d_low",                           # 更低的低点
]
```

### 3.6 S1S2 过渡期

介于 S1 和 S2 之间：价格已在均线上方、均线多头但**尚未出现突破特征**。

```python
S1S2_CRITERIA = [
    "close > ma150 AND close > ma200",
    "ma150 > ma200",
    "ma200_curr > ma200_past",
    # 但以下至少一条不满足（与S2区别）:
    # - vol_ratio_50 < 1.5（未放量）
    # - vcp_count < 2（无收缩）
    # - rs_score < 70（RS不够强）
]
```

---

## 四、判定优先级

```
S2  >  S3  >  S4  >  S1S2  >  S1
```

```python
if s2_all_met:
    stage = 'S2'
elif s3_all_met:
    stage = 'S3'
elif s4_all_met:
    stage = 'S4'
elif s1s2_all_met:
    stage = 'S1S2'
else:
    stage = 'S1'
```

**理由**：S2 最具交易价值 → S3 风险信号优先提示 → S4 下跌趋势确认 → S1S2 过渡 → S1 兜底。

---

## 五、置信度计算统一公式

置信度 = 基础分 + 调整分，范围 0-99

```python
def calc_confidence(stage_id, met_count, total_criteria, extras):
    base = met_count / total_criteria * 80 + 10
    for key, val in extras.items():
        base += val
    return min(99, max(1, int(base)))
```

| 阶段 | 总分母 | 加分项 |
|------|--------|--------|
| S2 | 12 | RS≥90 +10, 巨量 +5, 极度收缩 +5 |
| S1 | 7 | 无加分 |
| S3 | 7 | 波动率>2.0 +5 |
| S4 | 7 | 无加分 |
| S1S2 | 5 | RS提升 +5 |

---

## 六、所需新增数据源

| 数据 | 来源 | 说明 |
|------|------|------|
| 全市场股票日收益率 | daily_kline | 计算 RS 百分位排名需要所有股票 |
| 大盘指数(沪深300)K线 | daily_kline | 用于 RS 相对线，代码 000300 |
| 成交量数据 | daily_kline | 已有，需加入均量计算 |
| ATR 波动率 | daily_kline | 现有数据可计算 |

---

## 七、S2 阶段示例（荣盛石化 2026-07-17）

```
close=11.33, ma50=10.42, ma150=9.58, ma200=9.31
above_ma50=true, above_ma150=true, above_ma200=true
ma150(9.58) > ma200(9.31): true
ma200_curr(9.31) > ma200_20d_ago(9.20): true
52w_low=7.71, close/52w_low=1.47 >= 1.30: true
52w_high=16.38, close/52w_high=0.69 < 0.75: MISS
vol_ratio_50: depends on volume check
rs_score: N/A (currently not computed)

→ 如果 RS≥70 + 放量突破 → S2 确认
→ 如果 vol_ratio_50<1.5 → S1S2 过渡期
```

---

## 八、实施计划

| 步骤 | 内容 | 涉及文件 |
|------|------|---------|
| 1 | 添加 RS 计算（全市场百分位排名） | `profile.py` + 新增查询或缓存 |
| 2 | 添加 VCP 检测函数 | `profile.py` |
| 3 | 添加均线斜率函数 | `profile.py` |
| 4 | 重构 `compute_stage()` 使用新标准 | `profile.py:704` |
| 5 | 更新置信度计算 | `profile.py:788-800` |
| 6 | 更新 scores 计算对齐新 stage | `profile.py:810` |
| 7 | 测试验证（用荣盛石化/东方盛虹/华峰化学） | 手动测试 |
| 8 | 批量刷新所有 stock profiles | API trigger |

---

*文档版本：v0.1 | 基于 Minervini SEPA + 技术分析量化 | 2026-07-18*
