from fastapi import APIRouter, Query
from pydantic import BaseModel
from ..strategies.technical import TECHNICAL_STRATEGIES, screen_ma_bullish, screen_quantitative_breakout
from ..strategies.fundamental import FUNDAMENTAL_STRATEGIES, screen_revenue_growth, screen_profit_growth, screen_debt_ratio, screen_fundamental_all, get_latest_report_date
from ..strategies.minervini import MINERVINI_STRATEGIES, screen_minervini_eps, screen_minervini_roe, screen_minervini_trend_template, screen_sepa_master
from ..strategies.turnaround import TURNAROUND_STRATEGIES, screen_turnaround
from ..database import query

router = APIRouter()


@router.get('/strategies')
def list_strategies():
    return {
        'technical': [
            {'id': k, **v} for k, v in TECHNICAL_STRATEGIES.items()
        ],
        'fundamental': [
            {'id': k, **v} for k, v in FUNDAMENTAL_STRATEGIES.items()
        ] + [{
            'id': 'fundamental_all',
            'name': '综合基本面筛选',
            'description': '营收增长率>阈值 且 净利润增长率>阈值 且 资产负债率<阈值',
            'params': {},
        }],
        'combined': [
            {
                'id': 'ma_bullish_and_revenue_growth',
                'name': '均线多头 + 营收增长 > 20%',
                'description': '筛选出均线多头排列且营业收入增长率超过20%的股票',
                'params': {},
            },
        ],
        'minervini': [
            {'id': k, **v} for k, v in MINERVINI_STRATEGIES.items()
        ],
        'turnaround': [
            {'id': k, **v} for k, v in TURNAROUND_STRATEGIES.items()
        ],
    }


@router.post('/execute')
def execute_screening(
    strategy_id: str = Query(..., description='策略ID'),
    ma_periods: str = Query('5,10,20,60', description='均线周期，逗号分隔'),
    revenue_threshold: float = Query(20.0, description='营收增长率下限(%)'),
    profit_threshold: float = Query(20.0, description='净利润增长率下限(%)'),
    debt_threshold: float = Query(50.0, description='资产负债率上限(%)'),
    consolidation_days: int = Query(20, description='横盘观察天数'),
):
    periods = [int(p.strip()) for p in ma_periods.split(',') if p.strip()]

    if strategy_id == 'quantitative_breakout':
        rows = screen_quantitative_breakout(consolidation_days)
        cols = ['breakout_price', 'breakout_pct', 'range_pct', 'breakout_date']
        return {'columns': cols, 'rows': rows, 'total': len(rows)}

    if strategy_id == 'ma_bullish':
        rows = screen_ma_bullish(periods)
        cols = ['close_price'] + [f'ma{p}' for p in periods]
        return {'columns': cols, 'rows': rows, 'total': len(rows)}

    if strategy_id == 'revenue_growth':
        rows = screen_revenue_growth(revenue_threshold)
        return {'columns': ['revenue_growth_rate', 'report_date'], 'rows': rows, 'total': len(rows)}

    if strategy_id == 'profit_growth':
        rows = screen_profit_growth(profit_threshold)
        return {'columns': ['net_profit_growth_rate', 'report_date'], 'rows': rows, 'total': len(rows)}

    if strategy_id == 'debt_ratio':
        rows = screen_debt_ratio(debt_threshold)
        return {'columns': ['debt_ratio', 'report_date'], 'rows': rows, 'total': len(rows)}

    if strategy_id == 'fundamental_all':
        rows = screen_fundamental_all(revenue_threshold, profit_threshold, debt_threshold)
        cols = ['revenue_growth_rate', 'net_profit_growth_rate', 'debt_ratio', 'operating_revenue', 'net_profit', 'report_date']
        return {'columns': cols, 'rows': rows, 'total': len(rows)}

    if strategy_id == 'ma_bullish_and_revenue_growth':
        return screen_ma_bullish_and_revenue_growth(periods, revenue_threshold)

    if strategy_id == 'sepa_master':
        rows = screen_sepa_master(
            eps_threshold=profit_threshold,
            rev_threshold=revenue_threshold,
            roe_threshold=debt_threshold,
        )
        cols = ['revenue_growth_rate', 'net_profit_growth_rate', 'roe', 'debt_ratio',
                'latest_price', 'pct_52w_high', 'ma50', 'ma150',
                'tightness', 'volume_ratio', 'report_date', 'latest_date']
        return {'columns': cols, 'rows': rows, 'total': len(rows)}

    if strategy_id == 'minervini_eps':
        rows = screen_minervini_eps(revenue_threshold)
        return {'columns': ['net_profit_growth_rate', 'report_date'], 'rows': rows, 'total': len(rows)}

    if strategy_id == 'minervini_roe':
        rows = screen_minervini_roe(debt_threshold)
        return {'columns': ['roe', 'report_date'], 'rows': rows, 'total': len(rows)}

    if strategy_id == 'minervini_trend_template':
        rows = screen_minervini_trend_template(revenue_threshold, int(profit_threshold))
        cols = ['latest_price', 'ma50', 'ma150', 'pct_52w_high', 'tightness', 'volume_ratio', 'latest_date']
        return {'columns': cols, 'rows': rows, 'total': len(rows)}

    if strategy_id == 'turnaround':
        rows = screen_turnaround(
            max_ma200_deviation=debt_threshold,
            min_rev_growth=revenue_threshold,
            min_prev_decline=-abs(profit_threshold),
            min_profit=max(1_000_000, int(abs(profit_threshold) * 1_000_000)),
        )
        cols = ['cur_rev_growth', 'prev_rev_growth', 'cur_profit_growth',
                'cur_profit', 'prev_profit', 'operating_revenue',
                'close_price', 'ma200', 'ma200_deviation_pct', 'report_date']
        return {'columns': cols, 'rows': rows, 'total': len(rows)}

    return {'error': f'Unknown strategy: {strategy_id}'}


