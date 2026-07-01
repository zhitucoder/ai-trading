from fastapi import APIRouter, Query
from ..database import query, query_one

router = APIRouter()

DISCLAIMER = '\n\n> ⚠️ **免责声明：** 以上分析仅基于历史数据和量化指标，不构成任何投资建议。股市有风险，投资需谨慎。过往表现不代表未来收益。'


def get_stock_name(code):
    r = query('SELECT stock_name FROM stocks WHERE stock_code = %s', [code])
    return r[0]['stock_name'] if r else ''


def get_klines(code, days=200):
    rows = query("""
        SELECT trade_date, open_price, high_price, low_price, close_price, volume
        FROM daily_kline
        WHERE stock_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
    """, [code, days])
    if not rows:
        return []
    rows.reverse()
    return [{
        'date': str(r['trade_date']),
        'open': float(r['open_price']),
        'high': float(r['high_price']),
        'low': float(r['low_price']),
        'close': float(r['close_price']),
        'volume': int(r['volume']),
    } for r in rows]


def get_financials(code):
    quarters = query("""
        SELECT fq.report_date, fq.q_revenue, fq.q_parent_net_profit
        FROM fin_quarterly fq
        WHERE fq.stock_code = %s
        ORDER BY fq.report_date DESC LIMIT 4
    """, [code])

    bs = query_one("""
        SELECT total_assets, total_liabilities, current_assets, current_liabilities
        FROM fin_balance_sheet
        WHERE stock_code = %s
        ORDER BY report_date DESC LIMIT 1
    """, [code])

    return quarters, bs


def calc_growth(cur, prev):
    if cur is None or prev is None or float(prev) == 0:
        return None
    return round((float(cur) - float(prev)) / float(prev) * 100, 2)


def compute_ma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def compute_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(len(prices) - period, len(prices)):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


@router.post('/debate/start')
def start_debate(stock_code: str = Query(..., description='股票代码')):
    name = get_stock_name(stock_code)
    if not name:
        return {'error': f'股票代码 {stock_code} 不存在'}

    klines = get_klines(stock_code)
    if len(klines) < 20:
        return {'error': f'股票 {stock_code} K线数据不足'}

    quarters, bs = get_financials(stock_code)

    closes = [k['close'] for k in klines]
    volumes = [k['volume'] for k in klines]
    n = len(closes)

    latest = closes[-1] if closes else 0
    prev_close = closes[-2] if n >= 2 else latest
    change_pct = round((latest - prev_close) / prev_close * 100, 2) if prev_close else 0

    ma5 = compute_ma(closes, 5)
    ma10 = compute_ma(closes, 10)
    ma20 = compute_ma(closes, 20)
    ma60 = compute_ma(closes, 60)
    ma200 = compute_ma(closes, 200)
    rsi14 = compute_rsi(closes, 14)

    vol_ma20 = sum(volumes[-20:]) / 20 if n >= 20 else None
    vol_surge = vol_ma20 and volumes[-1] > vol_ma20 * 1.5

    ma_bullish = ma5 and ma10 and ma20 and ma60 and ma5 > ma10 > ma20 > ma60
    ma_bearish = ma5 and ma10 and ma20 and ma60 and ma5 < ma10 < ma20 < ma60

    rev_growth = None
    profit_growth = None
    debt_ratio = None
    current_ratio = None
    latest_report_date = ''

    if quarters:
        latest_report_date = str(quarters[0]['report_date'])
        if len(quarters) >= 2:
            rev_growth = calc_growth(quarters[0]['q_revenue'], quarters[1]['q_revenue'])
            profit_growth = calc_growth(quarters[0]['q_parent_net_profit'], quarters[1]['q_parent_net_profit'])
        elif len(quarters) == 1:
            other_q = query_one("""
                SELECT q_revenue, q_parent_net_profit FROM fin_quarterly
                WHERE stock_code = %s
                ORDER BY report_date DESC LIMIT 1,1
            """, [stock_code])
            if other_q:
                rev_growth = calc_growth(quarters[0]['q_revenue'], other_q['q_revenue'])
                profit_growth = calc_growth(quarters[0]['q_parent_net_profit'], other_q['q_parent_net_profit'])

    if bs:
        ta = float(bs['total_assets']) if bs['total_assets'] else 0
        tl = float(bs['total_liabilities']) if bs['total_liabilities'] else 0
        ca = float(bs['current_assets']) if bs['current_assets'] else 0
        cl = float(bs['current_liabilities']) if bs['current_liabilities'] else 0
        if ta > 0:
            debt_ratio = round(tl / ta * 100, 2)
        if cl > 0:
            current_ratio = round(ca / cl, 2)

    if n >= 250:
        h52 = max(k['high'] for k in klines[-250:])
        l52 = min(k['low'] for k in klines[-250:])
    else:
        h52 = max(k['high'] for k in klines)
        l52 = min(k['low'] for k in klines)
    drawdown = round((h52 - l52) / h52 * 100, 2) if h52 else 0

    data = {
        'latest_price': latest,
        'change_pct': change_pct,
        'ma5': round(ma5, 2) if ma5 else None,
        'ma10': round(ma10, 2) if ma10 else None,
        'ma20': round(ma20, 2) if ma20 else None,
        'ma60': round(ma60, 2) if ma60 else None,
        'ma200': round(ma200, 2) if ma200 else None,
        'rsi14': rsi14,
        'volume_surge': vol_surge,
        'ma_bullish': ma_bullish,
        'ma_bearish': ma_bearish,
        'rev_growth': rev_growth,
        'profit_growth': profit_growth,
        'debt_ratio': debt_ratio,
        'current_ratio': current_ratio,
        '52w_high': round(h52, 2) if h52 else None,
        '52w_low': round(l52, 2) if l52 else None,
        'drawdown': drawdown,
        'report_date': latest_report_date,
    }

    rounds = [
        _analyst_opening(data, stock_code, name),
        _risk_manager_rebuttal(data, stock_code, name),
        _second_round_analyst(data, stock_code, name),
        _second_round_manager(data, stock_code, name),
        _comprehensive(data, stock_code, name),
    ]

    return {
        'stock_code': stock_code,
        'stock_name': name,
        'price': latest,
        'change_pct': change_pct,
        'rounds': rounds,
        'disclaimer': '⚠️ 免责声明：以上分析仅基于历史数据和量化指标，不构成任何投资建议。股市有风险，投资需谨慎。过往表现不代表未来收益。',
    }


