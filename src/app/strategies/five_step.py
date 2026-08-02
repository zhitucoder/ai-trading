from ..database import query

FIVE_STEP_STRATEGIES = {
    'five_step_screen': {
        'name': '五步筛选法',
        'description': 'ROE趋势/现金流质量/毛利率趋势/核心利润/资产负债表多维度评分(0-100)，筛选经营质量持续改善的公司',
        'params': {},
    },
}


def get_latest_report_date():
    row = query("SELECT MAX(report_date) AS d FROM fin_ratios")
    return row[0]['d'] if row else None


def screen_five_step():
    rdate = get_latest_report_date()
    if not rdate:
        return []

    sql = """
    WITH ranked AS (
        SELECT i.stock_code, i.report_date,
            i.operating_revenue, i.operating_cost, i.net_profit,
            COALESCE(i.selling_expense, 0) AS selling_expense,
            COALESCE(i.admin_expense, 0) AS admin_expense,
            b.total_assets, b.total_liabilities, b.total_equity, b.cash,
            c.op_cash_flow,
            COALESCE(c.free_cash_flow, 0) AS free_cash_flow,
            ROW_NUMBER() OVER (PARTITION BY i.stock_code ORDER BY i.report_date DESC) AS rn
        FROM fin_income i
        JOIN fin_balance_sheet b ON b.stock_code = i.stock_code AND b.report_date = i.report_date
        JOIN fin_cash_flow c ON c.stock_code = i.stock_code AND c.report_date = i.report_date
        WHERE i.report_date <= %(rdate)s
          AND i.operating_revenue > 0
    )
    SELECT
        p1.stock_code, s.stock_name, %(rdate)s AS report_date,
        p1.net_profit, p2.net_profit AS profit_1, p3.net_profit AS profit_2,
        p1.op_cash_flow, p2.op_cash_flow AS ocf_1, p3.op_cash_flow AS ocf_2,
        p1.free_cash_flow,
        p1.operating_revenue, p1.total_assets, p1.total_equity, p1.cash,
        p1.total_liabilities,

        CASE WHEN p1.total_equity > 0
            THEN p1.net_profit / p1.total_equity * 100 END AS roe,
        CASE WHEN p2.total_equity > 0
            THEN p2.net_profit / p2.total_equity * 100 END AS roe_1,
        CASE WHEN p3.total_equity > 0
            THEN p3.net_profit / p3.total_equity * 100 END AS roe_2,

        CASE WHEN p1.operating_revenue > 0
            THEN (p1.operating_revenue - p1.operating_cost) / p1.operating_revenue * 100 END AS gross_margin,
        CASE WHEN p2.operating_revenue > 0
            THEN (p2.operating_revenue - p2.operating_cost) / p2.operating_revenue * 100 END AS margin_1,
        CASE WHEN p3.operating_revenue > 0
            THEN (p3.operating_revenue - p3.operating_cost) / p3.operating_revenue * 100 END AS margin_2,

        (p1.operating_revenue - p1.operating_cost - p1.selling_expense - p1.admin_expense) AS core_profit,
        (p2.operating_revenue - p2.operating_cost - COALESCE(p2.selling_expense, 0) - COALESCE(p2.admin_expense, 0)) AS cp_1,
        (p3.operating_revenue - p3.operating_cost - COALESCE(p3.selling_expense, 0) - COALESCE(p3.admin_expense, 0)) AS cp_2,

        CASE WHEN p1.total_assets > 0
            THEN p1.total_liabilities / p1.total_assets * 100 END AS debt_ratio,

        CASE WHEN p1.net_profit > 0
            THEN p1.op_cash_flow / p1.net_profit END AS ocf_ratio
    FROM ranked p1
    JOIN stocks s ON s.stock_code = p1.stock_code
    LEFT JOIN ranked p2 ON p2.stock_code = p1.stock_code AND p2.rn = 2
    LEFT JOIN ranked p3 ON p3.stock_code = p1.stock_code AND p3.rn = 3
    WHERE p1.rn = 1
    ORDER BY p1.stock_code
    """

    rows = query(sql, {'rdate': rdate})

    results = []
    for r in rows:
        scores = _compute_scores(r)
        if scores is None:
            continue
        results.append({**scores, 'report_date': str(rdate)})

    results.sort(key=lambda x: x['total_score'], reverse=True)
    return results


