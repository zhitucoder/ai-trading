#!/home/rick/miniconda3/envs/aitrading/bin/python
"""股价 vs 基金持仓 联动分析绘图（通用版）。

用法:
  python plot_fund_holding_vs_price.py 600150 中国船舶 中国重工合并事件标注(可选)
  python plot_fund_holding_vs_price.py 300502 新易盛

数据：fund_portfolio 表（联合主键已去重）+ daily_kline 股价（不复权）。
产出：analysis/20260816/个股分析/{名称}_股价与基金持仓关系图.png
"""

import sys
import pymysql
from pymysql.cursors import DictCursor
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

DB_CONFIG = dict(host='127.0.0.1', port=3306, user='root',
                 password='aitrading123', database='ai_trading',
                 charset='utf8mb4', cursorclass=DictCursor)

for f in ['/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
          '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc']:
    try:
        fm.fontManager.addfont(f)
        plt.rcParams['font.family'] = fm.FontProperties(fname=f).get_name()
        break
    except Exception:
        pass
plt.rcParams['axes.unicode_minus'] = False

ENDS = ['20210331','20210630','20210930','20211231','20220331','20220630',
        '20220930','20221231','20230331','20230630','20230930','20231231',
        '20240331','20240630','20240930','20241231','20250331','20250630',
        '20250930','20251231','20260331','20260630']
LABELS = ['21Q1','21Q2','21Q3','21Q4','22Q1','22Q2','22Q3','22Q4',
          '23Q1','23Q2','23Q3','23Q4','24Q1','24Q2','24Q3','24Q4',
          '25Q1','25Q2','25Q3','25Q4','26Q1','26Q2']
IS_FULL = [False, True, False, True, False, True, False, True,
           False, True, False, True, False, True, False, True,
           False, True, False, True, False, True]


def is_passive(name):
    n = name or ''
    return any(k in n for k in ['ETF', '指数', '沪深300', '上证50', '中证500',
                                'MSCI', '增强', '联接', 'LOF', '300', '军工指数'])


