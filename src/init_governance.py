#!/home/rick/miniconda3/envs/aitrading/bin/python
"""数据治理平台-初始化脚本（数据资产目录 + 数据血缘）。

职责：
1. 创建 data_catalog_meta（表级元数据，人工可维护）与 data_lineage（血缘边）两张治理表
2. 灌入 32 张业务表的种子元数据（中文名/分类/数据来源/刷新方式/新鲜度探测列）
3. 读取 config/lineage.yaml 灌入表级+字段级血缘边（幂等：全量清空重灌）

运行: python src/init_governance.py
"""
import sys
from pathlib import Path

import pymysql
import yaml
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

BASE_DIR = Path(__file__).resolve().parent.parent
LINEAGE_YAML = BASE_DIR / 'config' / 'lineage.yaml'

CREATE_CATALOG_META = """
CREATE TABLE IF NOT EXISTS data_catalog_meta (
  table_name      VARCHAR(64)  NOT NULL COMMENT '英文表名',
  table_comment   VARCHAR(255) NOT NULL DEFAULT '' COMMENT '中文表名（目录展示名）',
  category        VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '业务分类：行情/财务/板块与股本/预计算分析/用户与日志',
  source          VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '数据来源：通达信/东方财富/系统计算/AI生成/人工/用户',
  refresh_method  VARCHAR(128) NOT NULL DEFAULT '' COMMENT '刷新方式：import_*.py / compute_*.py / 运行期写入',
  latest_date_col VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '新鲜度探测列：trade_date/report_date/updated_at/update_time/computed_at/data_date/started_at',
  description     VARCHAR(512) NOT NULL DEFAULT '' COMMENT '补充说明（口径、已知问题等）',
  PRIMARY KEY (table_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据资产目录-表级元数据（人工维护）'
"""

CREATE_LINEAGE = """
CREATE TABLE IF NOT EXISTS data_lineage (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  source_table  VARCHAR(64) NOT NULL COMMENT '上游表',
  source_column VARCHAR(64) NOT NULL DEFAULT '' COMMENT '上游字段（表级血缘时为空串）',
  target_table  VARCHAR(64) NOT NULL COMMENT '下游表',
  target_column VARCHAR(64) NOT NULL DEFAULT '' COMMENT '下游字段（表级血缘时为空串）',
  transform     VARCHAR(16) NOT NULL DEFAULT 'direct' COMMENT '转换类型：direct/derive/aggregate/join/lookup/self',
  formula       VARCHAR(512) NOT NULL DEFAULT '' COMMENT '计算表达式',
  note          VARCHAR(255) NOT NULL DEFAULT '' COMMENT '口径说明',
  KEY idx_target (target_table, target_column),
  KEY idx_source (source_table, source_column)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据血缘边（表级+字段级）'
"""

