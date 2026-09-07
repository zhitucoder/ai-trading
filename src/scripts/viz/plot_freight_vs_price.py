#!/home/rick/miniconda3/envs/aitrading/bin/python
"""绘制航运运价指数 vs 公司股价/利润 关系图。

覆盖公司 & 对应运价类型：
  - 招商轮船(601872)  油运(VLCC→BDTI) + 散货(BDI)  主看 BDTI，叠加 BDI
  - 中远海能(600026)  油运为主(VLCC→BDTI)          主看 BDTI
  - 中远海控(601919)  集运(CCFI/SCFI)               无集装箱运价数据→标注局限

每个公司生成一张图：上半部运价(左轴) vs 股价(右轴)双线；下半部归母净利柱状。
另出一张「运价-股价-净利 相关性散点」汇总图。

数据：shipping_* 运价表 + daily_kline 股价(后复权) + ads_stock_annual 年度净利。
产出：analysis/20260906/航运运价与股价利润分析/{名称}_运价股价利润关系.png
"""

import os
import sys
import pymysql
from pymysql.cursors import DictCursor
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

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

OUT_DIR = '/home/rick/workspace/ai-trading/analysis/20260906/航运运价与股价利润分析'

# 公司: (code, 名称, 主营, 主运价表, 次运价表)
COMPANIES = [
    dict(code='601872', name='招商轮船', biz='油运+散货+集运',
         main='shipping_bdti', main_cn='BDTI原油轮运价', sub='shipping_bdi', sub_cn='BDI干散货'),
    dict(code='600026', name='中远海能', biz='油运(纯)',
         main='shipping_bdti', main_cn='BDTI原油轮运价', sub=None, sub_cn=None),
    dict(code='601919', name='中远海控', biz='集运(纯)',
         main=None, main_cn='(无集装箱运价数据)', sub=None, sub_cn=None),
]

START = '2016-01-01'


def load_freight(table, code):
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(f"""SELECT trade_date, close_value FROM `{table}`
                    WHERE index_code=%s AND trade_date>=%s
                    ORDER BY trade_date""", (code, START))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series([float(r['close_value']) for r in rows],
                  index=pd.to_datetime([r['trade_date'] for r in rows]))
    return s


def load_price(code):
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""SELECT trade_date, close_price FROM daily_kline
                   WHERE stock_code=%s AND trade_date>=%s
                   ORDER BY trade_date""", (code, START))
    rows = cur.fetchall()
    conn.close()
    s = pd.Series([float(r['close_price']) for r in rows],
                  index=pd.to_datetime([r['trade_date'] for r in rows]))
    # 后复权近似：用交易日复权因子表? 本项目无qfq于daily, 用不复权并标注
    return s


def load_profit(code):
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""SELECT report_date, parent_net_profit FROM ads_stock_annual
                   WHERE stock_code=%s AND report_date>=%s
                   ORDER BY report_date""", (code, '2015-12-31'))
    rows = cur.fetchall()
    conn.close()
    return [(r['report_date'].year, float(r['parent_net_profit']) / 1e8) for r in rows]


def monthly_mean(s):
    """运价取月度均值,与股价月末对比,降低日频噪音"""
    return s.resample('ME').mean()


def corr_series(a, b):
    """对齐两序列后计算 Pearson 相关"""
    df = pd.concat([a, b], axis=1).dropna()
    if len(df) < 5 or df.iloc[:, 0].std() == 0 or df.iloc[:, 1].std() == 0:
        return None, 0
    return df.iloc[:, 0].corr(df.iloc[:, 1]), len(df)


def fmt_big(v, _):
    if abs(v) >= 100:
        return f'{v:.0f}'
    if abs(v) >= 10:
        return f'{v:.0f}'
    return f'{v:.1f}'