def screen_ma_bullish_and_revenue_growth(ma_periods, revenue_threshold=20.0):
    rdate = get_latest_report_date()
    if not rdate:
        return {'columns': [], 'rows': [], 'total': 0}

    periods = sorted(ma_periods)
    max_period = max(periods)

    fund_rows = query("""SELECT sub.stock_code FROM (
        SELECT r.stock_code
        FROM fin_ratios r
        JOIN fin_income i ON i.stock_code = r.stock_code AND i.report_date = r.report_date
        JOIN fin_income i2 ON i2.stock_code = r.stock_code
            AND i2.report_date = DATE_SUB(r.report_date, INTERVAL 1 YEAR)
        WHERE r.report_date = %(rdate)s
          AND i2.operating_revenue IS NOT NULL AND i2.operating_revenue > 0
          AND (i.operating_revenue - i2.operating_revenue) / i2.operating_revenue * 100 > %(th)s
    ) sub""", {'rdate': rdate, 'th': revenue_threshold})
    if not fund_rows:
        return {'columns': _combined_cols(periods), 'rows': [], 'total': 0}

    codes = [r['stock_code'] for r in fund_rows]
    ma_selects = [f'AVG(close_price) OVER (PARTITION BY recent.stock_code ORDER BY recent.trade_date ROWS BETWEEN {p-1} PRECEDING AND CURRENT ROW) AS ma{p}' for p in periods]
    cond = ' AND '.join([f'ma{periods[i]} > ma{periods[i + 1]}' for i in range(len(periods) - 1)])
    cols_list = ', '.join([f'r.ma{p}' for p in periods])

    sql = f"""SELECT r.stock_code, r.close_price, {cols_list}
FROM (SELECT recent.stock_code, recent.trade_date, recent.close_price,
             {', '.join(ma_selects)},
             ROW_NUMBER() OVER (PARTITION BY recent.stock_code ORDER BY recent.trade_date DESC) AS rn
      FROM daily_kline recent
      WHERE recent.stock_code IN ({','.join(['%s'] * len(codes))})
        AND recent.trade_date >= DATE_SUB((SELECT MAX(trade_date) FROM daily_kline), INTERVAL {max_period + 10} DAY)) r
WHERE r.rn = 1 AND {cond}"""
    ma_rows = query(sql, codes)
    if not ma_rows:
        return {'columns': _combined_cols(periods), 'rows': [], 'total': 0}

    ma_map = {r['stock_code']: r for r in ma_rows}
    fund_details = query(f"""SELECT sub.* FROM (
        SELECT r.stock_code, s.stock_name,
               (i.operating_revenue - i2.operating_revenue) / i2.operating_revenue * 100 AS revenue_growth_rate,
               (i.net_profit - i2.net_profit) / i2.net_profit * 100 AS net_profit_growth_rate,
               b.total_liabilities / b.total_assets * 100 AS debt_ratio,
               i.operating_revenue, i.net_profit, r.report_date
        FROM fin_ratios r
        JOIN stocks s ON s.stock_code = r.stock_code
        JOIN fin_income i ON i.stock_code = r.stock_code AND i.report_date = r.report_date
        JOIN fin_income i2 ON i2.stock_code = r.stock_code
            AND i2.report_date = DATE_SUB(r.report_date, INTERVAL 1 YEAR)
        JOIN fin_balance_sheet b ON b.stock_code = r.stock_code AND b.report_date = r.report_date
        WHERE r.stock_code IN ({','.join(['%s'] * len(ma_rows))})
          AND r.report_date = %s
    ) sub""", [r['stock_code'] for r in ma_rows] + [str(rdate)])

    rows = []
    for fd in fund_details:
        sc = fd['stock_code']
        mr = ma_map[sc]
        rows.append({**fd, **{k: mr[k] for k in ('close_price', *[f'ma{p}' for p in periods])}})
    return {'columns': _combined_cols(periods), 'rows': rows, 'total': len(rows)}


def _combined_cols(periods):
    return ['close_price'] + [f'ma{p}' for p in periods] + \
           ['revenue_growth_rate', 'net_profit_growth_rate', 'debt_ratio', 'operating_revenue', 'net_profit', 'report_date']