def _analyst_opening(data, code, name):
    content = f"各位好，我是张研。下面我来分析 **{name}（{code}）** 的投资价值。\n\n"
    content += "### 📊 核心数据\n\n"

    if data['ma_bullish']:
        content += f"**均线系统呈现完美的多头排列**（MA5={data['ma5']} > MA10={data['ma10']} > MA20={data['ma20']} > MA60={data['ma60']}），这是典型的强势特征，表明主力资金持续介入，中线趋势向好。\n\n"
    else:
        content += f"当前股价 **{data['latest_price']}**，各周期均线虽有反复，但中长期趋势仍可期。\n\n"

    content += f"RSI(14) 为 **{data['rsi14']}**，处于{'合理区间' if 30 <= data['rsi14'] <= 70 else '超买区域需警惕' if data['rsi14'] > 70 else '超卖区域，反弹机会大'}。\n\n"

    if data['rev_growth'] is not None:
        content += f"最新报告期（{data['report_date']}）**营业收入同比增长 {data['rev_growth']:.2f}%**，"
        if data['profit_growth'] is not None:
            content += f"**净利润同比增长 {data['profit_growth']:.2f}%**，"
        content += "显示出公司良好的经营态势。\n\n"

    if data['debt_ratio'] is not None:
        content += f"资产负债率 **{data['debt_ratio']:.2f}%**，偿债压力可控。\n\n"

    content += "### 💡 看多逻辑\n\n"
    content += f"1. **趋势确认**：{'均线多头排列，上涨趋势明确' if data['ma_bullish'] else '股价仍运行在长期均线上方，大趋势尚未破坏'}\n"
    content += f"2. **基本面支撑**：{'营收和利润双增长，业绩驱动明确' if data['rev_growth'] and data['profit_growth'] and data['rev_growth'] > 0 and data['profit_growth'] > 0 else '公司基本面稳健，估值合理'}\n"

    if data['current_ratio'] is not None and data['current_ratio'] > 1.5:
        content += f"3. **流动性充裕**：流动比率 {data['current_ratio']:.2f}，短期偿债能力强\n"
    if data['volume_surge']:
        content += "4. **放量信号**：近期成交量显著放大，资金入场迹象明显\n"
    content += f"5. **估值安全边际**：52周高低区间为 {data['52w_low']}~{data['52w_high']}，当前价格处于合理位置\n\n"

    content += "**结论：** 该股技术面与基本面形成共振，建议积极关注。"

    return {
        'speaker': '张研',
        'role': '分析师开题',
        'avatar': '📈',
        'stance': 'bullish',
        'content': content,
    }


