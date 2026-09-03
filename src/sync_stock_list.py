#!/home/rick/miniconda3/envs/aitrading/bin/python
"""从 Tushare stock_basic 同步 A股上市股票基础列表到 stocks 表。

stocks 表是前端搜索（代码/名称/拼音/首字母）与画像系统的查表，
本脚本用 Tushare 全市场上市列表作为权威来源，配 pypinyin 生成拼音字段。
只做 upsert（不删除），保证既有记录（含退市股）不受影响。

用法：
    python src/sync_stock_list.py
    # 或在数据管理页点击「更新K线」时自动触发
"""

import os
import sys
import unicodedata

from dotenv import load_dotenv
load_dotenv()

import pymysql
from pymysql.cursors import DictCursor
from pypinyin import lazy_pinyin

import tushare as ts

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4', cursorclass=DictCursor)

API_KEY = os.environ.get('TUSHARE_TOKEN', '')
if not API_KEY:
    raise SystemExit('缺少 TUSHARE_TOKEN 环境变量（.env 中配置 TUSHARE_TOKEN=你的tushare token）')

_EXCH_MAP = {'SH': 'sh', 'SZ': 'sz', 'BJ': 'bj'}

# 多音字修正：pypinyin 默认读法在上市公司名称中有误读。
# 字符级：股票名称中的「长」一律读 cháng（长鑫/长电/步长制药等），「都」读 dū（新华都/新国都/南都）。
# 词组级：重药(控股)=chóng yao、会稽(山)=kuai ji、燕京(啤酒)=yan jing。
_PINYIN_CHAR_FIX = {'长': 'chang', '都': 'du'}
_PINYIN_WORD_FIX = {'重药': 'chong yao', '会稽': 'kuai ji', '燕京': 'yan jing'}


def pinyin_fields(name):
    """股票名称 → (全拼, 首字母)。NFKC 归一化处理全角字母/数字。"""
    name = unicodedata.normalize('NFKC', str(name))
    syllables = []
    i, n = 0, len(name)
    while i < n:
        for w in sorted(_PINYIN_WORD_FIX, key=len, reverse=True):
            if name.startswith(w, i):
                syllables.extend(_PINYIN_WORD_FIX[w].split())
                i += len(w)
                break
        else:
            ch = name[i]
            if ch in _PINYIN_CHAR_FIX:
                syllables.append(_PINYIN_CHAR_FIX[ch])
            else:
                syllables.extend(lazy_pinyin(ch))
            i += 1
    full = ''.join(syllables)
    initials = ''.join(s[0] for s in syllables if s and s[0].isascii() and s[0].isalpha()).lower()
    return full, initials


def sync(conn=None):
    """拉取 Tushare 上市列表并 upsert 到 stocks 表，返回同步条数。"""
    pro = ts.pro_api(API_KEY)
    df = pro.stock_basic(exchange='', list_status='L',
                         fields='ts_code,symbol,name,list_date')
    if df is None or df.empty:
        raise RuntimeError('stock_basic 返回空数据')

    close_conn = False
    if conn is None:
        conn = pymysql.connect(**DB_CONFIG)
        close_conn = True
    try:
        cur = conn.cursor()
        rows = []
        for _, r in df.iterrows():
            code = str(r['symbol'])
            exchange = _EXCH_MAP.get(str(r['ts_code']).split('.')[-1], '')
            pinyin, initials = pinyin_fields(r['name'])
            rows.append((code, str(r['name']), pinyin, initials, exchange, 'stock'))

        sql = """INSERT INTO stocks (stock_code, stock_name, pinyin, py_initials, exchange, security_type)
                 VALUES (%s, %s, %s, %s, %s, %s)
                 ON DUPLICATE KEY UPDATE
                   stock_name=VALUES(stock_name), pinyin=VALUES(pinyin),
                   py_initials=VALUES(py_initials), exchange=VALUES(exchange),
                   security_type=VALUES(security_type)"""
        cur.executemany(sql, rows)
        conn.commit()
        return len(rows)
    finally:
        if close_conn:
            conn.close()


if __name__ == '__main__':
    try:
        n = sync()
        print(f'OK: stocks 表已同步 {n} 只上市股票')
    except Exception as e:
        print(f'ERROR: {e}')
        sys.exit(1)