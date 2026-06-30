#!/home/rick/miniconda3/envs/aitrading/bin/python
"""导入通达信专业财务数据（GPCW）到 MySQL，拆分为8张业务表"""

import os
import re
import pymysql
import pandas as pd
from pytdx.crawler.history_financial_crawler import HistoryFinancialCrawler

CW_DIR = '/mnt/d/programs/stock/vipdoc/cw'
DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4', local_infile=True)

# ── 字段映射：col_index → (英文名, 中文名) ──────────────────────
# 来源：https://blog.csdn.net/LuoShunkui/article/details/133693174
FIELD_MAP = {
    1: ('basic_eps', '基本每股收益'),
    2: ('diluted_eps', '扣非每股收益'),
    3: ('undistributed_ps', '每股未分配利润'),
    4: ('bps', '每股净资产'),
    5: ('capital_reserve_ps', '每股资本公积金'),
    6: ('roe', '净资产收益率'),
    7: ('ocf_ps', '每股经营现金流量'),
    # 资产负债表
    8: ('cash', '货币资金'),
    9: ('trading_fa', '交易性金融资产'),
    10: ('notes_receivable', '应收票据'),
    11: ('accounts_receivable', '应收账款'),
    17: ('inventory', '存货'),
    21: ('current_assets', '流动资产合计'),
    25: ('long_term_equity', '长期股权投资'),
    27: ('fixed_assets', '固定资产'),
    33: ('intangible_assets', '无形资产'),
    35: ('goodwill', '商誉'),
    39: ('noncurrent_assets', '非流动资产合计'),
    40: ('total_assets', '资产总计'),
    41: ('short_term_borrow', '短期借款'),
    44: ('accounts_payable', '应付账款'),
    54: ('current_liabilities', '流动负债合计'),
    55: ('long_term_borrow', '长期借款'),
    62: ('noncurrent_liabilities', '非流动负债合计'),
    63: ('total_liabilities', '负债合计'),
    64: ('share_capital', '实收资本(股本)'),
    65: ('capital_surplus', '资本公积'),
    66: ('surplus_reserve', '盈余公积'),
    68: ('retained_profit', '未分配利润'),
    69: ('minority_interest', '少数股东权益'),
    72: ('total_equity', '所有者权益合计'),
    73: ('total_liab_equity', '负债和所有者权益合计'),
    # 利润表
    74: ('operating_revenue', '营业收入'),
    75: ('operating_cost', '营业成本'),
    76: ('business_tax_surcharge', '营业税金及附加'),
    77: ('selling_expense', '销售费用'),
    78: ('admin_expense', '管理费用'),
    80: ('finance_expense', '财务费用'),
    81: ('asset_impairment', '资产减值损失'),
    83: ('investment_income', '投资收益'),
    86: ('operating_profit', '营业利润'),
    88: ('non_op_income', '营业外收入'),
    89: ('non_op_expense', '营业外支出'),
    92: ('total_profit', '利润总额'),
    93: ('income_tax', '所得税'),
    95: ('net_profit', '净利润'),
    96: ('parent_net_profit', '归母净利润'),
    97: ('minority_pnl', '少数股东损益'),
    # 现金流量表
    98: ('sale_cash_received', '销售商品收到的现金'),
    99: ('tax_refund', '收到的税费返还'),
    100: ('other_op_cash_in', '收到其他与经营活动有关的现金'),
    101: ('op_cash_inflow', '经营活动现金流入小计'),
    102: ('buy_goods_paid', '购买商品支付的现金'),
    103: ('employee_paid', '支付给职工的现金'),
    104: ('tax_paid', '支付的各项税费'),
    105: ('other_op_cash_out', '支付其他与经营活动有关的现金'),
    106: ('op_cash_outflow', '经营活动现金流出小计'),
    107: ('op_cash_flow', '经营活动现金流量净额'),
    108: ('invest_cash_inflow', '投资活动现金流入小计'),
    109: ('invest_cash_outflow', '投资活动现金流出小计'),
    110: ('invest_cash_flow', '投资活动现金流量净额'),
    113: ('finance_cash_inflow', '筹资活动现金流入小计'),
    114: ('finance_cash_outflow', '筹资活动现金流出小计'),
    115: ('finance_cash_flow', '筹资活动现金流量净额'),
    118: ('cash_net_change', '现金净增加额'),
    # 比率
    166: ('debt_ratio', '资产负债率'),
    167: ('current_ratio', '流动比率'),
    168: ('quick_ratio', '速动比率'),
    169: ('inventory_turnover', '存货周转率'),
    170: ('receivable_turnover', '应收账款周转率'),
    175: ('gross_margin', '毛利率'),
    176: ('net_margin', '净利率'),
    182: ('revenue_growth_rate', '营业收入增长率'),
    183: ('net_profit_growth_rate', '净利润增长率'),
    186: ('roe_weighted', '加权ROE'),
    187: ('roe_diluted', '摊薄ROE'),
    190: ('op_profit_growth_rate', '营业利润增长率'),
    193: ('total_asset_growth_rate', '总资产增长率'),
    194: ('nav_growth_rate', '净资产增长率'),
    197: ('op_cash_flow_ps', '每股经营现金流'),
    199: ('asset_liability_ratio', '资产负债率'),
    200: ('ebit_per_share', '每股EBIT'),
    # 单季度指标
    230: ('q_revenue', '单季营业收入'),
    231: ('q_operating_profit', '单季营业利润'),
    232: ('q_parent_net_profit', '单季归母净利润'),
    233: ('q_deducted_net_profit', '单季扣非净利润'),
    234: ('q_op_cash_flow', '单季经营活动现金流净额'),
    235: ('q_invest_cash_flow', '单季投资活动现金流净额'),
    236: ('q_finance_cash_flow', '单季筹资活动现金流净额'),
    # 股本股东
    242: ('total_shares', '总股本(万股)'),
    243: ('float_shares', '流通A股(万股)'),
    244: ('holders', '股东人数'),
    245: ('holders_prev', '上期股东人数'),
    247: ('top10_holders_ratio', '十大股东持股比例'),
    284: ('total_share_capital', '总股本'),
    # 机构持股
    298: ('fund_hold_shares', '基金持股(万股)'),
    299: ('fund_hold_ratio', '基金持股比例'),
    300: ('qfii_hold_shares', 'QFII持股(万股)'),
    301: ('social_security_hold', '社保持股(万股)'),
    302: ('insurance_hold', '保险持股(万股)'),
    307: ('northbound_hold', '陆股通持股'),
    308: ('northbound_ratio', '陆股通持股比例'),
    # 扩展指标
    337: ('rd_expense', '研发费用'),
    220: ('ebit', 'EBIT'),
    221: ('ebitda', 'EBITDA'),
    228: ('total_revenue_cagr_3y', '营收3年复合增长率'),
    229: ('net_profit_cagr_3y', '净利润3年复合增长率'),
     223: ('operating_revenue_ttm', '营业收入TTM'),
      224: ('net_profit_ttm', '净利润TTM'),
     225: ('op_cash_flow_ttm', '经营现金流TTM'),
      281: ('pe_ttm_raw', '市盈率(TTM原始)'),
     282: ('market_cap_raw', '总市值原始'),
     283: ('col283_other', '其他'),
}


