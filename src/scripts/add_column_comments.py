#!/home/rick/miniconda3/envs/aitrading/bin/python
"""数据治理-补全数据库表/列中文注释（幂等，可重复执行）。

对缺注释的表(8张)与缺注释的列(~130个)，从 information_schema 动态读取定义，
生成 ALTER TABLE ... MODIFY COLUMN ... COMMENT '...' 执行。
不修改类型/默认值/自增/键等任何其他属性，仅追加 COMMENT。

运行: python src/add_column_comments.py
"""
import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

# ── 缺注释的表 → 中文表名 ──
TABLE_COMMENTS = {
    'ads_refresh_log': '分析预计算刷新日志（每POST /api/data/update-ads一条）',
    'ads_sector_annual': '板块年度财务汇总（按板块×年报聚合ads_stock_annual）',
    'ads_sector_finance': '板块财务汇总（基于单季度财务fin_quarterly）',
    'ads_sector_latest': '板块最新快照（按板块聚合ads_stock_latest）',
    'ads_stock_annual': '个股年度财务（年报口径派生指标，core_profit/net_cash等）',
    'ads_stock_latest': '个股最新快照（市值/PE_TTM/股息率/最新财务同比）',
    'backtest_trades': '回测交易记录（用户自定义买卖交易）',
    'sector_prosperity': '板块景气度评分（营收增速/ROE/负债率综合）',
}

