#!/home/rick/miniconda3/envs/aitrading/bin/python
"""下载上市公司定期报告 PDF（年报 + 一季报/半年报/三季报）。

数据源（--source 可选，逗号分隔）：
  cninfo  巨潮资讯网，全市场（沪深北），无防爬
  szse    深交所官方接口（szse.cn annList），无防爬
  sse     上交所官方接口（query.sse.com.cn 列表 + static.sse.com.cn 下载）
          ⚠ PDF 下载有阿里云盾 acw_sc__v2 JS 挑战：脚本用 node 执行挑战脚本
          获取会话 cookie（1 小时有效），过期自动重新挑战

特性：
- 默认下载 2025 报告期；支持重跑（文件存在 + report_pdf 表双跳过）
- 全局限速（默认 5 秒/请求，--interval 可调），列表+下载共享
- 每股票每报告期一份正式版（排除摘要/英文版，更正版次选）
- 目录：~/workspace/annual_reports/{year}/{period}/{source}/
运行:
  python src/download_reports.py --source sse --period annual,q2   # 上交所年报+半年报
  python src/download_reports.py --source cninfo                   # 巨潮全市场
  python src/download_reports.py --source szse --period annual     # 深交所原生
"""
import argparse
import json
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pymysql
from curl_cffi import requests as cr
from pymysql.cursors import DictCursor

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4')

# 顶层目录：~/workspace/annual_reports（英文名，年报下载总目录）
# 结构：annual_reports/{year}/{period}/{source}/*.pdf
REPORT_DIR = Path.home() / 'workspace' / 'annual_reports'

MAX_RETRIES = 3
REQUEST_TIMEOUT = 20
MIN_INTERVAL = 5.0  # 请求最小间隔(秒)，防封限速

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'

SOURCES = {
    'cninfo': dict(
        label='巨潮资讯(沪深北)',
        list_url='http://www.cninfo.com.cn/new/hisAnnouncement/query',
        pdf_url='http://static.cninfo.com.cn/',
        headers={'User-Agent': UA, 'Referer': 'http://www.cninfo.com.cn/',
                 'Content-Type': 'application/x-www-form-urlencoded'},
        page_size=30,
    ),
    'szse': dict(
        label='深交所官方',
        list_url='http://www.szse.cn/api/disc/announcement/annList?random=0.123456789',
        pdf_url='http://disc.static.szse.cn/download',
        headers={'User-Agent': UA, 'Referer': 'http://www.szse.cn/disclosure/listed/notice/index.html',
                 'Origin': 'http://www.szse.cn', 'Content-Type': 'application/json',
                 'X-Request-Type': 'ajax', 'X-Requested-With': 'XMLHttpRequest'},
        page_size=50,
    ),
    'sse': dict(
        label='上交所官方',
        list_url='https://query.sse.com.cn/security/stock/queryCompanyBulletin.do',
        pdf_url='https://static.sse.com.cn',
        headers={'User-Agent': UA, 'Referer': 'https://www.sse.com.cn/disclosure/listedinfo/regular/'},
        page_size=25,
    ),
}