# ── 32 张表种子元数据：(英文名, 中文名, 分类, 数据来源, 刷新方式, 新鲜度探测列, 说明)
CATALOG_SEED = [
    # ── 行情 ──
    ('daily_kline', 'A股日K线数据', '行情', '通达信vipdoc', 'src/import_kline.py', 'trade_date',
     '仅股票/ETF/债券，不含指数和板块；约1000万行'),
    ('index_kline', '主要宽基指数日K线', '行情', '通达信', 'src/import_index_kline.py', 'trade_date',
     '上证综指/上证50/沪深300/中证500/中证1000'),
    ('sector_kline', '通达信板块指数日K线', '行情', '通达信', 'src/import_sector_kline.py', 'trade_date',
     '880xxx行业/概念 + 881xxx风格/地区'),
    # ── 财务 ──
    ('fin_income', '利润表', '财务', '通达信gpcw', 'src/import_financial.py', 'report_date',
     'pytdx列索引74-97，可信字段；营收/净利同比用自连接计算'),
    ('fin_balance_sheet', '资产负债表', '财务', '通达信gpcw', 'src/import_financial.py', 'report_date',
     'pytdx列索引8-73，可信字段'),
    ('fin_cash_flow', '现金流量表', '财务', '通达信gpcw', 'src/import_financial.py', 'report_date',
     'pytdx列索引98-118，可信字段'),
    ('fin_ratios', '比率分析', '财务', '通达信gpcw', 'src/import_financial.py', 'report_date',
     '⚠ 索引>=166的字段损坏，派生指标以ads_*为准'),
    ('fin_quarterly', '单季度指标', '财务', '通达信gpcw', 'src/import_financial.py', 'report_date',
     'pytdx列索引230-236，可信字段'),
    ('fin_extended', '扩展指标', '财务', '通达信gpcw', 'src/import_financial.py', 'report_date',
     '⚠ 列索引220-337损坏，需绕开'),
    ('fin_institution', '机构持股', '财务', '通达信gpcw', 'src/import_financial.py', 'report_date',
     'pytdx列索引298-308'),
    ('fin_shareholder', '股本股东', '财务', '通达信gpcw', 'src/import_financial.py', 'report_date',
     'pytdx列索引242-247'),
    ('fin_contract_bs', '合同负债与合同资产数据', '财务', '东方财富', 'scripts/fetch_contract_data.py', 'report_date',
     '东方财富NewFinanceAnalysis接口'),
    ('stock_dividend', '分红信息', '财务', '东方财富', 'scripts/fetch_dividend.py', 'updated_at',
     '含分红预案/实施进度；股息率等展示用'),
    # ── 板块与股本 ──
    ('sectors', '板块定义表', '板块与股本', '通达信BlockMap', 'src/import_sectors.py', '',
     '行业/地区/概念/风格四类板块定义'),
    ('stock_sectors', '股票-板块映射表', '板块与股本', '通达信', 'src/import_sectors.py', '',
     '每只股票所属板块，约8万条'),
    ('stock_shares_dfcf', '股本结构（东方财富F10）', '板块与股本', '东方财富F10', 'src/import_shares_dfcf.py', 'update_time',
     '⚠ 总股本/市值计算一律以此表为准，禁用fin_balance_sheet.share_capital'),
    ('stock_shares', '股本结构（旧表）', '板块与股本', 'em/pytdx/manual', 'src/import_shares.py', 'update_time',
     '⚠ 已废弃：存在缺失(1080只)与错误值，被stock_shares_dfcf取代'),
    # ── 预计算分析 ──
    ('ads_stock_annual', '个股年度财务', '预计算分析', '系统计算(compute_ads.py)', 'src/compute_ads.py', 'report_date',
     '年报口径；core_profit/net_cash等派生指标，损坏行已过滤'),
    ('ads_stock_latest', '个股最新快照', '预计算分析', '系统计算(compute_ads.py)', 'src/compute_ads.py', 'report_date',
     '市值/PE_TTM/股息率/最新营收净利同比；⚠ roe_ttm当前=roe(见compute_ads.py:426)'),
    ('ads_sector_annual', '板块年度汇总', '预计算分析', '系统计算(compute_ads.py)', 'src/compute_ads.py', 'report_date',
     '二级聚合：基于ads_stock_annual按板块汇总'),
    ('ads_sector_latest', '板块最新快照', '预计算分析', '系统计算(compute_ads.py)', 'src/compute_ads.py', 'report_date',
     '二级聚合：基于ads_stock_latest按板块汇总'),
    ('ads_annual_cagr', '年化增长率(CAGR)统计表', '预计算分析', '系统计算(compute_annual_cagr.py)', 'src/compute_annual_cagr.py', 'report_date',
     '3/5/10年营收与净利CAGR'),
    ('ads_sector_finance', '板块财务汇总', '预计算分析', '系统计算(compute_sector_finance.py)', 'src/compute_sector_finance.py', 'report_date',
     '基于单季度财务fin_quarterly汇总'),
    ('sector_prosperity', '板块景气度评分', '预计算分析', '系统计算(compute_prosperity.py)', 'src/compute_prosperity.py', 'computed_at',
     '营收增速/ROE/负债率综合评分'),
    ('zxm_stock_tags', '张新民六维分析标签表', '预计算分析', '系统计算(compute_zxm_tags.py)', 'src/compute_zxm_tags.py', 'data_date',
     '资产质量/利润质量/现金流等六维标签'),
    ('stock_profiles', '股票画像预计算表', '预计算分析', '系统计算(profile_batch.py)', 'src/app/profile_batch.py', 'trade_date',
     '技术面+基本面+标签体系综合画像，约2天一刷'),
    # ── 用户与日志 ──
    ('stocks', '股票基本信息', '用户与日志', '初始导入', '—', '',
     '股票代码→名称/拼音/交易所映射，DDL未入库'),
    ('stock_intro', '公司介绍与定位', '用户与日志', 'AI/模板/人工', 'src/generate_stock_intro.py', 'updated_at',
     '产业链位置/定位标签/介绍文本，三源生成'),
    ('user_watchlist', '自选股', '用户与日志', '用户', '运行期写入', 'added_at', '用户自选股列表'),
    ('backtest_trades', '回测交易记录', '用户与日志', '用户', '运行期写入', 'created_at', '回测保存的交易记录'),
    ('ads_refresh_log', '分析预计算刷新日志', '用户与日志', '系统', '运行期写入(data_management.py)', 'started_at',
     'POST /api/data/update-ads 每次运行一条'),
    ('profile_refresh_log', '画像刷新日志', '用户与日志', '系统', '运行期写入(profile_batch.py)', 'started_at',
     '画像批量刷新每次运行一条'),
]