def make_tables(cursor):
    tables = {
        'fin_balance_sheet': """
            CREATE TABLE IF NOT EXISTS fin_balance_sheet (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
                report_date DATE NOT NULL COMMENT '报告期',
                cash DECIMAL(20,2) COMMENT '货币资金',
                trading_fa DECIMAL(20,2) COMMENT '交易性金融资产',
                accounts_receivable DECIMAL(20,2) COMMENT '应收账款',
                inventory DECIMAL(20,2) COMMENT '存货',
                current_assets DECIMAL(20,2) COMMENT '流动资产合计',
                fixed_assets DECIMAL(20,2) COMMENT '固定资产',
                intangible_assets DECIMAL(20,2) COMMENT '无形资产',
                goodwill DECIMAL(20,2) COMMENT '商誉',
                noncurrent_assets DECIMAL(20,2) COMMENT '非流动资产合计',
                total_assets DECIMAL(20,2) COMMENT '资产总计',
                short_term_borrow DECIMAL(20,2) COMMENT '短期借款',
                accounts_payable DECIMAL(20,2) COMMENT '应付账款',
                current_liabilities DECIMAL(20,2) COMMENT '流动负债合计',
                long_term_borrow DECIMAL(20,2) COMMENT '长期借款',
                noncurrent_liabilities DECIMAL(20,2) COMMENT '非流动负债合计',
                total_liabilities DECIMAL(20,2) COMMENT '负债合计',
                share_capital DECIMAL(20,2) COMMENT '实收资本(股本)',
                capital_surplus DECIMAL(20,2) COMMENT '资本公积',
                surplus_reserve DECIMAL(20,2) COMMENT '盈余公积',
                retained_profit DECIMAL(20,2) COMMENT '未分配利润',
                minority_interest DECIMAL(20,2) COMMENT '少数股东权益',
                total_equity DECIMAL(20,2) COMMENT '所有者权益合计',
                UNIQUE KEY uk (stock_code, report_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='资产负债表'
        """,
        'fin_income': """
            CREATE TABLE IF NOT EXISTS fin_income (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code VARCHAR(10) NOT NULL,
                report_date DATE NOT NULL,
                operating_revenue DECIMAL(20,2) COMMENT '营业收入',
                operating_cost DECIMAL(20,2) COMMENT '营业成本',
                selling_expense DECIMAL(20,2) COMMENT '销售费用',
                admin_expense DECIMAL(20,2) COMMENT '管理费用',
                finance_expense DECIMAL(20,2) COMMENT '财务费用',
                asset_impairment DECIMAL(20,2) COMMENT '资产减值损失',
                investment_income DECIMAL(20,2) COMMENT '投资收益',
                operating_profit DECIMAL(20,2) COMMENT '营业利润',
                non_op_income DECIMAL(20,2) COMMENT '营业外收入',
                total_profit DECIMAL(20,2) COMMENT '利润总额',
                income_tax DECIMAL(20,2) COMMENT '所得税',
                net_profit DECIMAL(20,2) COMMENT '净利润',
                parent_net_profit DECIMAL(20,2) COMMENT '归母净利润',
                minority_pnl DECIMAL(20,2) COMMENT '少数股东损益',
                UNIQUE KEY uk (stock_code, report_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='利润表'
        """,
        'fin_cash_flow': """
            CREATE TABLE IF NOT EXISTS fin_cash_flow (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code VARCHAR(10) NOT NULL,
                report_date DATE NOT NULL,
                op_cash_inflow DECIMAL(20,2) COMMENT '经营活动现金流入',
                op_cash_outflow DECIMAL(20,2) COMMENT '经营活动现金流出',
                op_cash_flow DECIMAL(20,2) COMMENT '经营活动现金流量净额',
                invest_cash_inflow DECIMAL(20,2) COMMENT '投资活动现金流入',
                invest_cash_outflow DECIMAL(20,2) COMMENT '投资活动现金流出',
                invest_cash_flow DECIMAL(20,2) COMMENT '投资活动现金流量净额',
                finance_cash_inflow DECIMAL(20,2) COMMENT '筹资活动现金流入',
                finance_cash_outflow DECIMAL(20,2) COMMENT '筹资活动现金流出',
                finance_cash_flow DECIMAL(20,2) COMMENT '筹资活动现金流量净额',
                cash_net_change DECIMAL(20,2) COMMENT '现金净增加额',
                free_cash_flow DECIMAL(20,2) COMMENT '企业自由现金流',
                UNIQUE KEY uk (stock_code, report_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='现金流量表'
        """,
        'fin_ratios': """
            CREATE TABLE IF NOT EXISTS fin_ratios (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code VARCHAR(10) NOT NULL,
                report_date DATE NOT NULL,
                roe DECIMAL(10,4) COMMENT '净资产收益率',
                roe_weighted DECIMAL(10,4) COMMENT '加权ROE',
                roe_diluted DECIMAL(10,4) COMMENT '摊薄ROE',
                gross_margin DECIMAL(10,4) COMMENT '毛利率',
                net_margin DECIMAL(10,4) COMMENT '净利率',
                debt_ratio DECIMAL(10,4) COMMENT '资产负债率',
                current_ratio DECIMAL(10,4) COMMENT '流动比率',
                quick_ratio DECIMAL(10,4) COMMENT '速动比率',
                inventory_turnover DECIMAL(10,4) COMMENT '存货周转率',
                basic_eps DECIMAL(10,4) COMMENT '基本每股收益',
                diluted_eps DECIMAL(10,4) COMMENT '扣非每股收益',
                bps DECIMAL(10,4) COMMENT '每股净资产',
                revenue_growth_rate DECIMAL(10,4) COMMENT '营业收入增长率',
                net_profit_growth_rate DECIMAL(10,4) COMMENT '净利润增长率',
                op_profit_growth_rate DECIMAL(10,4) COMMENT '营业利润增长率',
                total_asset_growth_rate DECIMAL(10,4) COMMENT '总资产增长率',
                nav_growth_rate DECIMAL(10,4) COMMENT '净资产增长率',
                ebit DECIMAL(20,2) COMMENT 'EBIT',
                ebitda DECIMAL(20,2) COMMENT 'EBITDA',
                revenue_cagr_3y DECIMAL(10,4) COMMENT '营收3年复合增长率',
                net_profit_cagr_3y DECIMAL(10,4) COMMENT '净利润3年复合增长率',
                pe_ttm DECIMAL(10,4) COMMENT '市盈率(TTM)',
                market_cap DECIMAL(20,2) COMMENT '总市值',
                UNIQUE KEY uk (stock_code, report_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='比率分析'
        """,
        'fin_quarterly': """
            CREATE TABLE IF NOT EXISTS fin_quarterly (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code VARCHAR(10) NOT NULL,
                report_date DATE NOT NULL,
                q_revenue DECIMAL(20,2) COMMENT '单季营业收入',
                q_operating_profit DECIMAL(20,2) COMMENT '单季营业利润',
                q_parent_net_profit DECIMAL(20,2) COMMENT '单季归母净利润',
                q_deducted_net_profit DECIMAL(20,2) COMMENT '单季扣非净利润',
                q_op_cash_flow DECIMAL(20,2) COMMENT '单季经营活动现金流净额',
                q_invest_cash_flow DECIMAL(20,2) COMMENT '单季投资活动现金流净额',
                q_finance_cash_flow DECIMAL(20,2) COMMENT '单季筹资活动现金流净额',
                UNIQUE KEY uk (stock_code, report_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='单季度指标'
        """,
        'fin_shareholder': """
            CREATE TABLE IF NOT EXISTS fin_shareholder (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code VARCHAR(10) NOT NULL,
                report_date DATE NOT NULL,
                total_shares DECIMAL(20,2) COMMENT '总股本(万股)',
                float_shares DECIMAL(20,2) COMMENT '流通A股(万股)',
                holders INT COMMENT '股东人数',
                holders_prev INT COMMENT '上期股东人数',
                top10_ratio DECIMAL(10,4) COMMENT '十大股东持股比例',
                UNIQUE KEY uk (stock_code, report_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股本股东'
        """,
        'fin_institution': """
            CREATE TABLE IF NOT EXISTS fin_institution (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code VARCHAR(10) NOT NULL,
                report_date DATE NOT NULL,
                fund_hold_shares DECIMAL(20,2) COMMENT '基金持股(万股)',
                fund_hold_ratio DECIMAL(10,4) COMMENT '基金持股比例',
                qfii_hold_shares DECIMAL(20,2) COMMENT 'QFII持股(万股)',
                social_security_hold DECIMAL(20,2) COMMENT '社保持股(万股)',
                insurance_hold DECIMAL(20,2) COMMENT '保险持股(万股)',
                northbound_hold DECIMAL(20,2) COMMENT '陆股通持股(万股)',
                northbound_ratio DECIMAL(10,4) COMMENT '陆股通持股比例',
                UNIQUE KEY uk (stock_code, report_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='机构持股'
        """,
        'fin_extended': """
            CREATE TABLE IF NOT EXISTS fin_extended (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code VARCHAR(10) NOT NULL,
                report_date DATE NOT NULL,
                rd_expense DECIMAL(20,2) COMMENT '研发费用',
                operating_revenue_ttm DECIMAL(20,2) COMMENT '营业收入TTM',
                net_profit_ttm DECIMAL(20,2) COMMENT '净利润TTM',
                op_cash_flow_ttm DECIMAL(20,2) COMMENT '经营现金流TTM',
                long_term_equity DECIMAL(20,2) COMMENT '长期股权投资',
                capital_reserve_ps DECIMAL(10,4) COMMENT '每股资本公积金',
                free_cash_flow DECIMAL(20,2) COMMENT '自由现金流',
                ocf_ps DECIMAL(10,4) COMMENT '每股经营现金流',
                UNIQUE KEY uk (stock_code, report_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='扩展指标'
        """,
    }
    for name, ddl in tables.items():
        cursor.execute(f"DROP TABLE IF EXISTS {name}")
        cursor.execute(ddl)
        print(f"  created {name}")


