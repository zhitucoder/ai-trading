#!/home/rick/miniconda3/envs/aitrading/bin/python
"""国家队（机构主体）持仓预计算：生成 ads_institution_stock / _change / _sector / _overview。

基于 top10_float_holders（个股前十大流通股东），识别社保/养老/保险/财政部系/国资委系/北向香港中央结算
的持仓全貌与季度变化。持仓市值 = 持股股数 × 当季末收盘价（daily_kline 最近交易日）。

机构归属由 holder_owner 配置表驱动（正则/关键词归一化，避免精确匹配漏数）。

运行: python src/compute_institution_ads.py
"""
import os
import re
import time
import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

# holder_owner 配置表种子数据：pattern(match_type) -> (owner_type, group_name, owner_label, priority)
# priority 越大越优先（用于名称冲突判定）。
OWNER_SEEDS = [
    # ---- 社保基金 ----
    ('社保基金', 'substr', 'shebao', '社保基金', '社保基金', 50),
    ('全国社保', 'substr', 'shebao', '社保基金', '社保基金', 50),
    # ---- 基本养老保险基金（严格，区别于养老金产品）----
    ('基本养老保险基金', 'substr', 'yanglao', '基本养老保险基金', '基本养老保险基金', 60),
    # ---- 保险（用 holder_type + 名称双通道）----
    # 保险的名称识别易误伤，优先放在 holder_type 判断里；这里兜底名称含「保险」且非鹏华养老/国寿养老等发行方，交由代码逻辑处理
    # ---- 财政部系（白名单，精确匹配）----
    ('国开金融有限责任公司', 'substr', 'caizheng', '国开金融', '财政部', 40),
    ('中华人民共和国财政部', 'substr', 'caizheng', '财政部', '财政部', 40),
    ('国家开发投资集团有限公司', 'substr', 'caizheng', '国投集团', '财政部', 40),
    ('中央汇金投资有限责任公司', 'substr', 'caizheng', '中央汇金', '财政部', 40),
    ('中国证券金融股份有限公司', 'substr', 'caizheng', '证金公司', '财政部', 40),
    # ---- 国资委系（白名单）----
    ('国新宏盛投资(北京)有限公司', 'substr', 'guozwei', '国新宏盛', '国资委', 40),
    ('国新控股', 'substr', 'guozwei', '国新控股', '国资委', 40),
    ('国新投资', 'substr', 'guozwei', '国新投资', '国资委', 40),
    ('中国国新控股', 'substr', 'guozwei', '中国国新', '国资委', 40),
    # ---- 北向香港中央结算 ----
    ('香港中央结算', 'substr', 'hk_central', '香港中央结算', '北向·香港中央结算', 10),
    ('HKSCC', 'substr', 'hk_central', '香港中央结算', '北向·香港中央结算', 10),
]

# 保险 holder_type 白名单（按 holder_type 归类为保险）
INSURANCE_HOLDER_TYPES = {'保险投资组合', '金融机构-保险公司', '保险资管产品', '保险公司'}

# 北向名称中的噪声尾缀：归一化时剔除
HK_NORM_RE = re.compile(r'[(（].*?[)）]|\d+$')


def _drop_table(cur, name):
    cur.execute(f"DROP TABLE IF EXISTS {name}")


