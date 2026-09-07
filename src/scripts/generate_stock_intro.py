#!/usr/bin/env python3
"""批量生成公司介绍与定位 → stock_intro 表

用法:
  python src/generate_stock_intro.py --mode template                     # 模板兜底（全覆盖，快）
  python src/generate_stock_intro.py --mode ai --limit 20                # AI 生成（测试20只）
  python src/generate_stock_intro.py --mode ai --codes 002415,600519     # 指定股票
  python src/generate_stock_intro.py --mode ai --workers 8               # AI 全量并发（推荐）
  python src/generate_stock_intro.py --mode ai --workers 8 --resume      # 断点续跑（跳过已有AI记录）

人工维护(source=manual)的记录永不被覆盖。
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.app.database import query
from src.app.strategies.stock_intro import (
    build_template_intro,
    generate_intro_llm,
    update_intro_if_not_manual,
)
from src.app.strategies.profile import generate_profile


def iter_stocks(codes=None, limit=None):
    if codes:
        placeholders = ','.join(['%s'] * len(codes))
        rows = query(f"SELECT stock_code, stock_name FROM stocks WHERE stock_code IN ({placeholders}) "
                     "ORDER BY stock_code", codes)
    else:
        rows = query("SELECT stock_code, stock_name FROM stocks ORDER BY stock_code")
    if limit:
        rows = rows[:limit]
    return rows


def _needs_run(code, only_missing, resume):
    if only_missing:
        has = query("SELECT 1 FROM stock_intro WHERE stock_code = %s AND intro != ''", [code])
        if has:
            return False
    if resume:
        row = query("SELECT source FROM stock_intro WHERE stock_code = %s", [code])
        if row and row[0]['source'] == 'ai':
            return False
    return True


def process_one(mode, code, name):
    if mode == 'template':
        profile = generate_profile(code)
        if not profile or 'error' in profile:
            return code, name, None, '画像失败'
        text, status, label, chain = build_template_intro(profile)
        update_intro_if_not_manual(code, name, text, status, label, chain, source='template')
        return code, name, text, None
    text, status, label, chain, used_fallback = generate_intro_llm(code)
    if text is None:
        return code, name, None, '无画像数据'
    src = 'template' if used_fallback else 'ai'
    update_intro_if_not_manual(code, name, text, status, label, chain, source=src)
    return code, name, text, None


def run(mode, codes, limit, workers=4, only_missing=False, resume=False):
    stocks = iter_stocks(codes, limit)
    todo = [s for s in stocks if _needs_run(s['stock_code'], only_missing, resume)]
    print(f'共 {len(stocks)} 只股票，待处理 {len(todo)}，mode={mode}，workers={workers}', flush=True)
    ok = fail = skipped = 0
    t0 = time.time()

    def _wrap(s):
        code, name = s['stock_code'], s['stock_name']
        try:
            return process_one(mode, code, name)
        except Exception as e:
            return code, name, None, str(e)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_wrap, s): s for s in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            code, name, text, err = fut.result()
            if err:
                fail += 1
                print(f'[{i}/{len(todo)}] {code} {name}: 失败 {err}', flush=True)
            else:
                ok += 1
                print(f'[{i}/{len(todo)}] {code} {name}: {text[:50]}...', flush=True)

    print(f'\n完成: 成功 {ok} / 失败 {fail} / 跳过 {skipped}，耗时 {time.time()-t0:.1f}s', flush=True)


def main():
    p = argparse.ArgumentParser(description='生成公司介绍与定位')
    p.add_argument('--mode', choices=['template', 'ai'], default='template')
    p.add_argument('--codes', help='逗号分隔的股票代码')
    p.add_argument('--limit', type=int, help='最多处理N只')
    p.add_argument('--workers', type=int, default=4, help='并发数')
    p.add_argument('--only-missing', action='store_true', help='只补没有介绍记录的股票')
    p.add_argument('--resume', action='store_true', help='跳过已有ai记录（断点续跑）')
    args = p.parse_args()

    codes = [c.strip() for c in args.codes.split(',')] if args.codes else None
    run(args.mode, codes, args.limit, args.workers, args.only_missing, args.resume)


if __name__ == '__main__':
    main()