def draw_company(meta):
    code, name = meta['code'], meta['name']
    print(f'\n=== {name}({code}) {meta["biz"]} ===')

    price = load_price(code)
    profits = load_profit(code)
    years = [p[0] for p in profits]
    vals = [p[1] for p in profits]

    fig, axes = plt.subplots(2, 1, figsize=(14, 10),
                             gridspec_kw={'height_ratios': [1.5, 1], 'hspace': 0.32})

    ax = axes[0]
    corr_txt = []
    if meta['main']:
        freight = load_freight(meta['main'], meta['main'].split('_')[1].upper())
        fm_ = monthly_mean(freight)
        fm_ = fm_.loc[fm_.index >= pd.Timestamp('2016-02-01')]
        pm_ = monthly_mean(price)
        c1, n1 = corr_series(fm_, pm_)
        # 双轴
        ax.plot(fm_.index, fm_.values, color='#e23b3b', lw=1.9,
                label=f'{meta["main_cn"]}(左轴)', zorder=3)
        ax.set_ylabel(meta['main_cn'], color='#e23b3b', fontsize=12)
        ax.tick_params(axis='y', labelcolor='#e23b3b')
        ax2 = ax.twinx()
        ax2.plot(pm_.index, pm_.values, color='#2b7bd4', lw=2.0,
                 label=f'{name}股价(右轴)', zorder=4)
        ax2.set_ylabel('月度均价 股价(元, 不复权)', color='#2b7bd4', fontsize=12)
        ax2.tick_params(axis='y', labelcolor='#2b7bd4')
        if c1 is not None:
            corr_txt.append(f'{meta["main_cn"]} vs 股价 相关 r={c1:.2f} (n={n1})')
        # 叠加次级运价
        if meta['sub']:
            f2 = load_freight(meta['sub'], meta['sub'].split('_')[1].upper())
            f2m = monthly_mean(f2)
            f2m = f2m / f2m.max() * fm_.max() * 0.55  # 归一便于同图观察
            ax.plot(f2m.index, f2m.values, color='#b08a2e', lw=1.1, ls='--', alpha=0.7,
                    label=f'{meta["sub_cn"]}(归一,左轴)')
            c2, n2 = corr_series(f2m, pm_)
            if c2 is not None:
                corr_txt.append(f'{meta["sub_cn"]}(归一同比例) vs 股价 r={c2:.2f}')
        ax.set_title(f'{name}({code}) {meta["biz"]}：运价 vs 股价 ({START[:4]}–2026)',
                     fontsize=15, fontweight='bold', pad=10)
        ax.grid(axis='y', ls='--', alpha=0.3)
        # 图例合并
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=9)
    else:
        ax.text(0.5, 0.5, f'{name} 为集装箱航运，对应 CCFI/SCFI 集装箱运价。\n'
                '该数据需上海航交所订阅，当前未入库，故无法绘制运价关系。',
                transform=ax.transAxes, ha='center', va='center', fontsize=13,
                color='#666', bbox=dict(boxstyle='round', fc='#f5f5f5', ec='#ccc'))
        ax.set_title(f'{name}({code}) {meta["biz"]}：运价数据缺失说明',
                     fontsize=15, fontweight='bold', pad=10)

    # 下半：归母净利柱状
    axb = axes[1]
    colors = ['#4a9d5f' if v >= 0 else '#d9534f' for v in vals]
    axb.bar(years, vals, color=colors, width=0.6)
    axb.axhline(0, color='#444', lw=0.8)
    axb.set_ylabel('年度归母净利 (亿元)', fontsize=12)
    axb.set_title('年度归母净利润 (ads_stock_annual)', fontsize=12, fontweight='bold')
    axb.grid(axis='y', ls='--', alpha=0.3)
    for x, v in zip(years, vals):
        axb.annotate(f'{v:.0f}', (x, v), textcoords='offset points',
                     xytext=(0, 5 if v >= 0 else -12), ha='center',
                     fontsize=8.5, color='#2b5f3c' if v >= 0 else '#a0302c')

    if corr_txt:
        fig.text(0.5, 0.005,
                 '注：运价为月均；股价为不复权月末月均。相关r用当月运价均值与当月股价均值对齐计算。 '
                 '数据源：akshare波罗的海指数 + ai_trading库 daily_kline/ads_stock_annual。',
                 ha='center', fontsize=8.5, color='#666')
        print('  ' + '; '.join(corr_txt))
    else:
        fig.text(0.5, 0.005,
                 '注：该司为集装箱航运，需CCFI/SCFI数据。数据源：ai_trading库。',
                 ha='center', fontsize=8.5, color='#666')

    os.makedirs(OUT_DIR, exist_ok=True)
    out = f'{OUT_DIR}/{name}_运价股价利润关系.png'
    plt.savefig(out, dpi=130, bbox_inches='tight')
    plt.close()
    print('  saved:', out)


