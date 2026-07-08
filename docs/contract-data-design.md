# 合同负债/合同资产数据获取方案

## 背景

本地通达信导入的 `fin_extended` / `fin_ratios` 表中部分财务字段（索引≥166）因 pytdx 字段索引偏移而损坏，合同负债、合同资产等字段不可信。因此需要从独立的公开数据源重新获取。

## 数据源

- **来源**：东方财富（East Money）财务报表 API
- **接口**：`https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/zcfzbAjaxNew`
- **覆盖范围**：全 A 股（SH/SZ 市场），按报告期（季度）披露
- **数据可靠性**：东方财富的财报数据直接来自上市公司公告，是国内最可靠的公开财报数据源之一

## 表结构

### 表名：`fin_contract_bs`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT PK | 自增主键 |
| `stock_code` | VARCHAR(10) | 股票代码 |
| `report_date` | DATE | 报告日期（季度末） |
| `contract_liab` | DECIMAL(20,2) | **合同负债** — 新收入准则下，已收款但尚未履行履约义务的金额（原预收账款中与收入相关的部分） |
| `contract_asset` | DECIMAL(20,2) | **合同资产** — 已履行部分履约义务但尚需满足其他条件才能收款的权利 |
| `advance_receivables` | DECIMAL(20,2) | **预收款项** — 旧准则下的预收账款，新准则下仅保留非收入相关的预收（如房租预收） |
| `total_assets` | DECIMAL(20,2) | 总资产 |
| `total_liabilities` | DECIMAL(20,2) | 总负债 |
| `source` | VARCHAR(20) | 固定为 `'eastmoney'` |

索引：`(stock_code, report_date)` 唯一覆盖

## 与旧准则的对应关系

2018 年新收入准则（CAS 14 / IFRS 15）实施后，资产负债表科目发生变化：

```
旧准则              → 新准则
────────────────────────────────
预收款项（部分）     → 合同负债（与收入相关的预收款）
预收款项（剩余）     → 预收款项（非收入相关的，如房租）
已完工未结算        → 合同资产
```

对于大部分企业，原"预收款项"中与合同收入相关的部分已转入"合同负债"。2021年后的数据均为新准则口径。

## 数据获取方法

### 脚本位置

`scripts/fetch_contract_data.py`

### 执行流程

对每只股票，脚本执行以下步骤：

```
Step 1: 确定交易所前缀
  SH = 6xxxxx, SZ = 0/3xxxxx
  → symbol = "SH600519" or "SZ000001"

Step 2: 获取公司类型（company_type）
  请求 HTML 页面提取 hidden input `hidctype` 的值
  URL: https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index
  params: {type: "web", code: "sh600150"}

Step 3: 获取可用报告日期列表
  URL: .../zcfzbDateAjaxNew
  params: {companyType, reportDateType: "0", code}
  → 返回该股票历史上所有季度末日期

Step 4: 按报告日期批量获取资产负债表数据
  URL: .../zcfzbAjaxNew
  params: {companyType, reportDateType: "0", reportType: "1", dates: "date1,date2,...", code}
  每次最多传 5 个日期
  响应中包含 CONTRACT_LIAB, CONTRACT_ASSET, ADVANCE_RECEIVABLES 等 319 个字段

Step 5: 写入 MySQL
  INSERT INTO fin_contract_bs (stock_code, report_date, ...)
  ON DUPLICATE KEY UPDATE → 支持断点续传

Step 6: 并发控制
  ThreadPoolExecutor(max_workers=8) 并行处理
  每 100 只股票批量写入一次
```

### 运行方式

```bash
# 全量抓取
python3 scripts/fetch_contract_data.py

# 断点续传（跳过已完成的股票）
python3 scripts/fetch_contract_data.py --resume

# 测试模式（只抓前 N 只）
python3 scripts/fetch_contract_data.py --limit 10
```

### 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--resume` | False | 跳过 `fin_contract_bs` 中已有的股票 |
| `--workers` | 8 | 并行线程数 |
| `--limit` | 0 | 最多处理股票数（0=全部） |

### 性能

- 吞吐量：~240 只股票/分钟（8 线程并发）
- 全量 5,205 只股票：约 21 分钟
- 每只股票约 5 次 API 请求（1 次取公司类型 + 1 次取日期 + 3-4 次取数据）

### 错误处理

- 每次 API 请求有 15 秒超时
- 自动重试 2 次（指数退避：2s → 4s）
- 单只股票失败不影响其他股票
- 支持 `--resume` 参数实现断点续传

## 数据校验

抓取完成后，可通过以下方式校验数据质量：

```sql
-- 基础统计
SELECT COUNT(*) as records, COUNT(DISTINCT stock_code) as stocks
FROM fin_contract_bs;

-- 时间跨度
SELECT MIN(report_date), MAX(report_date) FROM fin_contract_bs;

-- 有合同负债的股票数
SELECT COUNT(DISTINCT stock_code) FROM fin_contract_bs WHERE contract_liab > 0;

-- 行业典型值（白酒行业应有大量合同负债）
SELECT stock_code, report_date, contract_liab
FROM fin_contract_bs
WHERE stock_code IN ('600519','000858','600809')
  AND report_date = '2025-12-31';
```

## 与现有数据的区别

| 对比项 | 旧数据（fin_balance_sheet） | 新数据（fin_contract_bs） |
|--------|---------------------------|--------------------------|
| 来源 | 通达信 pytdx 导入 | 东方财富 API 直取 |
| 合同负债 | ❌ 无此字段 | ✅ 有 `contract_liab` |
| 合同资产 | ❌ 无此字段 | ✅ 有 `contract_asset` |
| 数据可信度 | ⚠️ 部分字段损坏 | ✅ 来自东方财富，与上市公司公告一致 |
| 时间范围 | 2000年-至今 | 2021年-至今（最近21个季度） |
| 更新频率 | 手动导入 | 可随时重新运行脚本 |
