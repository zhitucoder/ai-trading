#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A股 全市场 营业收入/净利润 总量测算（含/剔除银行）"""
import pymysql
import csv
from collections import defaultdict

conn = pymysql.connect(host='127.0.0.1', port=3306, user='root',
                       password='aitrading123', database='ai_trading', charset='utf8mb4')
cur = conn.cursor()

BANK_SECTOR = '880471'

cur.execute("SELECT stock_code FROM stock_sectors WHERE sector_code=%s", (BANK_SECTOR,))
banks = {r[0] for r in cur.fetchall()}
print('bank stocks:', len(banks))

annual_dates = [f'{y}-12-31' for y in range(2016, 2026)]
h1_dates = [f'{y}-06-30' for y in range(2016, 2027)]
all_dates = list(dict.fromkeys(annual_dates + h1_dates))

rows = {}
for d in all_dates:
    cur.execute("SELECT stock_code, operating_revenue, net_profit, parent_net_profit FROM fin_income WHERE report_date=%s", (d,))
    rows[d] = cur.fetchall()
conn.close()

def aggregate(date_rows, exclude_banks):
    rev = net = pnet = cnt = 0.0
    for code, r, n, p in date_rows:
        if exclude_banks and code in banks:
            continue
        if r is not None:
            rev += float(r)
        if n is not None:
            net += float(n)
        if p is not None:
            pnet += float(p)
        cnt += 1
    return rev, net, pnet, int(cnt)

def to_csv(path, dates, exclude_banks, label):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow([label, '公司数', '营业总收入(亿元)', '净利润(亿元)', '归母净利润(亿元)',
                    '总营收同比%', '净利润同比%', '归母净利同比%', '户均营收(亿元)'])
        prev = None
        for d in dates:
            rev, net, pnet, cnt = aggregate(rows[d], exclude_banks)
            rev_y = rev / 1e8
            net_y = net / 1e8
            pnet_y = pnet / 1e8
            if prev:
                pr, pn, pp, pc = prev
                row = [d[:7], cnt, round(rev_y, 1), round(net_y, 1), round(pnet_y, 1),
                       round((rev - pr) / pr * 100, 2), round((net - pn) / pn * 100, 2),
                       round((pnet - pp) / pp * 100, 2), round(rev_y / cnt, 2)]
            else:
                row = [d[:7], cnt, round(rev_y, 1), round(net_y, 1), round(pnet_y, 1),
                       '', '', '', round(rev_y / cnt, 2)]
            w.writerow(row)
            prev = (rev, net, pnet, cnt)

base = '/home/rick/workspace/ai-trading/analysis/20260903'
to_csv(f'{base}/annual_all.csv', annual_dates, False, '全部A股-年度')
to_csv(f'{base}/annual_no_bank.csv', annual_dates, True, '剔除银行-年度')
to_csv(f'{base}/half_all.csv', h1_dates, False, '全部A股-半年度')
to_csv(f'{base}/half_no_bank.csv', h1_dates, True, '剔除银行-半年度')
print('done')