# ── 缺注释的列 → 中文注释（key: 表.列） ──
COLUMN_COMMENTS = {
    # ── 通用 id 列 ──
    'ads_annual_cagr.id': '自增ID',
    'ads_refresh_log.id': '自增ID',
    'ads_sector_annual.id': '自增ID',
    'ads_stock_annual.id': '自增ID',
    'ads_sector_finance.id': '自增ID',
    'backtest_trades.id': '自增ID',
    'daily_kline.id': '自增ID',
    'data_lineage.id': '自增ID',
    'fin_balance_sheet.id': '自增ID',
    'fin_cash_flow.id': '自增ID',
    'fin_contract_bs.id': '自增ID',
    'fin_extended.id': '自增ID',
    'fin_income.id': '自增ID',
    'fin_institution.id': '自增ID',
    'fin_quarterly.id': '自增ID',
    'fin_ratios.id': '自增ID',
    'fin_shareholder.id': '自增ID',
    'index_kline.id': '自增ID',
    'profile_refresh_log.id': '自增ID',
    'sector_kline.id': '自增ID',
    'sectors.id': '自增ID',
    'stock_dividend.id': '自增ID',
    'stock_sectors.id': '自增ID',
    'stock_shares.id': '自增ID',
    'stock_shares_dfcf.id': '自增ID',
    'stock_profiles.id': '自增ID',
    'user_watchlist.id': '自增ID',
    'zxm_stock_tags.id': '自增ID',
    # ── 财务通用 stock_code/report_date ──
    'fin_income.stock_code': '股票代码',
    'fin_income.report_date': '报告期（YYYY-MM-DD，年报为12-31）',
    'fin_balance_sheet.stock_code': '股票代码',
    'fin_balance_sheet.report_date': '报告期',
    'fin_cash_flow.stock_code': '股票代码',
    'fin_cash_flow.report_date': '报告期',
    'fin_ratios.stock_code': '股票代码',
    'fin_ratios.report_date': '报告期',
    'fin_quarterly.stock_code': '股票代码',
    'fin_quarterly.report_date': '报告期',
    'fin_extended.stock_code': '股票代码',
    'fin_extended.report_date': '报告期',
    'fin_institution.stock_code': '股票代码',
    'fin_institution.report_date': '报告期',
    'fin_shareholder.stock_code': '股票代码',
    'fin_shareholder.report_date': '报告期',
    'fin_contract_bs.stock_code': '股票代码',
    'fin_contract_bs.report_date': '报告期',
    'fin_contract_bs.source': '数据来源: 东方财富',
    'stock_dividend.stock_code': '股票代码',
    'stock_dividend.dividend_yield': '股息率(%)',
    'stock_dividend.payout_ratio': '派息比率(%)',
    'stock_dividend.source': '数据来源: 东方财富',
    'stock_dividend.updated_at': '更新时间',
    # ── ads_annual_cagr ──
    'ads_annual_cagr.stock_code': '股票代码',
    'ads_annual_cagr.updated_at': '更新时间',
    # ── ads_refresh_log ──
    'ads_refresh_log.status': '运行状态: running/done/error',
    'ads_refresh_log.total_stocks': '总股票数',
    'ads_refresh_log.computed_stocks': '已计算股票数',
    'ads_refresh_log.error_stocks': '出错股票数',
    'ads_refresh_log.started_at': '开始时间',
    'ads_refresh_log.finished_at': '结束时间',
    'ads_refresh_log.message': '运行摘要',
    # ── ads_stock_annual ──
    'ads_stock_annual.stock_code': '股票代码',
    'ads_stock_annual.report_date': '年报报告期（仅12-31）',
    'ads_stock_annual.operating_revenue': '营业总收入(元)',
    'ads_stock_annual.operating_cost': '营业总成本(元)',
    'ads_stock_annual.gross_profit': '毛利润(元)=营收-成本',
    'ads_stock_annual.gross_margin': '毛利率(%)=(营收-成本)/营收×100',
    'ads_stock_annual.selling_expense': '销售费用(元)',
    'ads_stock_annual.admin_expense': '管理费用(元)',
    'ads_stock_annual.finance_expense': '财务费用(元)',
    'ads_stock_annual.core_profit': '核心利润(元)=营收-成本-销售费用-管理费用',
    'ads_stock_annual.core_margin': '核心利润率(%)=核心利润/营收×100',
    'ads_stock_annual.parent_net_profit': '归母净利润(元)',
    'ads_stock_annual.net_margin': '净利率(%)=归母净利/营收×100',
    'ads_stock_annual.total_assets': '总资产(元)',
    'ads_stock_annual.total_liabilities': '总负债(元)',
    'ads_stock_annual.total_equity': '净资产(元)',
    'ads_stock_annual.debt_ratio': '资产负债率(%)=总负债/总资产×100',
    'ads_stock_annual.cash': '货币资金(元)',
    'ads_stock_annual.trading_fa': '交易性金融资产(元)',
    'ads_stock_annual.cash_plus_tfa': '现金+交易性金融资产(元)',
    'ads_stock_annual.short_borrow': '短期借款(元)',
    'ads_stock_annual.long_borrow': '长期借款(元)',
    'ads_stock_annual.interest_debt': '有息负债(元)=短借+长借',
    'ads_stock_annual.net_cash': '净现金(元)=现金+交易性金融资产-短借-长借',
    'ads_stock_annual.accounts_receivable': '应收账款(元)',
    'ads_stock_annual.inventory': '存货(元)',
    'ads_stock_annual.fixed_assets': '固定资产(元)',
    'ads_stock_annual.goodwill': '商誉(元)',
    'ads_stock_annual.op_cash_flow': '经营现金流(元)',
    'ads_stock_annual.net_cash_ratio': '净现比=经营现金流/归母净利',
    'ads_stock_annual.roe': 'ROE(%)=归母净利/净资产×100',
    'ads_stock_annual.revenue_yoy': '营收同比(%)',
    'ads_stock_annual.profit_yoy': '净利同比(%)',
    # ── ads_stock_latest ──
    'ads_stock_latest.stock_code': '股票代码',
    'ads_stock_latest.stock_name': '股票名称',
    'ads_stock_latest.report_date': '最新财务报告期',
    'ads_stock_latest.annual_report_date': '最新年报日期',
    'ads_stock_latest.latest_price': '最新收盘价(元)',
    'ads_stock_latest.total_shares': '总股本(股, 来自stock_shares_dfcf)',
    'ads_stock_latest.market_cap': '总市值(亿元)=最新价×总股本/1e8',
    'ads_stock_latest.pe_ttm': '市盈率TTM=市值/TTM归母净利',
    'ads_stock_latest.dividend_yield': '股息率(%)',
    'ads_stock_latest.revenue': '最新报告期营收(元)',
    'ads_stock_latest.profit': '最新报告期归母净利(元)',
    'ads_stock_latest.revenue_yoy': '营收同比(%)',
    'ads_stock_latest.profit_yoy': '净利同比(%)',
    'ads_stock_latest.revenue_annual': '最新年报营收(元)',
    'ads_stock_latest.profit_annual': '最新年报归母净利(元)',
    'ads_stock_latest.gross_margin': '毛利率(%)=年报口径',
    'ads_stock_latest.core_margin': '核心利润率(%)=年报口径',
    'ads_stock_latest.net_margin': '净利率(%)=年报口径',
    'ads_stock_latest.roe': 'ROE(%)=年报口径',
    'ads_stock_latest.roe_ttm': 'ROE-TTM(⚠当前实现=roe,见compute_ads.py:426)',
    'ads_stock_latest.debt_ratio': '资产负债率(%)=年报口径',
    'ads_stock_latest.net_cash': '净现金(元)=年报口径',
    'ads_stock_latest.net_cash_ratio': '净现比=年报口径',
    'ads_stock_latest.op_cash_flow': '经营现金流(元)=年报口径',
    # ── ads_sector_annual ──
    'ads_sector_annual.sector_code': '板块代码',
    'ads_sector_annual.category': '板块分类(行业/地区/概念/风格)',
    'ads_sector_annual.sector_name': '板块名称',
    'ads_sector_annual.report_date': '年报报告期',
    'ads_sector_annual.stock_count': '成分股数',
    'ads_sector_annual.total_revenue': '板块总营收(元)',
    'ads_sector_annual.total_net_profit': '板块总净利(元)',
    'ads_sector_annual.avg_gross_margin': '平均毛利率(%)',
    'ads_sector_annual.avg_roe': '平均ROE(%)',
    'ads_sector_annual.avg_debt_ratio': '平均资产负债率(%)',
    'ads_sector_annual.revenue_yoy': '板块营收同比(%)',
    'ads_sector_annual.profit_yoy': '板块净利同比(%)',
    # ── ads_sector_latest ──
    'ads_sector_latest.sector_code': '板块代码',
    'ads_sector_latest.category': '板块分类(行业/地区/概念/风格)',
    'ads_sector_latest.sector_name': '板块名称',
    'ads_sector_latest.report_date': '最新年报日期(板块内MAX)',
    'ads_sector_latest.stock_count': '成分股数',
    'ads_sector_latest.total_market_cap': '板块总市值(亿元)',
    'ads_sector_latest.total_revenue': '板块总营收(元)',
    'ads_sector_latest.total_net_profit': '板块总净利(元)',
    'ads_sector_latest.revenue_yoy': '板块营收同比(%)',
    'ads_sector_latest.profit_yoy': '板块净利同比(%)',
    'ads_sector_latest.avg_gross_margin': '平均毛利率(%)',
    'ads_sector_latest.avg_roe': '平均ROE(%)',
    'ads_sector_latest.avg_debt_ratio': '平均资产负债率(%)',
    # ── ads_sector_finance ──
    'ads_sector_finance.sector_code': '板块代码',
    'ads_sector_finance.report_date': '报告期',
    'ads_sector_finance.total_revenue': '板块总营收(元)',
    'ads_sector_finance.total_net_profit': '板块总净利(元)',
    'ads_sector_finance.revenue_growth': '营收同比增长(%)',
    'ads_sector_finance.net_profit_growth': '净利同比增长(%)',
    # ── backtest_trades ──
    'backtest_trades.stock_code': '股票代码',
    'backtest_trades.trade_date': '交易日期',
    'backtest_trades.direction': '方向: buy买入/sell卖出',
    'backtest_trades.price': '成交价(元)',
    'backtest_trades.volume': '成交量(股)',
    'backtest_trades.created_at': '创建时间',
    # ── index_kline ──
    'index_kline.open_price': '开盘价',
    'index_kline.high_price': '最高价',
    'index_kline.low_price': '最低价',
    'index_kline.close_price': '收盘价',
    'index_kline.volume': '成交量(手)',
    'index_kline.amount': '成交额(元)',
    # ── profile_refresh_log ──
    'profile_refresh_log.started_at': '开始时间',
    'profile_refresh_log.finished_at': '结束时间',
    'profile_refresh_log.status': '状态: running/done/failed',
    'profile_refresh_log.total_stocks': '总股票数',
    'profile_refresh_log.computed_stocks': '已计算数',
    'profile_refresh_log.error_stocks': '出错数',
    'profile_refresh_log.trade_date': '画像对应交易日',
    'profile_refresh_log.fin_report_date': '财务数据报告期',
    # ── sector_kline / sectors / stock_sectors / stock_shares* ──
    'sector_kline.id': '自增ID',
    'sectors.id': '自增ID',
    'stock_sectors.id': '自增ID',
    'stock_shares.id': '自增ID',
    'stock_shares_dfcf.id': '自增ID',
    'stocks.pinyin': '拼音全拼',
    'stocks.py_initials': '拼音首字母',
    # ── sector_prosperity ──
    'sector_prosperity.sector_code': '板块代码',
    'sector_prosperity.avg_rev_growth': '平均营收增速(%)',
    'sector_prosperity.avg_roe': '平均ROE(%)',
    'sector_prosperity.avg_debt_ratio': '平均资产负债率(%)',
    'sector_prosperity.score': '综合景气评分',
    'sector_prosperity.level': '景气级别: high/medium/low',
    'sector_prosperity.computed_at': '计算时间',
    # ── stock_intro ──
    'stock_intro.stock_code': '股票代码',
    'stock_intro.stock_name': '股票名称',
    'stock_intro.intro': '公司介绍文本',
    'stock_intro.positioning_status': '定位状态: unknown/...',
    'stock_intro.positioning_label': '定位标签',
    'stock_intro.source': '来源: ai/template/manual',
    'stock_intro.updated_at': '更新时间',
    # ── stock_profiles ──
    'stock_profiles.dividend_yield': '股息率(%)',
    'stock_profiles.pe_ttm': '市盈率TTM',
    'stock_profiles.peg': 'PEG估值',
    'stock_profiles.roe': 'ROE(%)',
    'stock_profiles.roe_ttm': 'ROE-TTM(%)',
    'stock_profiles.gross_margin': '毛利率(%)',
    'stock_profiles.prev_year_revenue': '上年营收(元)',
    'stock_profiles.rev_cagr_3y': '3年营收CAGR(%)',
    'stock_profiles.rev_cagr_5y': '5年营收CAGR(%)',
    'stock_profiles.rev_cagr_10y': '10年营收CAGR(%)',
    'stock_profiles.profit_cagr_3y': '3年净利CAGR(%)',
    'stock_profiles.profit_cagr_5y': '5年净利CAGR(%)',
    'stock_profiles.profit_cagr_10y': '10年净利CAGR(%)',
    'stock_profiles.price_cagr_3y': '3年股价CAGR(%，前复权)',
    'stock_profiles.divergence': '业绩股价背离=3年净利CAGR-3年股价CAGR(百分点)',
    'stock_profiles.profile_json': '画像完整JSON',
    'stock_profiles.updated_at': '更新时间',
    'stock_profiles.data_date': '画像数据日期',
    'stock_profiles.tag_annual_rev_growth_1y': '年度营收增长标签-近1年',
    'stock_profiles.tag_annual_rev_growth_2y': '年度营收增长标签-近2年',
    'stock_profiles.tag_annual_rev_growth_3y': '年度营收增长标签-近3年',
    'stock_profiles.tag_annual_rev_growth_4y': '年度营收增长标签-近4年',
    'stock_profiles.tag_annual_profit_growth_1y': '年度净利增长标签-近1年',
    'stock_profiles.tag_annual_profit_growth_2y': '年度净利增长标签-近2年',
    'stock_profiles.tag_annual_profit_growth_3y': '年度净利增长标签-近3年',
    'stock_profiles.tag_annual_profit_growth_4y': '年度净利增长标签-近4年',
    'stock_profiles.tag_annual_gm_improve_1y': '毛利率改善标签-近1年',
    'stock_profiles.tag_annual_gm_improve_2y': '毛利率改善标签-近2年',
    'stock_profiles.tag_annual_gm_improve_3y': '毛利率改善标签-近3年',
    'stock_profiles.tag_annual_gm_improve_4y': '毛利率改善标签-近4年',
    'stock_profiles.tag_tenbagger': '十倍股标签',
    'stock_profiles.tag_annual_rev_growth_5y': '年度营收增长标签-近5年',
    'stock_profiles.tag_annual_rev_growth_6y': '年度营收增长标签-近6年',
    'stock_profiles.tag_annual_rev_growth_7y': '年度营收增长标签-近7年',
    'stock_profiles.tag_annual_rev_growth_8y': '年度营收增长标签-近8年',
    'stock_profiles.tag_annual_rev_growth_9y': '年度营收增长标签-近9年',
    'stock_profiles.tag_annual_profit_growth_5y': '年度净利增长标签-近5年',
    'stock_profiles.tag_annual_profit_growth_6y': '年度净利增长标签-近6年',
    'stock_profiles.tag_annual_profit_growth_7y': '年度净利增长标签-近7年',
    'stock_profiles.tag_annual_profit_growth_8y': '年度净利增长标签-近8年',
    'stock_profiles.tag_annual_profit_growth_9y': '年度净利增长标签-近9年',
    'stock_profiles.has_dividend_this_year': '今年是否分红',
    'stock_profiles.consecutive_dividend_years': '连续分红年数',
    'stock_profiles.has_mid_year_dividend': '是否有中期分红',
    # ── user_watchlist ──
    'user_watchlist.stock_code': '股票代码',
    'user_watchlist.stock_name': '股票名称',
    'user_watchlist.added_at': '添加时间',
    # ── zxm_stock_tags ──
    'zxm_stock_tags.stock_code': '股票代码',
    'zxm_stock_tags.stock_name': '股票名称',
    'zxm_stock_tags.report_date': '财务报告期',
    'zxm_stock_tags.data_date': '标签计算日期',
    'zxm_stock_tags.asset_type': '资产类型(重资产/轻资产等)',
    'zxm_stock_tags.asset_weight': '资产比重',
    'zxm_stock_tags.cash_status': '现金储备状态',
    'zxm_stock_tags.inventory_risk': '存货风险',
    'zxm_stock_tags.contract_liab_tag': '合同负债标签',
    'zxm_stock_tags.hematopoiesis': '造血能力',
    'zxm_stock_tags.hematopoiesis_ratio': '造血比率(%)',
    'zxm_stock_tags.leverage': '杠杆水平',
    'zxm_stock_tags.debt_ratio': '资产负债率(%)',
    'zxm_stock_tags.margin_level': '毛利水平',
    'zxm_stock_tags.core_profit_margin': '核心利润率(%)',
    'zxm_stock_tags.profit_source': '利润来源',
    'zxm_stock_tags.minority_ratio': '少数股东损益占比(%)',
    'zxm_stock_tags.profit_status': '盈利状态',
    'zxm_stock_tags.match_fa_rev': '固定资产与营收匹配',
    'zxm_stock_tags.match_fa_rev_ratio': '固定资产/营收比率',
    'zxm_stock_tags.match_rev_profit': '营收与利润匹配',
    'zxm_stock_tags.match_rev_profit_ratio': '营收利润匹配比率',
    'zxm_stock_tags.match_profit_ocf': '利润与经营现金流匹配',
    'zxm_stock_tags.match_profit_ocf_ratio': '净现比',
    'zxm_stock_tags.cashflow_type': '现金流类型',
    'zxm_stock_tags.ocf_to_np': '经营现金流/净利',
    'zxm_stock_tags.fcf_status': '自由现金流状态',
    'zxm_stock_tags.growth_rate': '增长率水平',
    'zxm_stock_tags.growth_quality': '增长质量',
    'zxm_stock_tags.risk_flags': '风险标记(逗号分隔)',
    'zxm_stock_tags.overall_rating': '综合评级',
    'zxm_stock_tags.pattern_label': '模式标签',
    'zxm_stock_tags.framework_version': '框架版本',
    'zxm_stock_tags.created_at': '创建时间',
    'zxm_stock_tags.updated_at': '更新时间',
    # ── data_lineage 治理表 ──
    'data_lineage.id': '自增ID',
}