# 报告期：cninfo 分类 / szse bigCategoryId / sse reportType
PERIODS = {
    'annual': dict(cninfo='category_ndbg_szsh', szse='010301', sse='YEARLY', title='2025年年度报告', label='年报'),
    'q1':     dict(cninfo='category_yjdbg_szsh', szse='010305', sse='QUATER1', title='2025年一季度报告', label='一季报'),
    'q2':     dict(cninfo='category_bndbg_szsh', szse='010303', sse='QUATER2', title='2025年半年度报告', label='半年报'),
    'q3':     dict(cninfo='category_sjdbg_szsh', szse='010307', sse='QUATER3', title='2025年三季度报告', label='三季报'),
}

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS report_pdf (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
  stock_name VARCHAR(50) NOT NULL COMMENT '股票名称',
  report_year SMALLINT NOT NULL COMMENT '报告年度',
  report_period VARCHAR(10) NOT NULL COMMENT 'annual/q1/q2/q3',
  publish_date DATE COMMENT '披露日期',
  file_path VARCHAR(512) NOT NULL COMMENT '本地PDF路径',
  file_size BIGINT COMMENT '文件大小(字节)',
  title VARCHAR(255) NOT NULL COMMENT '公告标题',
  source VARCHAR(20) NOT NULL DEFAULT 'cninfo' COMMENT '数据源: cninfo/szse/sse',
  source_doc_id VARCHAR(64) NOT NULL COMMENT '源公告ID(幂等键)',
  download_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_doc (source, source_doc_id),
  KEY idx_stock_period (stock_code, report_year, report_period)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='上市公司定期报告PDF下载记录'
"""

# 全局限速：所有 HTTP 请求（列表+下载）共享间隔，多线程下也保证不超频
_rate_lock = threading.Lock()
_last_request = [0.0]


def _throttle():
    with _rate_lock:
        wait = MIN_INTERVAL - (time.time() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.time()


def set_interval(seconds):
    global MIN_INTERVAL
    MIN_INTERVAL = max(0.5, seconds)


def get_db():
    return pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)


def _request(method, url, headers=None, **kw):
    for attempt in range(MAX_RETRIES + 1):
        try:
            _throttle()
            return cr.request(method, url, headers=headers or {}, impersonate='chrome',
                              timeout=REQUEST_TIMEOUT, **kw)
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            raise e


def _disclose_dates(period, year):
    """披露期：年报在次年披露，季报在同年披露。"""
    if period == 'annual':
        return (f'{year + 1}-01-01', f'{year + 1}-04-30')
    if period == 'q1':
        return (f'{year}-04-01', f'{year}-04-30')
    if period == 'q2':
        return (f'{year}-07-01', f'{year}-08-31')
    return (f'{year}-10-01', f'{year}-10-31')


# ── 上交所 acw_sc__v2 挑战：node 执行挑战脚本获取会话 cookie ──
_NODE_MOCK = """import { readFileSync } from 'fs';
const script = process.argv[1];
let cookieVal = '';
globalThis.document = {
    set cookie(v) { cookieVal = v; },
    get cookie() { return cookieVal; },
    location: { reload: () => {} },
};
globalThis.window = globalThis;
globalThis.location = { host: '%s', hostname: '%s' };
globalThis.atob = s => Buffer.from(s, 'base64').toString('binary');
globalThis.btoa = s => Buffer.from(s, 'binary').toString('base64');
eval(script);
process.stdout.write(cookieVal);
"""


def _solve_sse_challenge(challenge_html):
    """从挑战页提取 JS 并用 node 执行，返回 acw_sc__v2 cookie 值或 None。"""
    m = re.search(r'<script>(.*?)</script>', challenge_html, re.S)
    if not m or 'acw_sc__v2' not in m.group(1):
        return None
    js = m.group(1)
    try:
        proc = subprocess.run(['node', '-e', _NODE_MOCK % ('static.sse.com.cn', 'static.sse.com.cn'), js],
                              capture_output=True, text=True, timeout=30)
        cm = re.search(r'acw_sc__v2=([0-9a-fA-F]+)', proc.stdout or '')
        return cm.group(1) if cm else None
    except Exception:
        return None


class SseSession:
    """上交所下载会话：挑战 cookie 自动获取/续期。"""

    def __init__(self):
        self.cookie = None
        self._lock = threading.Lock()

    def ensure_cookie(self, probe_url=None):
        with self._lock:
            if self.cookie:
                return self.cookie
            try:
                probe = probe_url or (SOURCES['sse']['pdf_url']
                                      + '/disclosure/listedinfo/announcement/c/new/probe.pdf')
                r = _request('GET', probe, headers=SOURCES['sse']['headers'])
                if r.status_code == 200 and 'acw_sc__v2' in r.text:
                    self.cookie = _solve_sse_challenge(r.text)
            except Exception:
                pass
            if not self.cookie:
                raise RuntimeError('上交所挑战cookie获取失败')
            return self.cookie


def list_sse(period, year, max_pages):
    cfg = PERIODS[period]
    dates = _disclose_dates(period, year)
    src = SOURCES['sse']
    out, page = [], 1
    while page <= max_pages:
        try:
            params = {
                'jsonCallBack': f'jsonpCallback{int(time.time() * 1000) % 100000000}',
                'isPagination': 'true',
                'pageHelp.pageSize': src['page_size'], 'pageHelp.pageNo': page,
                'pageHelp.beginPage': page, 'pageHelp.cacheSize': 1, 'pageHelp.endPage': 1,
                'productId': '', 'securityType': '0101,120100,020100,020200,120200',
                'reportType2': 'DQBG', 'reportType': cfg['sse'],
                'beginDate': dates[0], 'endDate': dates[1],
                '_': str(int(time.time() * 1000)),
            }
            r = _request('GET', src['list_url'], headers=src['headers'], params=params)
            body = r.text
            j = body[body.index('{'):body.rindex('}') + 1]
            data = json.loads(j)
        except Exception as e:
            print(f'  ⚠ sse 列表失败 page={page}: {e}', flush=True)
            return out
        ph = data.get('pageHelp') or {}
        rows = ph.get('data') or []
        out.extend(rows)
        total = ph.get('total') or 0
        if page * src['page_size'] >= total or not rows:
            break
        page += 1
    return out


def list_cninfo(period, year, max_pages):
    cfg = PERIODS[period]
    dates = _disclose_dates(period, year)
    src = SOURCES['cninfo']
    out, page = [], 1
    while page <= max_pages:
        try:
            r = _request('POST', src['list_url'], headers=src['headers'], data={
                'pageNum': page, 'pageSize': src['page_size'], 'column': 'szse',
                'tabName': 'fulltext', 'plate': '', 'stock': '', 'searchkey': '',
                'secid': '', 'category': cfg['cninfo'], 'trade': '',
                'seDate': f'{dates[0]}~{dates[1]}', 'sortName': '', 'sortType': '', 'isHLtitle': 'true',
            })
            data = r.json()
        except Exception as e:
            print(f'  ⚠ cninfo 列表失败 page={page}: {e}', flush=True)
            return out
        anns = data.get('announcements') or []
        out.extend(anns)
        total = data.get('totalAnnouncement') or 0
        if page * src['page_size'] >= total or not anns:
            break
        page += 1
    return out


def list_szse(period, year, max_pages):
    cfg = PERIODS[period]
    dates = _disclose_dates(period, year)
    src = SOURCES['szse']
    out, page = [], 1
    while page <= max_pages:
        try:
            r = _request('POST', src['list_url'], headers=src['headers'], json={
                'seDate': [dates[0], dates[1]], 'channelCode': ['listedNotice_disc'],
                'bigCategoryId': [cfg['szse']], 'pageSize': src['page_size'], 'pageNum': page,
            })
            data = r.json()
        except Exception as e:
            print(f'  ⚠ szse 列表失败 page={page}: {e}', flush=True)
            return out
        anns = data.get('data') or []
        out.extend(anns)
        total = data.get('announceCount') or 0
        if page * src['page_size'] >= total or not anns:
            break
        page += 1
    return out


def normalize(ann, source):
    """把各源公告统一为内部结构。"""
    if source == 'szse':
        return {
            'code': ann['secCode'][0], 'name': ann['secName'][0],
            'title': ann['title'], 'doc_id': str(ann['annId']),
            'url': SOURCES['szse']['pdf_url'] + ann['attachPath'],
            'publish_ts': int(time.mktime(time.strptime(ann['publishTime'], '%Y-%m-%d %H:%M:%S')) * 1000),
            'size': ann.get('attachSize') or 0,
        }
    if source == 'sse':
        return {
            'code': ann['SECURITY_CODE'], 'name': ann['SECURITY_NAME'],
            'title': ann['TITLE'], 'doc_id': ann['URL'],
            'url': SOURCES['sse']['pdf_url'] + ann['URL'],
            'publish_ts': int(time.mktime(time.strptime(ann['ADDDATE'], '%Y-%m-%d %H:%M:%S')) * 1000),
            'size': 0,
        }
    return {
        'code': ann['secCode'], 'name': ann['secName'],
        'title': ann['announcementTitle'], 'doc_id': str(ann['announcementId']),
        'url': SOURCES['cninfo']['pdf_url'] + ann['adjunctUrl'],
        'publish_ts': ann['announcementTime'],
        'size': 0,
    }


def _title_key(period):
    """标题匹配正则：期别关键词（兼容"一季度报告/第一季度报告"写法）。"""
    if period == 'q1':
        main = r'2025年(第)?一季(度)?(报)?告'
    elif period == 'q3':
        main = r'2025年(第)?三季(度)?(报)?告'
    else:
        main = re.escape(PERIODS[period]['title'])
    return re.compile(main)


def _is_formal(title):
    return not re.search(r'摘要|英文版|摘[要]', title)


def _title_of(ann, source):
    return ann['TITLE'] if source == 'sse' else (ann['title'] if source == 'szse' else ann['announcementTitle'])


def _code_of(ann, source):
    return ann['SECURITY_CODE'] if source == 'sse' else (ann['secCode'][0] if source == 'szse' else ann['secCode'])


def _time_of(ann, source):
    if source == 'cninfo':
        return ann['announcementTime']
    if source == 'sse':
        return ann['ADDDATE']
    return ann['publishTime']


def select_targets(source, period, year, force, existing_docs, existing_files, max_pages=999):
    """拉列表 → 标题过滤 → 每股票每期一份 → 跳过已下载，返回 [(code,name,ann,path)]。"""
    cfg = PERIODS[period]
    print(f'[{SOURCES[source]["label"]}·{cfg["label"]}] 拉取公告列表...', flush=True)
    if source == 'sse':
        anns = list_sse(period, year, max_pages)
    elif source == 'szse':
        anns = list_szse(period, year, max_pages)
    else:
        anns = list_cninfo(period, year, max_pages)
    print(f'[{SOURCES[source]["label"]}·{cfg["label"]}] 共 {len(anns)} 条公告', flush=True)

    rx = _title_key(period)
    matched = [a for a in anns if rx.search(_title_of(a, source) or '')]
    print(f'[{SOURCES[source]["label"]}·{cfg["label"]}] 标题匹配 {len(matched)} 条', flush=True)

    by_stock = {}
    for a in matched:
        by_stock.setdefault(_code_of(a, source), []).append(a)
    targets = []
    for code, items in by_stock.items():
        formal = [a for a in items if _is_formal(_title_of(a, source))
                  and not re.search(r'更正|修订|取消|补充', _title_of(a, source))]
        pool = formal or items
        pool.sort(key=lambda a: _time_of(a, source))
        best = pool[0]
        ann = normalize(best, source)
        if not force and (source, ann['doc_id']) in existing_docs:
            continue
        name = (ann['name'] or code).replace('/', '_').replace('\\', '_')
        path = REPORT_DIR / str(year) / period / source / f'{code}_{name}.pdf'
        if not force and path in existing_files:
            continue
        ann['_src'] = source
        targets.append((code, name, ann, str(path)))
    print(f'[{SOURCES[source]["label"]}·{cfg["label"]}] 待下载 {len(targets)} 个', flush=True)
    return targets


_sse_session = SseSession()


def download_one(args):
    code, name, ann, path = args
    try:
        headers = {'User-Agent': UA}
        if ann.get('_src') == 'sse':
            headers['Cookie'] = f'acw_sc__v2={_sse_session.ensure_cookie(ann["url"])}'
            headers['Referer'] = 'https://www.sse.com.cn/'
        r = _request('GET', ann['url'], headers=headers)
        r.raise_for_status()
        if len(r.content) < 1000 or 'text/html' in r.headers.get('Content-Type', ''):
            return code, name, None, '空文件/非PDF'
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)
        return code, name, ann, p.stat().st_size
    except Exception as e:
        return code, name, None, str(e)[:120]


def main():
    parser = argparse.ArgumentParser(description='下载沪深上市公司定期报告PDF')
    parser.add_argument('--year', type=int, default=2025, help='报告年度（默认2025）')
    parser.add_argument('--period', default='annual,q1,q2,q3',
                        help='报告期: annual/q1/q2/q3，逗号分隔（默认全部）')
    parser.add_argument('--source', default='cninfo', help='数据源: cninfo/szse/sse，逗号分隔（默认cninfo）')
    parser.add_argument('--force', action='store_true', help='强制重下（默认跳过已下载）')
    parser.add_argument('--workers', type=int, default=1, help='并发数（默认1）')
    parser.add_argument('--interval', type=float, default=5.0, help='请求最小间隔秒（默认5，防封）')
    parser.add_argument('--limit', type=int, default=0, help='每个报告期最多下载N个（调试用）')
    args = parser.parse_args()
    set_interval(args.interval)

    sources = [s.strip() for s in args.source.split(',') if s.strip() in SOURCES]
    if not sources:
        print('--source 无效，可选: cninfo/szse/sse')
        sys.exit(1)

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(CREATE_TABLE)
        db.commit()
        with db.cursor() as cur:
            cur.execute("SELECT source, source_doc_id FROM report_pdf")
            existing_docs = {(r['source'], r['source_doc_id']) for r in cur.fetchall()}
    finally:
        db.close()
    existing_files = {p for p in REPORT_DIR.rglob('*.pdf')} if REPORT_DIR.exists() else set()
    print(f'重跑跳过: DB记录 {len(existing_docs)} 条, 已有文件 {len(existing_files)} 个')

    periods = [p.strip() for p in args.period.split(',') if p.strip() in PERIODS]
    if not periods:
        print('--period 无效，可选: annual/q1/q2/q3')
        sys.exit(1)

    ok = fail = 0
    for source in sources:
        for period in periods:
            max_pages = 999
            if args.limit:
                max_pages = max(2, args.limit // SOURCES[source]['page_size'] + 2)
            targets = select_targets(source, period, args.year, args.force, existing_docs, existing_files,
                                     max_pages=max_pages)
            if args.limit:
                targets = targets[:args.limit]
            if not targets:
                continue
            t0 = time.time()
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futs = {pool.submit(download_one, t): t for t in targets}
                for i, fut in enumerate(as_completed(futs), 1):
                    code, name, ann, res = fut.result()
                    if isinstance(res, int):
                        ok += 1
                        if ann:
                            try:
                                db2 = get_db()
                                try:
                                    with db2.cursor() as cur:
                                        cur.execute(
                                            "INSERT IGNORE INTO report_pdf "
                                            "(stock_code, stock_name, report_year, report_period, publish_date, file_path, file_size, title, source, source_doc_id) "
                                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                            (code, name, args.year, period,
                                             time.strftime('%Y-%m-%d', time.localtime(ann['publish_ts'] / 1000)),
                                             str(REPORT_DIR / str(args.year) / period / source / f'{code}_{name}.pdf'),
                                             res, ann['title'], source, ann['doc_id']))
                                    db2.commit()
                                finally:
                                    db2.close()
                            except Exception as e:
                                print(f'  ⚠ DB记录失败 {code}: {e}', flush=True)
                    else:
                        fail += 1
                        print(f'  ✗ {code} {name}: {res}', flush=True)
                    if i % 50 == 0 or i == len(targets):
                        print(f'  [{source}·{period}] 进度 {i}/{len(targets)}  成功{ok} 失败{fail}  耗时{int(time.time()-t0)}s', flush=True)
    print(f'完成：成功 {ok} 个，失败 {fail} 个')
    print(f'保存目录: {REPORT_DIR}')


if __name__ == '__main__':
    main()