def get_conn():
    return pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)


def seed_catalog(conn):
    """灌入表级元数据种子（REPLACE 幂等，不会覆盖用户后续编辑的字段值之外的列）。"""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) c FROM data_catalog_meta")
        cnt = cur.fetchone()['c']
        if cnt > 0:
            print(f'  data_catalog_meta 已有 {cnt} 行，跳过种子灌入（保留人工编辑）')
            return
        cur.executemany(
            "INSERT INTO data_catalog_meta (table_name, table_comment, category, source, refresh_method, latest_date_col, description) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)", CATALOG_SEED)
        conn.commit()
        print(f'  data_catalog_meta 灌入 {len(CATALOG_SEED)} 行')


def seed_lineage(conn):
    """读取 config/lineage.yaml，全量清空重灌血缘边。"""
    if not LINEAGE_YAML.exists():
        print(f'  ⚠ 未找到 {LINEAGE_YAML}，跳过血缘灌入')
        return
    data = yaml.safe_load(LINEAGE_YAML.read_text(encoding='utf-8'))
    edges = []          # (source_table, source_column, target_table, target_column, transform, formula, note)
    table_comments = {}
    for t in data['tables']:
        tname = t['name']
        table_comments[tname] = t.get('comment', '')
        # 表级边：upstream -> tname
        for up in t.get('upstream', []):
            edges.append((up, '', tname, '', 'join', '', ''))
        # 字段级边：from[i] -> tname.field
        for f in t.get('fields', []):
            for src in f.get('from', []):
                s_tbl, _, s_col = src.partition('.')
                edges.append((s_tbl, s_col, tname, f['name'], f.get('transform', 'direct'),
                              f.get('formula', ''), f.get('note', '')))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM data_lineage")
        cur.executemany(
            "INSERT INTO data_lineage (source_table, source_column, target_table, target_column, transform, formula, note) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)", edges)
        conn.commit()
    print(f'  data_lineage 灌入 {len(edges)} 条边（表级+字段级）')


def sync_comments_from_schema(conn):
    """将 data_catalog_meta.table_comment 与 information_schema 的表注释对齐。

    场景：compute_ads.py 重算后 DB 注释被重建，或人工改了 DB 注释后，
    血缘/目录页展示的是 data_catalog_meta 里的旧值。执行本函数一次性对齐。
    注意：会覆盖 data_catalog_meta 中未被人工编辑的同名列（当前种子与DB一致）。
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE data_catalog_meta m
            JOIN (SELECT table_name AS table_name, table_comment AS table_comment
                  FROM information_schema.tables WHERE table_schema=%s) t
              ON m.table_name = t.table_name
            SET m.table_comment = t.table_comment
            WHERE t.table_comment IS NOT NULL AND t.table_comment != ''
        """, (DB_CONFIG['database'],))
        conn.commit()
        n = cur.rowcount
    print(f'  表注释同步: {n} 行已对齐 information_schema')


def main():
    import sys
    sync_only = '--sync-comments' in sys.argv
    conn = get_conn()
    try:
        if sync_only:
            sync_comments_from_schema(conn)
            print('同步完成')
            return
        with conn.cursor() as cur:
            cur.execute(CREATE_CATALOG_META)
            cur.execute(CREATE_LINEAGE)
        conn.commit()
        print('治理表就绪: data_catalog_meta / data_lineage')
        seed_catalog(conn)
        seed_lineage(conn)
        sync_comments_from_schema(conn)
        print('初始化完成')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
