# TODO：港股数据导入（Tushare Pro）—— 待办事项

> 状态：**暂停中**（2026-09-09 写入，未来再处理）
> 相关分支：git HEAD `e969576`（branch: stage/s1，提交前须与用户确认）

---

## 一、任务目标

通过 Tushare Pro 导入港股数据，6 张表：

| 表 | 内容 | 接口文档 |
|---|---|---|
| `hk_basic` | 港股列表（代码/名称/上市日/币种等） | doc_id=253 |
| `hk_daily` | 港股日线行情（OHLC/涨跌幅/成交量额） | doc_id=192 |
| `hk_income` | 港股利润表（科目长表） | doc_id=389 |
| `hk_balancesheet` | 港股资产负债表（科目长表） | doc_id=390 |
| `hk_cashflow` | 港股现金流量表（科目长表） | doc_id=391 |
| `hk_fina_indicator` | 港股财务指标（宽表） | doc_id=388 |

当前跟踪股票：`DEFAULT_CODES = ['00883.HK']`（中国海洋石油）。

**用户指定近期目标：先完成 00883.HK 的历史行情数据下载。**

---

## 二、已完成 ✅

### 代码

1. **`src/scripts/source/import_hk_tushare.py`**（新建，653 行）
   - 6 张表 DDL + `hk_sync_state` 断点表，字段注释 / `update_time` / UNIQUE 约束 / `INSERT ... ON DUPLICATE KEY UPDATE` 幂等写入
   - `parse_codes()`：用户输入 `0883` → `00883.HK`（5 位补零）
   - `update_hk_basic`：按 ts_code 下载列表，幂等
   - `update_hk_daily_his`：历史行情，按 **15 年时间窗**分页（单次接口上限 5000 行），每窗完成写断点 `hk_daily_his_{ts_code}`，**断点续传**，限频时 `wait_on_limit=True` 睡 3600s 重试当前窗
   - `update_hk_daily_inc`：增量行情，按 **trade_date 逐日**下载全港股行情，断点 `hk_daily_last_date`，只保留跟踪股票行
   - `update_hk_financial`：4 个财报接口逐个 try/except，权限错误优雅写入 detail，不中断
   - CLI 参数：`--basic / --daily-his / --daily-inc / --financial / --all / --codes / --start / --end`
   - `py_compile` 通过

2. **`src/app/routers/data_management.py`**（修改）
   - 新增 3 个锁：`_hk_basic_lock` / `_hk_daily_lock` / `_hk_fin_lock`
   - `GET /api/data/hk/status`（含任务运行状态）
   - `POST /api/data/update-hk-basic`
   - `POST /api/data/update-hk-daily`（`mode=inc` 默认，`mode=his` 切历史）
   - `POST /api/data/update-hk-financial`
   - 线程 + 锁模式，后台运行

3. **`web/index.html`**（修改）：原油卡片后新增「港股数据」卡片，3 个独立按钮（港股列表蓝 / 行情·每日黄 / 财报·季度紫），状态行循环 `hkStatus.detail`（rows / max_date / resume_date）

4. **`web/app.js`**（修改）：新增 `hkLoading`(reactive)、`hkResult`、`hkError`、`hkStatus`、`hkDotClass`、`hkStatusText`、`loadHkStatus`、`updateHk(kind)`，全部导出并在 `onMounted` 加载

### 验证

- ✅ `node --check web/app.js` 通过；served app.js 渲染链路核对一致（含 updateHk/hkStatus 等绑定）
- ✅ 3 个 POST 端点 + GET status 均返回预期
- ✅ `hk_basic` 已入库 1 行：`00883.HK 中国海洋石油`（list_date=20010228）
- ✅ 幂等验证：重复跑 `--basic` 不新增（仍 1 行）
- ✅ `docs/数据来源介绍.md` 已补充 2.2 港股章节 + 索引行
- ✅ uvicorn 服务运行：`http://127.0.0.1:9000`

### 服务重启要点（易踩坑）