def main():
    code = sys.argv[1]
    name = sys.argv[2]
    event_note = sys.argv[3] if len(sys.argv) > 3 else None
    suffix = 'SH' if code.startswith('6') else 'SZ'
    symbol = f'{code}.{suffix}'
    out = f'/home/rick/workspace/ai-trading/analysis/20260816/个股分析/{name}_股价与基金持仓关系图.png'

    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute('SELECT ts_code, name FROM fund_basic')
    names = {r['ts_code']: r['name'] for r in cur.fetchall()}

    end_day = {3: 31, 6: 30, 9: 30, 12: 31}
    prices, funds, active, passive = [], [], [], []
    shares, mktvals, intra_highs = [], [], []
    prev_end = '20201231'
    for e in ENDS:
        cur.execute("SELECT close_price FROM daily_kline WHERE stock_code=%s "
                    "AND trade_date<=%s ORDER BY trade_date DESC LIMIT 1", (code, e))
        prices.append(float(cur.fetchone()['close_price']))
        cur.execute("SELECT MAX(high_price) FROM daily_kline WHERE stock_code=%s "
                    "AND trade_date>%s AND trade_date<=%s", (code, prev_end, e))
        intra_highs.append(float(cur.fetchone()['MAX(high_price)']))
        prev_end = e
        cur.execute('''
            SELECT ts_code, ann_date, symbol, amount, mkv FROM (
                SELECT p.ts_code, p.ann_date, p.symbol, p.amount, p.mkv,
                       ROW_NUMBER() OVER (PARTITION BY p.ts_code, p.symbol
                                          ORDER BY p.ann_date DESC) rn
                FROM fund_portfolio p WHERE p.symbol=%s AND p.end_date=%s) t
            WHERE rn=1''', (symbol, e))
        rows = cur.fetchall()
        a = [r for r in rows if not is_passive(names.get(r['ts_code'], ''))]
        p = [r for r in rows if is_passive(names.get(r['ts_code'], ''))]
        funds.append(len(rows))
        active.append(len(a))
        passive.append(len(p))
        shares.append(sum(float(r['amount']) for r in rows) / 1e8)
        mktvals.append(sum(float(r['mkv']) for r in rows) / 1e8)
    conn.close()

    x = list(range(len(ENDS)))
    fig, axes = plt.subplots(3, 1, figsize=(13, 12), sharex=True,
                             gridspec_kw={'height_ratios': [1.1, 1, 1]})

    # 图1：股价（不复权：收盘价 + 盘中高点）
    ax = axes[0]
    ax.plot(x, prices, color='#e23b3b', lw=2.2, marker='o', ms=5, zorder=3,
            label='季度末收盘价(不复权)')
    ax.scatter(x, intra_highs, color='#ff8c1a', marker='^', s=55, zorder=4,
               label='季度内盘中最高(不复权)')
    ax.set_ylabel('股价 (元)', fontsize=12)
    ax.set_title(f'{name}({code}) 股价与基金持仓联动关系 (2021Q1–2026Q2)',
                 fontsize=15, fontweight='bold', pad=12)
    ax.grid(axis='y', ls='--', alpha=0.35)
    for xi, v in zip(x, prices):
        ax.annotate(f'{v:.0f}', (xi, v), textcoords='offset points',
                    xytext=(0, 8), ha='center', fontsize=8, color='#e23b3b')
    ax.legend(loc='upper left', fontsize=9)
    peak_i = max(range(len(ENDS)), key=lambda i: intra_highs[i])
    ax.annotate(f'历史顶点 {intra_highs[peak_i]:.2f}\n({ENDS[peak_i]} 盘中)',
                xy=(peak_i, intra_highs[peak_i]),
                xytext=(peak_i - 2.5, intra_highs[peak_i] + max(prices) * 0.12),
                fontsize=9, color='#ff8c1a', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#ff8c1a', lw=1.4))
    if event_note:
        ax.text(0.02, 0.02, event_note, transform=ax.transAxes,
                fontsize=9, color='#8a6d00',
                bbox=dict(boxstyle='round,pad=0.3', fc='#fff7d6', ec='#f0c040', alpha=0.9))

    # 图2：持仓基金数（区分口径）
    ax = axes[1]
    full_x = [xi for xi, f in enumerate(IS_FULL) if f]
    part_x = [xi for xi, f in enumerate(IS_FULL) if not f]
    ax.plot(full_x, [funds[i] for i in full_x], color='#2b7bd4', lw=2.2,
            marker='s', ms=6, label='半年报/年报(全部持仓)')
    ax.plot(part_x, [funds[i] for i in part_x], color='#2b7bd4', lw=1.4,
            marker='o', ms=6, ls='--', label='季报(仅前十大重仓)', alpha=0.75)
    ax.set_ylabel('持仓基金数 (只)', fontsize=12)
    ax.grid(axis='y', ls='--', alpha=0.35)
    ax.legend(loc='upper left', fontsize=10)
    for xi in full_x:
        ax.annotate(f'{funds[xi]}', (xi, funds[xi]), textcoords='offset points',
                    xytext=(0, 7), ha='center', fontsize=8.5, color='#2b7bd4')

    # 图3：基金持仓股数
    ax = axes[2]
    ax.bar(x, shares, color=['#4a9d5f' if f else '#8fc9a3' for f in IS_FULL],
           width=0.62, label='基金持股总量(亿股)')
    ax.set_ylabel('基金持股 (亿股)', fontsize=12)
    ax.grid(axis='y', ls='--', alpha=0.35)
    for xi, v in zip(x, shares):
        ax.annotate(f'{v:.2f}', (xi, v), textcoords='offset points',
                    xytext=(0, 5), ha='center', fontsize=8.5, color='#2b5f3c')

    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, fontsize=9, rotation=0)
    ax.set_xlabel('报告期', fontsize=12)

    fig.text(0.5, 0.012,
             '注：股价为不复权口径。季报(3/9月)仅披露前十大重仓股，基金数与持股量天然偏低；半年报/年报(6/12月)披露全部持仓。'
             '深绿柱=半年报/年报口径，浅绿柱=季报口径。数据来源：Tushare Pro fund_portfolio + ai_trading 数据库。',
             ha='center', fontsize=8.5, color='#666')

    plt.tight_layout(rect=[0, 0.03, 1, 0.99])
    plt.savefig(out, dpi=130, bbox_inches='tight')
    print('saved:', out)

    print('\n关键节点：')
    for i in [3, 7, 11, 15, 17, 21]:
        print(f'{LABELS[i]} ({ENDS[i]}): 收盘{prices[i]:.2f} 盘中高{intra_highs[i]:.2f} '
              f'基金{funds[i]}只 持股{shares[i]:.2f}亿股 主动{active[i]} 被动{passive[i]}')


if __name__ == '__main__':
    main()