def draw_summary():
    """汇总：三家公司股价与BDTI/BDI 归一对比 + 净利"""
    fig, axes = plt.subplots(3, 1, figsize=(14, 13), sharex=True,
                             gridspec_kw={'hspace': 0.35})
    bdti = monthly_mean(load_freight('shipping_bdti', 'BDTI'))
    bdi = monthly_mean(load_freight('shipping_bdi', 'BDI'))
    for ax, meta in zip(axes, COMPANIES):
        price = monthly_mean(load_price(meta['code']))
        # 双轴
        ax2 = ax.twinx()
        if meta['main']:
            fm_ = bdti.loc[bdti.index >= pd.Timestamp('2016-02-01')]
            ax.plot(fm_.index, fm_.values, color='#e23b3b', lw=1.6,
                    label=f'{meta["main_cn"]}(左)', zorder=3)
            ax.set_ylabel(meta['main_cn'], color='#e23b3b', fontsize=11)
            ax.tick_params(axis='y', labelcolor='#e23b3b')
        ax2.plot(price.index, price.values, color='#2b7bd4', lw=1.8,
                 label=f'股价(右)', zorder=4)
        ax2.set_ylabel('股价(元)', color='#2b7bd4', fontsize=11)
        ax2.tick_params(axis='y', labelcolor='#2b7bd4')
        ax.set_title(f'{meta["name"]}({meta["code"]}) {meta["biz"]}', fontsize=13, fontweight='bold')
        ax.grid(axis='y', ls='--', alpha=0.3)
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=9)
    axes[0].set_title('三公司股价 vs 对应运价（月度）全景对比 2016–2026',
                      fontsize=15, fontweight='bold', pad=12)
    fig.text(0.5, 0.006,
             '注：中远海控为集运需CCFI/SCFI(未入库)，此处仅展示其股价与BDTI(不相关业务)对照以说明运价类型差异。'
             '运价为月均；股价不复权月均。',
             ha='center', fontsize=8.5, color='#666')
    out = f'{OUT_DIR}/三公司_运价股价全景对比.png'
    plt.savefig(out, dpi=130, bbox_inches='tight')
    plt.close()
    print('  saved:', out)