def _compute_scores(r):
    roe = r.get('roe')
    roe_1 = r.get('roe_1')
    roe_2 = r.get('roe_2')
    margin = r.get('gross_margin')
    margin_1 = r.get('margin_1')
    margin_2 = r.get('margin_2')
    cp = r.get('core_profit')
    cp_1 = r.get('cp_1')
    cp_2 = r.get('cp_2')
    profit = r.get('net_profit')
    profit_1 = r.get('profit_1')
    profit_2 = r.get('profit_2')
    ocf = r.get('op_cash_flow')
    ocf_1 = r.get('ocf_1')
    ocf_2 = r.get('ocf_2')
    ocf_ratio = r.get('ocf_ratio')
    debt = r.get('debt_ratio')
    total_assets = r.get('total_assets')
    cash = r.get('cash')
    free_cf = r.get('free_cash_flow')
    rev = r.get('operating_revenue')

    def safe(v):
        return v if v is not None else 0

    if roe is None or safe(roe) <= 3:
        return None

    roe_score = 0
    roe_improve = 0
    if roe_2 is not None and roe_1 is not None and safe(roe_1) > safe(roe_2):
        roe_improve += 1
    if roe_1 is not None and roe is not None and safe(roe) > safe(roe_1):
        roe_improve += 1
    roe_score = 10 + roe_improve * 10
    roe_score = min(roe_score, 30)

    ocf_score = 0
    cf_years = 0
    cf_ratios = []
    for o, p in [(ocf, profit), (ocf_1, profit_1), (ocf_2, profit_2)]:
        if o is not None and p is not None and p > 0:
            ratio = o / p
            cf_ratios.append(ratio)
            if ratio > 1.0:
                ocf_score += 8
            cf_years += 1
    if cf_ratios:
        avg_ratio = sum(cf_ratios) / len(cf_ratios)
        if avg_ratio > 1.2:
            ocf_score = min(ocf_score + 1, 25)
    ocf_score = min(ocf_score, 25)

    margin_score = 0
    margin_improve = 0
    if margin_2 is not None and margin_1 is not None:
        if safe(margin_1) > safe(margin_2):
            margin_improve += 1
    if margin_1 is not None and margin is not None:
        if safe(margin) > safe(margin_1):
            margin_improve += 1
    margin_score = margin_improve * 6
    if margin is not None and margin_2 is not None and safe(margin) > safe(margin_2):
        margin_score += 4
    if rev is not None and profit is not None and profit_1 is not None and rev > 0:
        rev_growth = (safe(rev) - safe(r.get('operating_revenue', 0))) / r.get('operating_revenue', 1) * 100
        profit_growth = (safe(profit) - safe(profit_1)) / max(abs(safe(profit_1)), 1) * 100
        if rev_growth > 10 and profit_growth > rev_growth * 2:
            margin_score += 4
    margin_score = min(margin_score, 20)

    cp_score = 0
    if cp is not None and cp > 0:
        for c, p in [(cp, profit), (cp_1, profit_1), (cp_2, profit_2)]:
            if c is not None and p is not None and safe(c) > safe(p):
                cp_score += 5
        if cp is not None and cp_2 is not None:
            current_gap = safe(cp) - safe(profit)
            past_gap = safe(cp_2) - safe(profit_2)
            if current_gap > past_gap:
                cp_score = min(cp_score + 2, 15)
    cp_score = min(cp_score, 15)

    bs_score = 0
    if debt is not None and safe(debt) < 60:
        bs_score += 3
    if total_assets and cash and safe(cash) / safe(total_assets) * 100 > 10:
        bs_score += 3
    if free_cf is not None and safe(free_cf) > 0:
        bs_score += 4
    bs_score = min(bs_score, 10)

    total = roe_score + ocf_score + margin_score + cp_score + bs_score

    if total >= 85:
        grade = 'A'
    elif total >= 70:
        grade = 'B'
    elif total >= 50:
        grade = 'C'
    else:
        grade = 'D'

    return {
        'stock_code': r['stock_code'],
        'stock_name': r['stock_name'],
        'total_score': round(total, 1),
        'roe_score': roe_score,
        'ocf_score': ocf_score,
        'margin_score': margin_score,
        'cp_score': cp_score,
        'bs_score': bs_score,
        'roe_current': round(roe, 1) if roe is not None else None,
        'margin_current': round(margin, 1) if margin is not None else None,
        'ocf_ratio': round(ocf_ratio, 2) if ocf_ratio is not None else None,
        'debt_ratio': round(debt, 1) if debt is not None else None,
        'score_grade': grade,
    }