def seed_holder_owner(cur):
    cur.execute("DROP TABLE IF EXISTS holder_owner")
    cur.execute("""
        CREATE TABLE holder_owner (
          id INT AUTO_INCREMENT PRIMARY KEY,
          pattern      VARCHAR(255) NOT NULL COMMENT '名称关键词/正则',
          match_type   ENUM('regex','exact','substr') DEFAULT 'substr' COMMENT '匹配方式',
          owner_type   VARCHAR(32) NOT NULL COMMENT '归属势力: shebao/yanglao/baoxian/caizheng/guozwei/hk_central',
          group_name   VARCHAR(50) NOT NULL COMMENT '归一化主体名',
          owner_label  VARCHAR(50) NOT NULL COMMENT '展示名',
          priority     INT DEFAULT 0 COMMENT '冲突优先级(大者优先)',
          remark       VARCHAR(255) COMMENT '备注',
          UNIQUE KEY uk_pattern (pattern, group_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='机构主体→归属势力配置(正则/关键词归一化)'
    """)
    for pattern, mtype, otype, gname, label, prio in OWNER_SEEDS:
        cur.execute("""
            INSERT INTO holder_owner (pattern, match_type, owner_type, group_name, owner_label, priority)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (pattern, mtype, otype, gname, label, prio))
    cur.execute("SELECT * FROM holder_owner ORDER BY priority DESC")
    return cur.fetchall()


def build_classifier(rules):
    """把 holder_owner 行编译成可调用的分类函数。
    返回 (owner_type, group_name, owner_label) 或 None。
    """
    def classify(name, holder_type):
        # 先试 holder_type 保险白名单
        if holder_type in INSURANCE_HOLDER_TYPES:
            # 但排除明显的「养老金产品」/「基本养老保险基金」(其 holder_type 常被标成保险类)
            if '养老金产品' not in name and '基本养老保险基金' not in name:
                return ('baoxian', '保险', '保险')
        for r in rules:
            pat = r['pattern']
            if r['match_type'] == 'substr':
                if pat.lower() in name.lower():
                    return (r['owner_type'], r['group_name'], r['owner_label'])
            elif r['match_type'] == 'exact':
                if name.strip() == pat:
                    return (r['owner_type'], r['group_name'], r['owner_label'])
        return None
    return classify


def normalize_hk_name(name):
    """把香港中央结算的 18 种变体归一到 '香港中央结算'。"""
    if '香港中央结算' in name or name.startswith('HKSCC'):
        base = HK_NORM_RE.sub('', name)
        base = base.replace('股份', '').replace('代理', '')
        if base.startswith('HKSCC'):
            return '香港中央结算'
        return '香港中央结算'
    return name


def create_tables(cur):
    for t in ('ads_institution_stock', 'ads_institution_change',
              'ads_institution_sector', 'ads_institution_overview'):
        _drop_table(cur, t)
    cur.execute("""
        CREATE TABLE ads_institution_stock (
          id INT AUTO_INCREMENT PRIMARY KEY,
          owner_type   VARCHAR(32) NOT NULL COMMENT 'shebao/yanglao/baoxian/caizheng/guozwei/hk_central',
          group_name   VARCHAR(50) NOT NULL COMMENT '归一化主体名',
          owner_label  VARCHAR(50) COMMENT '展示名',
          stock_code   VARCHAR(10) NOT NULL,
          stock_name   VARCHAR(50),
          end_date     VARCHAR(8) NOT NULL,
          quarter      CHAR(6),
          holder_cnt   INT COMMENT '该机构下持有此股的产品/组合数',
          total_hold   DECIMAL(20,4) COMMENT '合计持股股数',
          hold_ratio   DECIMAL(10,4) COMMENT '合计占总股本比例(%)',
          hold_float_ratio DECIMAL(10,4) COMMENT '合计占流通比例(%)',
          close_price  DECIMAL(10,2) COMMENT '当季末收盘价',
          hold_mkv     DECIMAL(20,2) COMMENT '持仓市值=total_hold×close_price',
          update_time  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk (owner_type, group_name, stock_code, end_date),
          KEY idx_date (end_date),
          KEY idx_mkv (hold_mkv),
          KEY idx_code (stock_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='机构主体×股票×季度 持仓(归一化合并全变体)'
    """)
    cur.execute("""
        CREATE TABLE ads_institution_change (
          id INT AUTO_INCREMENT PRIMARY KEY,
          owner_type   VARCHAR(32) NOT NULL,
          group_name   VARCHAR(50) NOT NULL,
          stock_code   VARCHAR(10) NOT NULL,
          stock_name   VARCHAR(50),
          end_date     VARCHAR(8) NOT NULL,
          prev_end_date VARCHAR(8) COMMENT '上季度',
          quarter      CHAR(6),
          hold_mkv     DECIMAL(20,2),
          prev_hold_mkv DECIMAL(20,2),
          mkv_change   DECIMAL(20,2) COMMENT '市值变化',
          total_hold   DECIMAL(20,4),
          prev_total_hold DECIMAL(20,4),
          hold_change  DECIMAL(20,4) COMMENT '股数变化',
          hold_change_pct DECIMAL(10,2) COMMENT '股数变化率(%)',
          action       VARCHAR(10) COMMENT '新开仓/增持/减持/清仓/持有',
          update_time  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk (owner_type, group_name, stock_code, end_date),
          KEY idx_date (end_date),
          KEY idx_action (action),
          KEY idx_mkv (mkv_change)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='机构主体×股票 季环比(增减/新开仓/清仓)'
    """)
    cur.execute("""
        CREATE TABLE ads_institution_sector (
          id INT AUTO_INCREMENT PRIMARY KEY,
          owner_type  VARCHAR(32) NOT NULL,
          group_name  VARCHAR(50) NOT NULL,
          sector_type VARCHAR(20) NOT NULL COMMENT 'industry/concept',
          sector_name VARCHAR(50) NOT NULL,
          end_date    VARCHAR(8) NOT NULL,
          stock_cnt   INT,
          hold_mkv    DECIMAL(20,2),
          prev_hold_mkv DECIMAL(20,2) COMMENT '0=上季无数据',
          mkv_change  DECIMAL(20,2),
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk (owner_type, group_name, sector_type, sector_name, end_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='机构主体×板块 持仓流向(行业/概念)'
    """)
    cur.execute("""
        CREATE TABLE ads_institution_overview (
          id INT AUTO_INCREMENT PRIMARY KEY,
          owner_type VARCHAR(32) NOT NULL,
          group_name VARCHAR(50) NOT NULL,
          owner_label VARCHAR(50),
          end_date   VARCHAR(8) NOT NULL,
          quarter    CHAR(6),
          stock_cnt  INT COMMENT '持股公司数',
          holder_cnt INT COMMENT '该机构下全部组合/产品数',
          total_mkv  DECIMAL(20,2) COMMENT '总持仓市值',
          avg_ratio  DECIMAL(10,4) COMMENT '平均持股比例(%)',
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk (owner_type, group_name, end_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='机构主体×季度 总览指标卡'
    """)


def _quarter_label(end_date):
    yy = end_date[2:4]
    m = int(end_date[4:6])
    q = (m - 1) // 3 + 1
    return f'{yy}Q{q}'


_INST_TABLES = ['ads_institution_stock', 'ads_institution_change',
                'ads_institution_sector', 'ads_institution_overview']


def compute(progress_cb=None):
    conn = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    cur = conn.cursor()
    t0 = time.time()

    def log(msg):
        if progress_cb:
            progress_cb(msg)
        else:
            print(msg, flush=True)

    rules = seed_holder_owner(cur)
    classify = build_classifier(rules)
    conn.commit()

    log('Dropping old institution ads tables...')
    create_tables(cur)
    conn.commit()

    # ── 1. 采集并归一化原始持仓 ──
    log('[1/5] loading top10_float_holders (归一化 + 过滤机构) ...')
    cur.execute("""
        SELECT h.ts_code, h.holder_name, h.holder_type, h.hold_amount,
               h.hold_ratio, h.hold_float_ratio, h.end_date
        FROM top10_float_holders h
    """)
    holder_rows = cur.fetchall()
    # 缓存股票名（与上面同一 cursor 分开取，避免结果集被覆盖）
    cur.execute("SELECT stock_code, stock_name FROM stocks")
    name_map = {r['stock_code']: r['stock_name'] for r in cur.fetchall()}

    # 逐行归一化，仅保留可识别机构（返回 None 则非目标机构）
    raw_rows = 0
    norm_rows = []  # (code, gname, otype, label, amount, ratio, f_ratio, end)
    for r in holder_rows:
        raw_rows += 1
        name = r['holder_name'] or ''
        htype = r['holder_type'] or ''
        amt = float(r['hold_amount'] or 0)
        if amt <= 0:
            continue
        # 北向归一化
        norm_name = normalize_hk_name(name)
        cls = classify(norm_name, htype)
        if cls is None:
            if norm_name != name:  # 北向但有噪声，尝试重新归类
                cls = classify(norm_name, htype)
            if cls is None:
                continue
        otype, gname, label = cls
        code = r['ts_code'].split('.')[0] if '.' in r['ts_code'] else r['ts_code']
        norm_rows.append((
            code, gname, otype, label, amt,
            float(r['hold_ratio']) if r['hold_ratio'] is not None else None,
            float(r['hold_float_ratio']) if r['hold_float_ratio'] is not None else None,
            r['end_date'],
        ))
    log(f'  raw rows: {raw_rows}, institution rows: {len(norm_rows)}')

    # ── 2. 聚合 ads_institution_stock（同 机构×股票×季度 合并） ──
    log('[2/5] aggregating ads_institution_stock ...')
    from collections import defaultdict
    agg2 = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    for code, gname, otype, label, amt, ratio, f_ratio, end in norm_rows:
        key = (otype, gname, code, end)
        a = agg2[key]
        a[0] += 1
        a[1] += amt
        a[2] += amt * (ratio if ratio is not None else 0)
        a[3] += amt * (f_ratio if f_ratio is not None else 0)
    # 占比 = 各组合持仓股数加权平均（Σ(股数×比例)/Σ股数）

    # 回填季末价
    log('  loading quarter-end close prices...')
    ends = sorted({key[3] for key in agg2.keys()})
    price_map = {}
    for end in ends:
        cur.execute("""
            SELECT m.stock_code, k.close_price FROM daily_kline k
            JOIN (SELECT stock_code, MAX(trade_date) md FROM daily_kline
                  WHERE trade_date <= %s GROUP BY stock_code) m
              ON k.stock_code = m.stock_code AND k.trade_date = m.md
        """, (end,))
        for rr in cur.fetchall():
            price_map[(rr['stock_code'], end)] = float(rr['close_price'])

    insert_batch = []
    for (otype, gname, code, end), a in agg2.items():
        hcnt, tot, w_ratio, w_fratio = a
        price = price_map.get((code, end))
        mkv = round(tot * price, 2) if price else None
        ratio = round(w_ratio / tot, 4) if tot > 0 else None
        f_ratio = round(w_fratio / tot, 4) if tot > 0 else None
        ratio = min(100.0, max(0.0, ratio)) if ratio is not None else None
        f_ratio = min(100.0, max(0.0, f_ratio)) if f_ratio is not None else None
        insert_batch.append((
            otype, gname, code, name_map.get(code), end, _quarter_label(end),
            hcnt, round(tot, 2), ratio, f_ratio, price, mkv,
        ))
    cur.executemany("""
        INSERT INTO ads_institution_stock
        (owner_type, group_name, stock_code, stock_name, end_date, quarter,
         holder_cnt, total_hold, hold_ratio, hold_float_ratio, close_price, hold_mkv)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, insert_batch)
    conn.commit()
    log(f'  ads_institution_stock rows: {len(insert_batch)}')

    # ── 3. ads_institution_change（季环比 + action） ──
    log('[3/5] computing ads_institution_change ...')
    by_owner_stock = defaultdict(dict)  # (otype,gname,code) -> {end: row}
    for row in insert_batch:
        by_owner_stock[(row[0], row[1], row[2])][row[4]] = row
    change_batch = []
    for (otype, gname, code), qmap in by_owner_stock.items():
        ordered = sorted(qmap.items())
        for i, (end, cur_r) in enumerate(ordered):
            if i == 0:
                continue
            prev_end, prev_r = ordered[i - 1]
            cur_mkv = cur_r[11] or 0
            prev_mkv = prev_r[11] or 0
            cur_hold = cur_r[7]
            prev_hold = prev_r[7]
            hold_chg = cur_hold - prev_hold
            pct = round(hold_chg / prev_hold * 100, 2) if prev_hold and prev_hold > 0 else None
            if prev_hold == 0 or prev_hold is None:
                action = '新开仓'
            elif cur_hold == 0:
                action = '清仓'
            elif hold_chg > 0:
                action = '增持'
            elif hold_chg < 0:
                action = '减持'
            else:
                action = '持有'
            change_batch.append((
                otype, gname, code, cur_r[3], end, prev_end, _quarter_label(end),
                cur_mkv, prev_mkv, round(cur_mkv - prev_mkv, 2),
                cur_hold, prev_hold, hold_chg, pct, action,
            ))
    cur.executemany("""
        INSERT INTO ads_institution_change
        (owner_type, group_name, stock_code, stock_name, end_date, prev_end_date, quarter,
         hold_mkv, prev_hold_mkv, mkv_change,
         total_hold, prev_total_hold, hold_change, hold_change_pct, action)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, change_batch)
    conn.commit()
    log(f'  ads_institution_change rows: {len(change_batch)}')

    # ── 4. ads_institution_sector（板块流向） ──
    log('[4/5] computing ads_institution_sector ...')
    cur.execute("""
        SELECT ss.stock_code, s.sector_name, s.category
        FROM stock_sectors ss JOIN sectors s ON ss.sector_code = s.sector_code
        WHERE s.category IN ('industry','concept')
    """)
    sec_map = defaultdict(set)
    for rr in cur.fetchall():
        sec_map[rr['stock_code']].add((rr['sector_name'], rr['category']))

    sectors_batch = []
    for (otype, gname, code), qmap in by_owner_stock.items():
        for sec_name, sec_type in sec_map.get(code, set()):
            for end, _ in qmap.items():
                sectors_batch.append((otype, gname, code, sec_type, sec_name, end))
    # 聚合成 (otype, gname, sec_type, sec_name, end) 求和
    from collections import defaultdict as dd
    sec_agg = dd(lambda: [0, 0.0])
    for otype, gname, code, sec_type, sec_name, end in sectors_batch:
        key = (otype, gname, sec_type, sec_name, end)
        row = by_owner_stock[(otype, gname, code)].get(end)
        if row and row[11]:
            sec_agg[key][0] += 1
            sec_agg[key][1] += row[11]
    # 季环比
    sec_out = []
    for (otype, gname, sec_type, sec_name, end), (cnt, mkv) in sec_agg.items():
        prev_mkv = 0.0
        # 找上一季度该(机构,板块)市值
        prev_end = None
        for e in sorted(ends):
            if e < end:
                prev_end = e
        if prev_end:
            prev_mkv = sec_agg.get((otype, gname, sec_type, sec_name, prev_end), [0, 0.0])[1]
        sec_out.append((
            otype, gname, sec_type, sec_name, end,
            cnt, round(mkv, 2), round(prev_mkv, 2), round(mkv - prev_mkv, 2),
        ))
    cur.executemany("""
        INSERT INTO ads_institution_sector
        (owner_type, group_name, sector_type, sector_name, end_date,
         stock_cnt, hold_mkv, prev_hold_mkv, mkv_change)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, sec_out)
    conn.commit()
    log(f'  ads_institution_sector rows: {len(sec_out)}')

    # ── 5. ads_institution_overview（季度总览） ──
    log('[5/5] computing ads_institution_overview ...')
    # 每 (otype, gname) 的展示名（来自归一化分类，非股票名）
    label_of = {}
    for code, gname, otype, label, amt, ratio, fr, end in norm_rows:
        label_of.setdefault((otype, gname), label or gname)
    # 每 (otype, gname, end) 聚合：股票集合、组合数、总市值、float_ratio 求和(后求平均)
    from collections import defaultdict as dd
    ov = dd(lambda: {'codes': set(), 'holders': set(), 'mkv': 0.0, 'fr_sum': 0.0, 'fr_cnt': 0})
    for row in insert_batch:
        otype, gname, code = row[0], row[1], row[2]
        end = row[4]
        key = (otype, gname, end)
        o = ov[key]
        o['codes'].add(code)
        if row[6]:
            o['holders'].add(row[6])
        o['mkv'] += (row[11] or 0)
        if row[9] is not None:
            o['fr_sum'] += row[9]
            o['fr_cnt'] += 1
    ov_batch = []
    for (otype, gname, end), o in ov.items():
        avg_ratio = round(o['fr_sum'] / o['fr_cnt'], 4) if o['fr_cnt'] else None
        ov_batch.append((
            otype, gname, label_of.get((otype, gname), gname),
            end, _quarter_label(end), len(o['codes']), len(o['holders']),
            round(o['mkv'], 2), avg_ratio,
        ))
    cur.executemany("""
        INSERT INTO ads_institution_overview
        (owner_type, group_name, owner_label, end_date, quarter,
         stock_cnt, holder_cnt, total_mkv, avg_ratio)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, ov_batch)
    conn.commit()
    log(f'  ads_institution_overview rows: {len(ov_batch)}')

    elapsed = int(time.time() - t0)
    log(f'Done in {elapsed}s')
    conn.close()
    return {
        'stock': len(insert_batch),
        'change': len(change_batch),
        'sector': len(sec_out),
        'overview': len(ov_batch),
        'elapsed_seconds': elapsed,
    }


if __name__ == '__main__':
    print(compute())
