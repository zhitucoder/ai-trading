#!/home/rick/miniconda3/envs/aitrading/bin/python
"""创建画像预计算相关表"""
import pymysql

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

TAG_BOOLEAN_COLS = [
    'tag_ma5_above_ma10', 'tag_ma10_above_ma20', 'tag_ma20_above_ma60',
    'tag_price_above_ma20', 'tag_price_above_ma50', 'tag_price_above_ma150', 'tag_price_above_ma200',
    'tag_rsi_overbought', 'tag_rsi_oversold',
    'tag_volume_surge', 'tag_volume_shrink',
    'tag_boom_growth', 'tag_high_growth', 'tag_steady_growth',
    'tag_revenue_decline', 'tag_profit_decline', 'tag_double_decline',
    'tag_profit_collapse', 'tag_profit_to_loss', 'tag_growth_slowdown',
    'tag_financial_healthy', 'tag_financial_moderate', 'tag_financial_risky',
    'tag_financial_critical', 'tag_financial_insolvent',
    'tag_strong_momentum', 'tag_weak_momentum', 'tag_bullish', 'tag_bearish',
    'tag_volume_price_up', 'tag_volume_price_down', 'tag_break_support',
    'tag_consecutive_profit_3q', 'tag_consecutive_profit_5q', 'tag_consecutive_revenue_3q',
]

TAG_DDL = ', '.join(f'{c} BOOLEAN NOT NULL DEFAULT FALSE COMMENT \'{c}\'' for c in TAG_BOOLEAN_COLS)

STOCK_PROFILES_DDL = f'''
CREATE TABLE IF NOT EXISTS stock_profiles (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
    stock_name VARCHAR(50) NOT NULL COMMENT '股票名称',
    trade_date DATE NOT NULL COMMENT '画像对应的交易日',
    stage_id VARCHAR(20) NOT NULL COMMENT '阶段ID',
    stage_confidence TINYINT UNSIGNED NOT NULL COMMENT '置信度 0-100',
    tech_score TINYINT UNSIGNED NOT NULL COMMENT '技术面评分 0-100',
    fund_score TINYINT UNSIGNED NOT NULL COMMENT '基本面评分 0-100',
    latest_price DECIMAL(10,2) NOT NULL COMMENT '最新收盘价',
    price_change_pct DECIMAL(5,2) NOT NULL COMMENT '当日涨跌幅 %',
    revenue_growth DECIMAL(10,2) COMMENT '营收增长率 %',
    net_profit_growth DECIMAL(10,2) COMMENT '净利润增长率 %',
    debt_ratio DECIMAL(10,4) COMMENT '资产负债率 %',
    {TAG_DDL},
    profile_json JSON NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    data_date DATE NOT NULL,
    fin_report_date DATE COMMENT '财务数据报告期',
    UNIQUE KEY uk_stock_date (stock_code, trade_date),
    KEY idx_trade_date (trade_date),
    KEY idx_stage (stage_id),
    KEY idx_scores (tech_score, fund_score),
    KEY idx_revenue_growth (revenue_growth)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票画像预计算表'
'''

REFRESH_LOG_DDL = '''
CREATE TABLE IF NOT EXISTS profile_refresh_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    status ENUM('running', 'done', 'failed') NOT NULL DEFAULT 'running',
    total_stocks INT NOT NULL DEFAULT 0,
    computed_stocks INT NOT NULL DEFAULT 0,
    error_stocks INT NOT NULL DEFAULT 0,
    trade_date DATE NOT NULL,
    fin_report_date DATE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='画像刷新日志'
'''


def main():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(STOCK_PROFILES_DDL)
    print('Created stock_profiles')
    cursor.execute(REFRESH_LOG_DDL)
    print('Created profile_refresh_log')
    conn.commit()
    cursor.close()
    conn.close()
    print('Done!')


if __name__ == '__main__':
    main()
