from .database import query
import json


def _f(val):
    return float(val) if val is not None else 0.0


def _ratio(a, b):
    if b is None or _f(b) == 0:
        return None
    return round(_f(a) / _f(b) * 100, 2)


def _growth(cur, prev):
    if prev is None or _f(prev) <= 0:
        return None
    return round((_f(cur) - _f(prev)) / _f(prev) * 100, 2)


def compute_tags(stock_code, report_date=None):
    if report_date is None:
        r = query("SELECT MAX(report_date) AS d FROM fin_income WHERE stock_code = %s AND MONTH(report_date)=12 AND DAY(report_date)=31", [stock_code])
        if not r or not r[0]['d']:
            return None
        report_date = r[0]['d']

    rdate = str(report_date)[:10]
    name_row = query("SELECT stock_name FROM stocks WHERE stock_code = %s", [stock_code])
    stock_name = name_row[0]['stock_name'] if name_row else stock_code

    bs = query("SELECT * FROM fin_balance_sheet WHERE stock_code = %s AND report_date = %s", [stock_code, rdate])
    inc = query("SELECT * FROM fin_income WHERE stock_code = %s AND report_date = %s", [stock_code, rdate])
    cf = query("SELECT * FROM fin_cash_flow WHERE stock_code = %s AND report_date = %s", [stock_code, rdate])
    cb = query("SELECT * FROM fin_contract_bs WHERE stock_code = %s AND report_date = %s", [stock_code, rdate])
    ext = query("SELECT * FROM fin_extended WHERE stock_code = %s AND report_date = %s", [stock_code, rdate])

    bs = bs[0] if bs else {}
    inc = inc[0] if inc else {}
    cf = cf[0] if cf else {}
    cb = cb[0] if cb else {}
    ext = ext[0] if ext else {}

    rev = _f(inc.get('operating_revenue'))
    cost = _f(inc.get('operating_cost'))
    ta = _f(bs.get('total_assets'))
    fa = _f(bs.get('fixed_assets'))
    cash = _f(bs.get('cash'))
    st_borrow = _f(bs.get('short_term_borrow'))
    lt_borrow = _f(bs.get('long_term_borrow'))
    inventory = _f(bs.get('inventory'))
    ap = _f(bs.get('accounts_payable'))
    ar = _f(bs.get('accounts_receivable'))
    trading_fa = _f(bs.get('trading_fa'))
    lt_equity = _f(ext.get('long_term_equity'))
    surplus = _f(bs.get('surplus_reserve'))
    retained = _f(bs.get('retained_profit'))
    capital = _f(bs.get('share_capital'))
    cap_surplus = _f(bs.get('capital_surplus'))
    total_equity = _f(bs.get('total_equity'))
    goodwill = _f(bs.get('goodwill'))
    np = _f(inc.get('net_profit'))
    parent_np = _f(inc.get('parent_net_profit'))
    op_profit = _f(inc.get('operating_profit'))
    selling = _f(inc.get('selling_expense'))
    admin = _f(inc.get('admin_expense'))
    inv_income = _f(inc.get('investment_income'))
    non_op_inc = _f(inc.get('non_op_income'))
    total_profit = _f(inc.get('total_profit'))
    ocf = _f(cf.get('op_cash_flow'))
    fcf = _f(cf.get('free_cash_flow'))
    contract_liab = _f(cb.get('contract_liab'))

    prev_inc = query("SELECT operating_revenue, net_profit FROM fin_income WHERE stock_code = %s AND report_date = DATE_SUB(%s, INTERVAL 1 YEAR)", [stock_code, rdate])
    prev_revenue = _f(prev_inc[0]['operating_revenue']) if prev_inc else None
    prev_np = _f(prev_inc[0]['net_profit']) if prev_inc else None

    t = {}

    inv_assets = trading_fa + lt_equity
    op_asset_ratio = _ratio(ta - inv_assets, ta)
    if op_asset_ratio is not None and op_asset_ratio > 70:
        t['asset_type'] = '经营主导型'
    elif inv_assets > 0 and _ratio(inv_assets, ta) is not None and _ratio(inv_assets, ta) > 30:
        t['asset_type'] = '投资主导型'
    else:
        t['asset_type'] = '均衡型'

    fa_inv_ratio = _ratio(fa + inventory, ta)
    if fa_inv_ratio is None:
        t['asset_weight'] = '未知'
    elif fa_inv_ratio < 15:
        t['asset_weight'] = '轻资产'
    elif fa_inv_ratio <= 30:
        t['asset_weight'] = '中资产'
    else:
        t['asset_weight'] = '重资产'

    cash_ratio = _ratio(cash, ta)
    if cash_ratio is None:
        t['cash_status'] = '未知'
    elif cash_ratio > 15 and cash > st_borrow * 1.5:
        t['cash_status'] = '现金充裕'
    elif cash_ratio >= 5 and cash > st_borrow:
        t['cash_status'] = '现金正常'
    elif cash < st_borrow:
        t['cash_status'] = '现金紧张'
    else:
        t['cash_status'] = '现金正常'

    inv_to_rev = _ratio(inventory, rev) if rev > 0 else None
    if inv_to_rev is None:
        t['inventory_risk'] = '未知'
    elif inv_to_rev < 15:
        t['inventory_risk'] = '存货风险低'
    elif inv_to_rev <= 30:
        t['inventory_risk'] = '存货风险中'
    else:
        t['inventory_risk'] = '存货风险高'

    cl_ratio = _ratio(contract_liab, ta) if ta > 0 else None
    if cl_ratio is None:
        t['contract_liab_tag'] = '未知'
    elif cl_ratio > 15:
        t['contract_liab_tag'] = '合同负债高'
    elif cl_ratio >= 5:
        t['contract_liab_tag'] = '合同负债正常'
    else:
        t['contract_liab_tag'] = '合同负债低'

    hemo_source = ap + surplus + retained
    trans_source = st_borrow + lt_borrow + capital + cap_surplus
    hemo_total = hemo_source + trans_source
    hemo_ratio = _ratio(hemo_source, hemo_total) if hemo_total > 0 else None
    if hemo_ratio is None:
        t['hematopoiesis'] = '未知'
    elif hemo_ratio >= 60:
        t['hematopoiesis'] = '造血型'
    elif hemo_ratio >= 30:
        t['hematopoiesis'] = '均衡型'
    else:
        t['hematopoiesis'] = '输血型'
    t['hematopoiesis_ratio'] = hemo_ratio

    debt_ratio_val = _ratio(st_borrow + lt_borrow, ta)
    if debt_ratio_val is None:
        t['leverage'] = '未知'
    elif debt_ratio_val == 0:
        t['leverage'] = '零杠杆'
    elif debt_ratio_val < 10:
        t['leverage'] = '低杠杆'
    elif debt_ratio_val < 25:
        t['leverage'] = '中杠杆'
    else:
        t['leverage'] = '高杠杆'
    t['debt_ratio'] = debt_ratio_val

    gm = _ratio(rev - cost, rev) if rev > 0 else None
    if gm is None:
        t['margin_level'] = '未知'
    elif gm > 40:
        t['margin_level'] = '高毛利'
    elif gm >= 15:
        t['margin_level'] = '中毛利'
    else:
        t['margin_level'] = '低毛利'

    core_profit = rev - cost - selling - admin
    core_pct = _ratio(core_profit, rev) if rev > 0 else None
    t['core_profit_margin'] = core_pct

    core_share = _ratio(core_profit, op_profit) if op_profit != 0 else None
    if core_share is not None and core_share > 80:
        t['profit_source'] = '价值创造型'
    elif inv_income > 0 and _ratio(inv_income, op_profit) is not None and _ratio(inv_income, op_profit) > 30:
        t['profit_source'] = '价值整合型'
    elif non_op_inc > 0 and total_profit > 0 and _ratio(non_op_inc, total_profit) > 20:
        t['profit_source'] = '会计调整型'
    else:
        t['profit_source'] = '经营驱动型'

    minority_ratio = _ratio(parent_np, np) if np != 0 else None
    t['minority_ratio'] = minority_ratio

    net_margin = _ratio(np, rev) if rev > 0 else None
    if np > 0 and net_margin is not None and net_margin > 5:
        t['profit_status'] = '盈利'
    elif np > 0:
        t['profit_status'] = '微利'
    else:
        t['profit_status'] = '亏损'

    fa_rev_ratio = _ratio(rev, fa) if fa > 0 else None
    if fa_rev_ratio is None:
        t['match_fa_rev'] = '未知'
    elif fa_rev_ratio > 3.0:
        t['match_fa_rev'] = '产能高效'
    elif fa_rev_ratio >= 1.0:
        t['match_fa_rev'] = '产能正常'
    else:
        t['match_fa_rev'] = '产能低效'
    t['match_fa_rev_ratio'] = fa_rev_ratio

    if core_pct is None:
        t['match_rev_profit'] = '未知'
    elif core_pct > 30:
        t['match_rev_profit'] = '强转化'
    elif core_pct >= 15:
        t['match_rev_profit'] = '中转化'
    elif core_pct >= 5:
        t['match_rev_profit'] = '弱转化'
    else:
        t['match_rev_profit'] = '极弱转化'
    t['match_rev_profit_ratio'] = core_pct

    ocf_core_ratio = _ratio(ocf, core_profit) if core_profit > 0 else None
    if ocf_core_ratio is None:
        t['match_profit_ocf'] = '未知'
    elif ocf_core_ratio > 0.8:
        t['match_profit_ocf'] = '现金实现强'
    elif ocf_core_ratio >= 0.3:
        t['match_profit_ocf'] = '现金实现中'
    else:
        t['match_profit_ocf'] = '现金实现弱'
    t['match_profit_ocf_ratio'] = ocf_core_ratio

    ocf_np_ratio = _ratio(ocf, np) if np >= 0 else None
    t['ocf_to_np'] = ocf_np_ratio
    if ocf < 0 and np < 0:
        t['cashflow_type'] = '失血状态'
    elif ocf_np_ratio is not None and ocf_np_ratio >= 0.8:
        t['cashflow_type'] = '现金奶牛'
    elif ocf_np_ratio is not None and ocf_np_ratio >= 0.3:
        t['cashflow_type'] = '现金正常'
    else:
        t['cashflow_type'] = '纸面富贵'
    t['fcf_status'] = 'FCF充裕' if fcf > 0 else 'FCF为负'

    rev_growth = _growth(rev, prev_revenue)
    np_growth = _growth(np, prev_np)
    if rev_growth is None:
        t['growth_rate'] = '未知'
    elif rev_growth > 50:
        t['growth_rate'] = '爆发增长'
    elif rev_growth >= 25:
        t['growth_rate'] = '高速增长'
    elif rev_growth >= 10:
        t['growth_rate'] = '稳健增长'
    elif rev_growth >= 0:
        t['growth_rate'] = '缓慢增长'
    else:
        t['growth_rate'] = '衰退'
    if rev_growth is None:
        t['growth_quality'] = '未知'
    elif rev_growth > 0 and np_growth is not None and np_growth > rev_growth:
        t['growth_quality'] = '增收增利'
    elif rev_growth > 0 and np_growth is not None and np_growth < 0:
        t['growth_quality'] = '增收不增利'
    elif rev_growth > 0 and np_growth is not None:
        t['growth_quality'] = '增收平利'
    elif rev_growth <= 0 and np_growth is not None and np_growth <= 0:
        t['growth_quality'] = '减收减利'
    else:
        t['growth_quality'] = '未知'

    risk_flags = []
    if inventory > 0 and rev > 0 and _ratio(inventory, rev) > 30:
        risk_flags.append('存货风险')
    if ar > 0 and rev > 0 and _ratio(ar, rev) > 20:
        risk_flags.append('应收风险')
    if goodwill > 0 and total_equity > 0 and _ratio(goodwill, total_equity) > 30:
        risk_flags.append('商誉风险')
    if fa_inv_ratio is not None and fa_inv_ratio > 30 and cash < st_borrow:
        risk_flags.append('短债长投')
    t['risk_flags'] = json.dumps(risk_flags, ensure_ascii=False)

    score = 0
    max_score = 0
    checks = [
        (t.get('hematopoiesis') == '造血型', 15),
        (t.get('leverage') in ('零杠杆', '低杠杆'), 10),
        (t.get('margin_level') == '高毛利', 10),
        (t.get('cashflow_type') == '现金奶牛', 10),
        (t.get('growth_quality') == '增收增利', 10),
        (t.get('asset_weight') == '轻资产', 5),
        (t.get('cash_status') == '现金充裕', 5),
        (t.get('match_fa_rev') == '产能高效', 5),
        (t.get('match_rev_profit') in ('强转化', '中转化'), 5),
        (t.get('match_profit_ocf') == '现金实现强', 5),
        (t.get('profit_status') == '盈利', 5),
        (len(risk_flags) == 0, 10),
        (t.get('hematopoiesis') != '输血型', 5),
    ]
    for ok, pts in checks:
        max_score += pts
        if ok:
            score += pts
    pct = round(score / max_score * 100) if max_score > 0 else 0
    if pct >= 75:
        t['overall_rating'] = '优秀'
    elif pct >= 55:
        t['overall_rating'] = '良好'
    elif pct >= 35:
        t['overall_rating'] = '中等'
    elif pct >= 20:
        t['overall_rating'] = '中下'
    else:
        t['overall_rating'] = '差'

    pattern_parts = []
    if t.get('asset_weight') in ('轻资产',):
        pattern_parts.append('轻资产')
    if t.get('margin_level') == '高毛利':
        pattern_parts.append('高毛利')
    elif t.get('margin_level') == '低毛利':
        pattern_parts.append('低毛利')
    if t.get('cashflow_type') == '现金奶牛':
        pattern_parts.append('现金奶牛')
    if t.get('hematopoiesis') == '造血型':
        pattern_parts.append('造血')
    elif t.get('hematopoiesis') == '输血型':
        pattern_parts.append('输血')
    if t.get('growth_quality') == '增收不增利':
        pattern_parts.append('增收不增利')
    if t.get('leverage') == '高杠杆':
        pattern_parts.append('高杠杆')
    if contract_liab > 0 and cl_ratio is not None and cl_ratio > 15:
        pattern_parts.append('订单驱动')
    t['pattern_label'] = ''.join(pattern_parts) if pattern_parts else '一般'

    t['stock_code'] = stock_code
    t['stock_name'] = stock_name
    t['report_date'] = rdate
    return t