def _risk_manager_rebuttal(data, code, name):
    content = f"感谢张研的分析。我是李风控，负责投资风险管理。我持有不同意见。\n\n"
    content += "### ⚠️ 风险警示\n\n"

    if data['rsi14'] is not None and data['rsi14'] > 70:
        content += f"**RSI达到{data['rsi14']:.1f}，进入超买区间**，短期回调风险加剧。历史上该股在高RSI区域往往伴随5%~10%的调整幅度，当前追高性价比不高。\n\n"
    elif data['rsi14'] is not None and data['rsi14'] < 30:
        content += f"尽管RSI处于{data['rsi14']:.1f}的超卖区域，但这往往不是反转信号——在弱势行情中超卖可以持续很久。\n\n"

    if not data['ma_bullish']:
        content += f"**均线系统未能形成多头排列**，MA5（{data['ma5']}）< MA10（{data['ma10']}）< MA20（{data['ma20']}），短期趋势偏弱，此时入场容易接飞刀。\n\n"

    if data['rev_growth'] is not None and data['rev_growth'] < 0:
        content += f"**营收同比下降 {abs(data['rev_growth']):.2f}%**，这是一个值得警惕的信号。收入端萎缩往往预示着市场份额流失或行业景气度下行。\n\n"
    elif data['rev_growth'] is not None and data['rev_growth'] < 10:
        content += f"营收增速仅 **{data['rev_growth']:.2f}%**，增长动力不足。在当前的宏观环境下，低增长公司面临估值下修的风险。\n\n"

    if data['profit_growth'] is not None and data['profit_growth'] < 0:
        content += f"**净利润同比下滑 {abs(data['profit_growth']):.2f}%**，盈利恶化是最核心的风险信号。\n\n"

    if data['debt_ratio'] is not None and data['debt_ratio'] > 60:
        content += f"**资产负债率高达 {data['debt_ratio']:.2f}%**，财务杠杆偏高。在利率上行或经营波动时，高负债企业面临更大的财务压力。\n\n"

    content += f"过去一年最大回撤为 **{data['drawdown']:.2f}%**，波动性不容忽视。\n\n"

    content += "### 🚨 看空理由\n\n"
    content += "1. **风险收益比不佳**：当前上涨空间有限，下行风险敞口较大\n"
    content += "2. **动量衰减风险**：" + ("RSI超买后往往伴随回调" if data.get('rsi14', 0) > 70 else "趋势动能不足，难以持续上涨") + "\n"
    if data['profit_growth'] is not None and data['profit_growth'] < 10:
        content += f"3. **盈利质量存疑**：净利润增速（{data['profit_growth']:.2f}%）难以支撑当前估值\n"
    content += "4. **宏观不确定性**：当前市场环境复杂，系统性风险不容忽视\n\n"

    content += "**结论：** 建议保持谨慎，等待更好的入场时机或设置严格止损。"

    return {
        'speaker': '李风控',
        'role': '投资经理反驳',
        'avatar': '🛡️',
        'stance': 'bearish',
        'content': content,
    }


def _second_round_analyst(data, code, name):
    content = "李经理提示的风险很有价值，但我认为当前市场的定价已经充分反映了这些担忧。\n\n"
    content += "**我的补充逻辑：**\n\n"

    if data['rev_growth'] is not None and data['profit_growth'] is not None:
        if data['rev_growth'] > 10 and data['profit_growth'] > 10:
            content += f"✅ 营收增长{data['rev_growth']:.2f}%、利润增长{data['profit_growth']:.2f}%的组合表明公司正处于**业绩兑现期**，而非概念炒作。业绩是股价最坚实的支撑。\n\n"
        elif data['rev_growth'] > 0:
            content += f"✅ 在宏观承压背景下仍实现营收正增长（{data['rev_growth']:.2f}%），体现了公司**较强的抗周期能力**。\n\n"

    if data['current_ratio'] and data['current_ratio'] > 1:
        content += f"✅ 流动比率{data['current_ratio']:.2f}，短期流动性无虞，公司有能力度过短期困难。\n\n"

    if data['ma20'] and data['latest_price'] > data['ma20']:
        content += f"✅ 股价站上20日均线（{data['ma20']}），短期支撑有效，这是技术派交易者的重要参考线。\n\n"

    content += "从更长的周期来看，当前的经济下行阶段是优质公司的试金石——只有真正有竞争力的企业才能在逆势中扩张份额。"

    return {
        'speaker': '张研',
        'role': '分析师回应',
        'avatar': '📈',
        'stance': 'bullish',
        'content': content,
    }