def safe(val):
    if val is None:
        return None
    if isinstance(val, float):
        if abs(val) > 1e15 or abs(val) < 1e-15:
            return None
        if 999998 < abs(val) < 1000001:
            return None
    return val


def get_fields(df, field_names):
    """从 DataFrame 提取指定字段列表的列索引映射"""
    col_map = {}
    for en_name, cn_name in field_names:
        # find the col index
        col_idx = next((i for i, c in enumerate(df.columns) if c == en_name), None)
        col_map[en_name] = col_idx
    return col_map


def parse_and_insert(cursor, filepath):
    """解析一个 dat/zip 文件并写入数据库"""
    crawler = HistoryFinancialCrawler()
    with open(filepath, 'rb') as f:
        data = crawler.parse(download_file=f)
    if not data:
        return 0

    df = crawler.to_df(data)
    if df is None or df.empty:
        return 0

    rev_map = {v[0]: k for k, v in FIELD_MAP.items()}

    report_date = data[0][1] if data else None
    if not report_date:
        return 0
    report_date_str = str(report_date)
    rdate = f"{report_date_str[:4]}-{report_date_str[4:6]}-{report_date_str[6:8]}"

    table_cols = {
        'fin_balance_sheet': ['cash', 'trading_fa', 'accounts_receivable',
            'inventory', 'current_assets', 'fixed_assets', 'intangible_assets',
            'goodwill', 'noncurrent_assets', 'total_assets', 'short_term_borrow',
            'accounts_payable', 'current_liabilities', 'long_term_borrow',
            'noncurrent_liabilities', 'total_liabilities', 'share_capital',
            'capital_surplus', 'surplus_reserve', 'retained_profit',
            'minority_interest', 'total_equity'],
        'fin_income': ['operating_revenue', 'operating_cost', 'selling_expense',
            'admin_expense', 'finance_expense', 'asset_impairment',
            'investment_income', 'operating_profit', 'non_op_income',
            'total_profit', 'income_tax', 'net_profit', 'parent_net_profit',
            'minority_pnl'],
        'fin_cash_flow': ['op_cash_inflow', 'op_cash_outflow', 'op_cash_flow',
            'invest_cash_inflow', 'invest_cash_outflow', 'invest_cash_flow',
            'finance_cash_inflow', 'finance_cash_outflow', 'finance_cash_flow',
            'cash_net_change', 'free_cash_flow'],
        'fin_ratios': ['roe', 'roe_weighted', 'roe_diluted', 'gross_margin',
            'net_margin', 'debt_ratio', 'current_ratio', 'quick_ratio',
            'inventory_turnover', 'basic_eps', 'diluted_eps', 'bps',
            'revenue_growth_rate', 'net_profit_growth_rate',
            'op_profit_growth_rate', 'total_asset_growth_rate',
            'nav_growth_rate', 'ebit', 'ebitda', 'revenue_cagr_3y',
            'net_profit_cagr_3y', 'pe_ttm', 'market_cap'],
        'fin_quarterly': ['q_revenue', 'q_operating_profit',
            'q_parent_net_profit', 'q_deducted_net_profit',
            'q_op_cash_flow', 'q_invest_cash_flow', 'q_finance_cash_flow'],
        'fin_shareholder': ['total_shares', 'float_shares', 'holders',
            'holders_prev', 'top10_ratio'],
        'fin_institution': ['fund_hold_shares', 'fund_hold_ratio',
            'qfii_hold_shares', 'social_security_hold', 'insurance_hold',
            'northbound_hold', 'northbound_ratio'],
        'fin_extended': ['rd_expense', 'operating_revenue_ttm',
            'net_profit_ttm', 'op_cash_flow_ttm', 'long_term_equity',
            'capital_reserve_ps', 'free_cash_flow', 'ocf_ps'],
    }

    row_count = 0
    BATCH = 1000

    for table_name, col_names in table_cols.items():
        rows = []
        for code_val, row in df.iterrows():
            vals = {'stock_code': code_val, 'report_date': rdate}
            for cn in col_names:
                col_idx = rev_map.get(cn)
                if col_idx is None:
                    vals[cn] = None
                else:
                    vals[cn] = safe(row.get(f'col{col_idx}'))
            rows.append(vals)

        for i in range(0, len(rows), BATCH):
            batch = rows[i:i + BATCH]
            cols = ['stock_code', 'report_date'] + col_names
            ph = ', '.join([f'%({c})s' for c in cols])
            sql = f"INSERT IGNORE INTO {table_name} ({', '.join(cols)}) VALUES ({ph})"
            cursor.executemany(sql, batch)
            conn.commit()
        row_count += len(rows)

    return row_count


if __name__ == '__main__':
    import sys
    # Get list of dat files sorted by date
    dat_files = sorted([f for f in os.listdir(CW_DIR)
                        if re.match(r'gpcw20\d{6}\.dat$', f) and os.path.getsize(os.path.join(CW_DIR, f)) > 100])

    print(f"Found {len(dat_files)} gpcw dat files")

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("Creating tables...")
    make_tables(cursor)

    total = 0
    for fname in dat_files:
        fpath = os.path.join(CW_DIR, fname)
        date_str = fname[4:12]
        rdate = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        try:
            cnt = parse_and_insert(cursor, fpath)
            total += cnt
            print(f"  {fname} ({rdate}): {cnt} records")
        except Exception as e:
            print(f"  {fname}: ERROR {e}")

    cursor.close()
    conn.close()
    print(f"\nDone! Total records: {total}")