- `pkill -f "uvicorn src.app.main"` 会匹配到自身 bash 命令行导致自杀 → 用 `pkill -f "uvicorn src[.]app[.]main"` 或先查 pid
- 启动命令必须 setsid + 全重定向（AGENTS.md 规范），bash 工具 120s 超时属表象，进程实际已起：
  ```bash
  setsid /home/rick/miniconda3/envs/aitrading/bin/uvicorn src.app.main:app \
    --host 0.0.0.0 --port 9000 </dev/null >/tmp/uvicorn.log 2>&1 &
  ```

---

## 三、未完成 / 待办 ⏳

### 1. 00883.HK 历史行情下载（核心，受 hk_daily 限频 1次/小时阻塞）

- 状态：后台同步进程曾启动（`--codes 00883.HK --daily-his`）但**因限频未落库**，已 `kill` 停止
- 原因：Tushare `hk_daily` 当前账号 **限频 1次/小时**（错误原文「您访问接口(hk_daily)频率超限(1次/小时)」），00883 约 25 年历史需 2 个 15 年窗 ≈ 至少 2 小时
- 续跑命令（断点续传，需在限频窗口外跑，脚本会自动睡 1h 重试）：
  ```bash
  cd /home/rick/workspace/ai-trading && setsid /home/rick/miniconda3/envs/aitrading/bin/python \
    src/scripts/source/import_hk_tushare.py --codes 00883.HK --daily-his \
    </dev/null >/tmp/hk_daily_his.log 2>&1 &
  ```

### 2. 4 个财报接口无权限（外部阻塞，需用户决策）

- `hk_income / hk_balancesheet / hk_cashflow / hk_fina_indicator`：当前 token **无访问权限**
  （错误原文「您没有接口(hk_xxx)访问权限，权限详情：https://tushare.pro/document/1?doc_id=108」）
- 选项：① 用户在 Tushare 平台为 token 开通权限；② 换高积分 token；③ 改数据源
- 脚本已优雅处理（写入 detail），不阻塞其它接口

### 3. 收尾项（数据落库后）

- [ ] 验证历史行情行数 / 首末日期（`SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM hk_daily`）
- [ ] 验证幂等：二次运行 0 新增
- [ ] 前端页面实际点击 3 个按钮走通（含进度反馈）
- [ ] 与用户确认后提交 git（commit → push origin dev）
- [ ] 「原油与航运」页 canvas 渲染 bug（e969576 存在，非本任务范围，可另立 TODO）

---

## 四、关键口径 / 约束

- **代码格式**：Tushare 港股代码必须 5 位补零 + `.HK`（`00883.HK`）
- **`change` 是 MySQL 保留字**：`hk_daily` 的 DDL 与 INSERT 该列须加反引号（已处理）
- **断点表**：`hk_sync_state`（k/v），键 `hk_daily_his_{ts_code}`（历史进度）、`hk_daily_last_date`（增量日期）、`hk_daily_his_start`（增量开始日）
- **财报表为科目长表**：`(ts_code, end_date, name, ind_name, ind_value)`，主键 `(ts_code, end_date, ind_name)`
- **hk_fina_indicator 为宽表**：主键 `(ts_code, end_date, report_type)`
- **数据库**：`root/aitrading123@127.0.0.1:3306/ai_trading`
- **Tushare token**：`.env` 中 `TUSHARE_TOKEN`

---

## 五、相关文件

| 文件 | 说明 |
|---|---|
| `src/scripts/source/import_hk_tushare.py` | 核心导入脚本（续传/限频自愈逻辑在此） |
| `src/app/routers/data_management.py` | HK 3 端点 + 3 锁 |
| `web/index.html` | 港股卡片 |
| `web/app.js` | 前端 HK 逻辑 |
| `docs/数据来源介绍.md` | 2.2 港股章节 |
| `src/app/main.py` | data_management 路由挂载（第 24 行） |
| `docs/股票画像与筛选系统_当前架构设计.md` | 表可靠性参考 |