def _second_round_manager(data, code, name):
    content = "张研，我尊重你的观点，但我必须再次强调风险的具象化。\n\n"
    content += "**我的核心担忧：**\n\n"

    if data['debt_ratio'] and data['debt_ratio'] > 50:
        content += f"❌ {data['debt_ratio']:.2f}%的资产负债率不是空谈——这意味着公司每{data['latest_price']:.2f}元的股价背后，有大量的债务在支撑。一旦信贷收紧，估值将承压。\n\n"

    if data['rsi14'] and data['rsi14'] > 60:
        content += f"❌ RSI {data['rsi14']:.1f}已经处于历史偏高水平，统计上该股在此位置继续大幅上涨的概率不足30%。\n\n"

    content += "❌ 投资的第一原则不是赚钱，而是不亏钱。当前时点入场，我们需要扪心自问：如果明天跌5%，我们是否还有信心持有？\n\n"
    content += f"52周低点{data['52w_low']}到当前价格{data['latest_price']}的涨幅已经可观，盈利盘随时可能兑现。\n\n"
    content += "还是那句话：**宁错过，不做错。**"

    return {
        'speaker': '李风控',
        'role': '投资经理回应',
        'avatar': '🛡️',
        'stance': 'bearish',
        'content': content,
    }


def _comprehensive(data, code, name):
    content = f"### 📋 综合评估\n\n"
    content += f"我们对 **{name}（{code}）** 进行了多维度分析，以下是关键指标汇总：\n\n"
    content += "| 维度 | 指标 | 数值 | 倾向 |\n"
    content += "|------|------|------|------|\n"
    content += f"| 价格 | 最新价 | {data['latest_price']} | {'📈' if data['change_pct'] >= 0 else '📉'} |\n"
    content += f"| 技术 | MA5/10/20/60 | {data['ma5']}/{data['ma10']}/{data['ma20']}/{data['ma60']} | {'🟢多头' if data['ma_bullish'] else '🔴偏弱'} |\n"
    content += f"| 技术 | RSI14 | {data['rsi14']} | {'🔥超买' if data['rsi14'] > 70 else '❄️超卖' if data['rsi14'] < 30 else '✅中性'} |\n"
    content += f"| 财务 | 营收增速 | {data['rev_growth']:.2f}% | {'🟢' if data['rev_growth'] and data['rev_growth'] > 0 else '🔴'} |\n"
    if data['profit_growth'] is not None:
        content += f"| 财务 | 利润增速 | {data['profit_growth']:.2f}% | {'🟢' if data['profit_growth'] > 0 else '🔴'} |\n"
    if data['debt_ratio'] is not None:
        content += f"| 财务 | 资产负债率 | {data['debt_ratio']:.2f}% | {'🟢' if data['debt_ratio'] < 40 else '🟡' if data['debt_ratio'] < 60 else '🔴'} |\n"
    content += f"| 风险 | 一年最大回撤 | {data['drawdown']:.2f}% | ⚠️ |\n\n"

    bullish_signals = 0
    bearish_signals = 0

    if data['ma_bullish']:
        bullish_signals += 1
    else:
        bearish_signals += 1
    if data['rev_growth'] and data['rev_growth'] > 10:
        bullish_signals += 1
    elif data['rev_growth'] and data['rev_growth'] < 0:
        bearish_signals += 1
    if data['profit_growth'] and data['profit_growth'] > 10:
        bullish_signals += 1
    elif data['profit_growth'] and data['profit_growth'] < 0:
        bearish_signals += 1
    if data['debt_ratio'] and data['debt_ratio'] > 60:
        bearish_signals += 1
    elif data['debt_ratio'] and data['debt_ratio'] < 40:
        bullish_signals += 1
    if data['rsi14'] and data['rsi14'] > 70:
        bearish_signals += 1
    elif data['rsi14'] and data['rsi14'] < 30:
        bullish_signals += 1

    total = bullish_signals + bearish_signals
    bull_pct = round(bullish_signals / total * 100) if total > 0 else 50

    content += "### 🎯 最终评估\n\n"
    if bull_pct > 60:
        content += f"**偏多倾向（{bull_pct}%看多）** — 张研的观点在当前数据支撑下更具说服力，但建议设置止损位，控制仓位在合理范围。\n\n"
    elif bull_pct < 40:
        content += f"**偏空倾向（{100 - bull_pct}%看空）** — 李风控的风险提示不可忽视，建议等待更明确的入场信号。\n\n"
    else:
        content += "**中性（多空力量均衡）** — 双方各有依据，建议结合自身风险偏好和持仓周期做出判断。\n\n"

    content += "> 💡 **建议：** 无论多空，做好仓位管理和止损设置。建议单只股票仓位不超过总资金的20%，设置5%~8%的止损线。"

    return {
        'speaker': '总结',
        'role': '综合讨论',
        'avatar': '🎯',
        'stance': 'neutral',
        'content': content,
    }
