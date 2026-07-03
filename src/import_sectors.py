#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从通达信本地文件导入板块信息到 MySQL"""

import os
import re
import pymysql

TDX_DIR = '/mnt/d/programs/stock'
TDX_CACHE = os.path.join(TDX_DIR, 'T0002', 'hq_cache')
BLOCK_MAP_XML = os.path.join(TDX_DIR, 'BlockMap', 'BlockMapXML.dat')

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

CATEGORY_MAP = {
    '2': 'industry',
    '3': 'region',
    '4': 'concept',
    '5': 'style',
}

CATEGORY_CN = {
    'industry': '行业',
    'region': '地区',
    'concept': '概念',
    'style': '风格',
}


def make_tables(cursor):
    cursor.execute("DROP TABLE IF EXISTS sectors")
    cursor.execute("""
        CREATE TABLE sectors (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sector_code VARCHAR(10) NOT NULL COMMENT '板块指数代码',
            sector_name VARCHAR(50) NOT NULL COMMENT '板块名称',
            category VARCHAR(20) NOT NULL COMMENT '板块类型: industry/region/concept/style',
            category_cn VARCHAR(10) NOT NULL COMMENT '板块类型中文',
            sub_category INT COMMENT '子分类',
            level INT DEFAULT 0 COMMENT '层级: 0=一级, 1=二级',
            tdx_industry_code VARCHAR(20) COMMENT '通达信行业代码',
            stock_count INT DEFAULT 0 COMMENT '成分股数量',
            UNIQUE KEY uk_code (sector_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块定义表'
    """)

    cursor.execute("DROP TABLE IF EXISTS stock_sectors")
    cursor.execute("""
        CREATE TABLE stock_sectors (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
            sector_code VARCHAR(10) NOT NULL COMMENT '板块指数代码',
            category VARCHAR(20) NOT NULL COMMENT '板块类型',
            UNIQUE KEY uk_stock_sector (stock_code, sector_code),
            KEY idx_sector (sector_code),
            KEY idx_stock (stock_code),
            KEY idx_category (category)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票-板块映射表'
    """)


def parse_sector_definitions():
    """从 tdxzs.cfg 解析板块定义"""
    filepath = os.path.join(TDX_CACHE, 'tdxzs.cfg')
    sectors = {}
    with open(filepath, 'rb') as f:
        text = f.read().decode('gbk', errors='replace')

    for line in text.strip().split('\n'):
        parts = line.strip().split('|')
        if len(parts) < 6:
            continue
        name, code, cat, sub_cat, level, tdx_code = (
            parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
        )
        category = CATEGORY_MAP.get(cat, 'unknown')
        sectors[code] = {
            'sector_code': code,
            'sector_name': name,
            'category': category,
            'category_cn': CATEGORY_CN.get(category, '未知'),
            'sub_category': int(sub_cat) if sub_cat else None,
            'level': int(level) if level else 0,
            'tdx_industry_code': tdx_code if category == 'industry' else None,
            'stock_count': 0,
        }
    return sectors


def parse_stock_sector_mapping():
    """从 infoharbor_block.dat 解析股票-板块映射（概念/风格/地区）"""
    filepath = os.path.join(TDX_CACHE, 'infoharbor_block.dat')
    mappings = []
    current_sector = None

    with open(filepath, 'rb') as f:
        text = f.read().decode('gbk', errors='replace')

    for line in text.strip().split('\n'):
        line = line.strip()
        if line.startswith('#'):
            header = line[1:].split(',')
            if len(header) >= 3:
                current_sector = header[2]
        elif current_sector and line:
            for item in line.split(','):
                item = item.strip()
                if '#' in item:
                    market, code = item.split('#', 1)
                    code = code.strip()
                    if code and len(code) == 6:
                        mappings.append((code, current_sector))
    return mappings


def parse_industry_stock_mapping(sectors):
    """从 tdxhy.cfg 解析股票-行业板块映射（含父级行业）"""
    filepath = os.path.join(TDX_CACHE, 'tdxhy.cfg')

    tdx_code_to_sector = {}
    for code, s in sectors.items():
        if s['tdx_industry_code']:
            tdx_code_to_sector[s['tdx_industry_code']] = code

    all_tdx_codes = sorted(tdx_code_to_sector.keys())

    def find_parent_sectors(tdx_code):
        result = []
        if tdx_code in tdx_code_to_sector:
            result.append(tdx_code_to_sector[tdx_code])
        for parent_code in all_tdx_codes:
            if parent_code != tdx_code and tdx_code.startswith(parent_code):
                result.append(tdx_code_to_sector[parent_code])
        return result

    mappings = []
    with open(filepath, 'rb') as f:
        text = f.read().decode('gbk', errors='replace')

    for line in text.strip().split('\n'):
        parts = line.strip().split('|')
        if len(parts) < 3:
            continue
        stock_code = parts[1]
        tdx_ind_code = parts[2]
        if stock_code and len(stock_code) == 6 and tdx_ind_code:
            for sector_code in find_parent_sectors(tdx_ind_code):
                mappings.append((stock_code, sector_code))
    return mappings


def main():
    print("解析板块定义...")
    sectors = parse_sector_definitions()
    print(f"  共 {len(sectors)} 个板块")

    print("解析股票-板块映射（概念/风格/地区）...")
    mappings = parse_stock_sector_mapping()
    print(f"  共 {len(mappings)} 条映射")

    print("解析股票-行业板块映射...")
    industry_mappings = parse_industry_stock_mapping(sectors)
    print(f"  共 {len(industry_mappings)} 条映射")

    all_mappings = mappings + industry_mappings

    sector_stock_count = {}
    for stock_code, sector_code in all_mappings:
        sector_stock_count[sector_code] = sector_stock_count.get(sector_code, 0) + 1

    for code, count in sector_stock_count.items():
        if code in sectors:
            sectors[code]['stock_count'] = count

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("创建表...")
    make_tables(cursor)

    print("导入板块定义...")
    sector_rows = []
    for s in sectors.values():
        sector_rows.append((
            s['sector_code'], s['sector_name'], s['category'],
            s['category_cn'], s['sub_category'], s['level'],
            s['tdx_industry_code'], s['stock_count'],
        ))
    cursor.executemany("""
        INSERT INTO sectors
        (sector_code, sector_name, category, category_cn, sub_category, level, tdx_industry_code, stock_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, sector_rows)

    print("导入股票-板块映射...")
    sector_cat_map = {s['sector_code']: s['category'] for s in sectors.values()}
    batch = []
    for stock_code, sector_code in all_mappings:
        cat = sector_cat_map.get(sector_code, 'unknown')
        batch.append((stock_code, sector_code, cat))

    CHUNK = 5000
    for i in range(0, len(batch), CHUNK):
        cursor.executemany("""
            INSERT IGNORE INTO stock_sectors (stock_code, sector_code, category)
            VALUES (%s, %s, %s)
        """, batch[i:i + CHUNK])
        conn.commit()
        print(f"  {min(i + CHUNK, len(batch))}/{len(batch)}")

    conn.commit()
    cursor.close()
    conn.close()

    print("\n统计:")
    for cat in ['industry', 'region', 'concept', 'style']:
        cnt = sum(1 for s in sectors.values() if s['category'] == cat)
        print(f"  {CATEGORY_CN[cat]}板块: {cnt} 个")
    print(f"  股票-板块映射: {len(all_mappings)} 条")
    print("Done!")


if __name__ == '__main__':
    main()