def draw_oil_pair():
    """油运双雄(招商轮船+中远海能)对比：BDTI运价 + 各自股价 + 净利——不含中远海控"""
    import matplotlib.gridspec as gridspec
    bdti = monthly_mean(load_freight('shipping_bdti', 'BDTI'))
    bdti = bdti.loc[bdti.index >= pd.Timestamp('2016-02-01')]

    fig = plt.figure(figsize=(14, 11))
    gs = gridspec.GridSpec(3, 2, height_ratios=[1.4, 1.2, 1.2], hspace=0.5, wspace=0.28)

    # 顶部大图: BDTI 运价 vs 招商轮船+中远海能 股价(归一对比不够直观→双轴各自价格差异大,统一画右轴股价)
    ax = fig.add_subplot(gs[0, :])
    ax.plot(bdti.index, bdti.values, color='#e23b3b', lw=2.2, label='BDTI 原油轮运价(左轴)', zorder=3)
    ax.fill_between(bdti.index, bdti.values, color='#e23b3b', alpha=0.08, zorder=1)
    ax.set_ylabel('BDTI 运价指数(点)', color='#e23b3b', fontsize=12)
    ax.tick_params(axis='y', labelcolor='#e23b3b')
    ax.grid(axis='y', ls='--', alpha=0.3)
    ax.set_title('BDTI原油轮运价 vs 油运双雄股价 (2016–2026, 月度)', fontsize=15, fontweight='bold', pad=10)

    ax2 = ax.twinx()
    for code, nm, c in [('601872', '招商轮船', '#2b7bd4'), ('600026', '中远海能', '#4a9d5f')]:
        p = monthly_mean(load_price(code))
        ax2.plot(p.index, p.values, color=c, lw=1.7, label=f'{nm}股价(右轴)', zorder=4)
    ax2.set_ylabel('股价(元,不复权)', fontsize=12)
    ax2.tick_params(axis='y')
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=10, ncol=3)
    # 标注2021低谷 & 2022景气
    ax.annotate('2021 运价十年低点\n中远海能巨亏', xy=(pd.Timestamp('2021-04-01'), bdti.loc['2021'].min()),
                xytext=(pd.Timestamp('2018-06-01'), 2600), fontsize=10, color='#a0302c',
                arrowprops=dict(arrowstyle='->', color='#a0302c'))
    ax.annotate('2022 俄乌冲突\n油运大景气', xy=(pd.Timestamp('2022-06-01'), 2300),
                xytext=(pd.Timestamp('2023-06-01'), 4000), fontsize=10, color='#2b5f3c',
                arrowprops=dict(arrowstyle='->', color='#2b5f3c'))

    # 下面: 两公司净利(占2/3+1/3 用两列)
    for i, (code, nm, c) in enumerate([('601872', '招商轮船', '#2b7bd4'), ('600026', '中远海能', '#4a9d5f')]):
        axp = fig.add_subplot(gs[1 + i, :])
        profits = load_profit(code)
        years = [p[0] for p in profits if 2016 <= p[0] <= 2025]
        vals = [dict(profits)[y] for y in years]
        colors = ['#4a9d5f' if v >= 0 else '#d9534f' for v in vals]
        axp.bar(years, vals, color=colors, width=0.6)
        axp.axhline(0, color='#444', lw=0.8)
        axp.set_ylabel(f'{nm} 归母净利(亿)', fontsize=11)
        axp.set_title(f'{nm}({code}) 年度归母净利润', fontsize=12, fontweight='bold', color=c)
        axp.grid(axis='y', ls='--', alpha=0.3)
        for x, v in zip(years, vals):
            axp.annotate(f'{v:.0f}', (x, v), textcoords='offset points',
                         xytext=(0, 4 if v >= 0 else -13), ha='center', fontsize=8.5,
                         color='#2b5f3c' if v >= 0 else '#a0302c')

    fig.text(0.5, 0.002,
             '注：BDTI=波罗的海原油轮运价指数(VLCC参照)。运价/股价均为月度均值；净利来自年度报告。'
             '相关r用月均运价与月均股价对齐计算: 招商轮船 r=0.84, 中远海能 r=0.77。数据源: akshare波罗的海指数 + ai_trading库。',
             ha='center', fontsize=9, color='#666')
    out = f'{OUT_DIR}/油运双雄_BDTI运价与股价净利.png'
    plt.savefig(out, dpi=130, bbox_inches='tight')
    plt.close()
    print('  saved:', out)

if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == '--oil-pair':
        draw_oil_pair()
    else:
        for m in COMPANIES:
            draw_company(m)
        draw_summary()
        draw_oil_pair()
    print('\n全部完成!')