def _column_def(col):
    """从 information_schema 列定义重建 MODIFY 子句（含 COMMENT 占位）。"""
    parts = [f"`{col['column_name']}` {col['column_type']}"]
    if col['is_nullable'] == 'NO':
        parts.append('NOT NULL')
    else:
        parts.append('NULL')
    if col['column_default'] is not None:
        d = col['column_default']
        if d == 'CURRENT_TIMESTAMP':
            parts.append('DEFAULT CURRENT_TIMESTAMP')
        else:
            parts.append(f"DEFAULT '{d}'")
    extra = col['extra'] or ''
    if 'auto_increment' in extra:
        parts.append('AUTO_INCREMENT')
    elif 'on update CURRENT_TIMESTAMP' in extra:
        parts.append('ON UPDATE CURRENT_TIMESTAMP')
    parts.append("COMMENT '%s'")
    return ' '.join(parts)


def main():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    try:
        with conn.cursor() as cur:
            # 1. 补表注释
            for tbl, cmt in TABLE_COMMENTS.items():
                cur.execute(
                    "SELECT COUNT(*) c FROM information_schema.tables "
                    "WHERE table_schema=%s AND table_name=%s AND (table_comment IS NULL OR table_comment='')",
                    (DB_CONFIG['database'], tbl))
                if cur.fetchone()['c']:
                    cur.execute(f"ALTER TABLE `{tbl}` COMMENT = %s", (cmt,))
                    print(f'  [表] {tbl} → {cmt}')

            # 2. 补列注释（仅对当前缺注释的列，动态读取定义）
            cur.execute(
                "SELECT table_name AS table_name, column_name AS column_name, "
                "column_type AS column_type, is_nullable AS is_nullable, "
                "column_default AS column_default, extra AS extra "
                "FROM information_schema.columns "
                "WHERE table_schema=%s AND (column_comment IS NULL OR column_comment='')",
                (DB_CONFIG['database'],))
            missing = cur.fetchall()

            n = 0
            for col in missing:
                key = f"{col['table_name']}.{col['column_name']}"
                cmt = COLUMN_COMMENTS.get(key)
                if cmt is None:
                    print(f'  [跳过] 未配置注释: {key}')
                    continue
                ddl = _column_def(col)
                sql = f"ALTER TABLE `{col['table_name']}` MODIFY COLUMN {ddl}" % cmt.replace("'", "''")
                cur.execute(sql)
                n += 1
            conn.commit()
            print(f'完成：补表注释 {len(TABLE_COMMENTS)} 张，补列注释 {n} 个')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
