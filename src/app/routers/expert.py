from fastapi import APIRouter, Query
from pydantic import BaseModel
from ..database import query
import os, json, glob, re
from pathlib import Path
from datetime import datetime, timedelta
import urllib.request
import urllib.error

router = APIRouter()

SKILLS_DIR = os.path.expanduser('~/.claude/skills')


def _load_env():
    env_path = Path(__file__).resolve().parent.parent.parent.parent / '.env'
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip()
                if k and k not in os.environ:
                    os.environ[k] = v


_load_env()

LLM_API_URL = os.environ.get('EXPERT_LLM_URL', 'http://localhost:11434/v1/chat/completions')
LLM_MODEL = os.environ.get('EXPERT_LLM_MODEL', 'qwen2.5:14b')
LLM_API_KEY = os.environ.get('EXPERT_LLM_KEY', '')

DISCLAIMER = '\n\n---\n> ⚠️ *以上为教学演示，不构成投资建议。股市有风险，投资需谨慎。*'


class ChatRequest(BaseModel):
    expert_id: str
    stock_code: str
    question: str
    history: list = []


def scan_skills():
    skills = []
    skills_dir = Path(SKILLS_DIR)
    if not skills_dir.exists():
        return skills

    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir():
            continue
        name = d.name

        if not name.endswith('-perspective'):
            continue

        skill_md = d / 'SKILL.md'
        if not skill_md.exists():
            continue
        content = skill_md.read_text(encoding='utf-8', errors='ignore')

        frontmatter_desc = ''
        m = re.search(r'^description:\s*[|>]?\s*(.+?)$', content, re.MULTILINE)
        if m:
            frontmatter_desc = m.group(1).strip()
        if not frontmatter_desc or frontmatter_desc == '|':
            frontmatter_desc = ''

        desc_line = ''
        for line in content.split('\n')[1:15]:
            if line.strip() and not line.startswith('---') and not line.startswith('name:') and not line.startswith('description:'):
                desc_line = line.strip()[:100]
                break

        display = name.replace('-perspective', '')
        display = display.replace('-', ' ').title()
        skills.append({
            'id': name,
            'name': display,
            'file_name': name,
            'description': frontmatter_desc or desc_line,
        })

    return skills


@router.get('/list')
def list_experts():
    return {'experts': scan_skills()}


def get_stock_data(stock_code):
    name_row = query("SELECT stock_name FROM stocks WHERE stock_code = %s", [stock_code])
    stock_name = name_row[0]['stock_name'] if name_row else ''

    fin = query("""
        SELECT r.report_date,
               ROUND((i.operating_revenue - i2.operating_revenue) / NULLIF(i2.operating_revenue, 0) * 100, 2) AS revenue_growth,
               ROUND((i.net_profit - i2.net_profit) / NULLIF(i2.net_profit, 0) * 100, 2) AS profit_growth,
               ROUND(i.net_profit / NULLIF(b.total_equity, 0) * 100, 2) AS roe,
               ROUND(b.total_liabilities / NULLIF(b.total_assets, 0) * 100, 2) AS debt_ratio,
               ROUND(i.operating_revenue, 2) AS revenue,
               ROUND(i.net_profit, 2) AS profit
        FROM fin_ratios r
        JOIN fin_income i ON i.stock_code = r.stock_code AND i.report_date = r.report_date
        JOIN fin_income i2 ON i2.stock_code = r.stock_code
            AND i2.report_date = DATE_SUB(r.report_date, INTERVAL 1 YEAR)
        JOIN fin_balance_sheet b ON b.stock_code = r.stock_code AND b.report_date = r.report_date
        WHERE r.stock_code = %s
        ORDER BY r.report_date DESC LIMIT 1
    """, [stock_code])

    tdate_row = query("SELECT MAX(trade_date) AS d FROM daily_kline")
    tdate = tdate_row[0]['d'] if tdate_row else None

    kline = None
    if tdate:
        kline = query("""
            SELECT d.close_price, d.volume, d.trade_date,
                   ROUND(AVG(d.close_price) OVER (ORDER BY d.trade_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW), 2) AS ma50,
                   ROUND(AVG(d.close_price) OVER (ORDER BY d.trade_date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW), 2) AS ma150,
                   ROUND(d.close_price / NULLIF(h.max_52w, 0) * 100, 1) AS pct_52w
            FROM daily_kline d
            CROSS JOIN (
                SELECT MAX(close_price) AS max_52w FROM daily_kline
                WHERE stock_code = %s AND trade_date >= DATE_SUB(%s, INTERVAL 260 DAY)
            ) h
            WHERE d.stock_code = %s
              AND d.trade_date = (SELECT MAX(trade_date) FROM daily_kline WHERE stock_code = %s)
        """, [stock_code, tdate, stock_code, stock_code])

    result = {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'price': float(kline[0]['close_price']) if kline else None,
        'date': str(tdate)[:10] if tdate else None,
        'ma50': float(kline[0]['ma50']) if kline and kline[0]['ma50'] else None,
        'ma150': float(kline[0]['ma150']) if kline and kline[0]['ma150'] else None,
        'pct_52w': float(kline[0]['pct_52w']) if kline and kline[0]['pct_52w'] else None,
        'volume': int(kline[0]['volume']) if kline else None,
        'financials': {
            'report_date': str(fin[0]['report_date'])[:10] if fin else None,
            'revenue_growth': float(fin[0]['revenue_growth']) if fin and fin[0]['revenue_growth'] else None,
            'profit_growth': float(fin[0]['profit_growth']) if fin and fin[0]['profit_growth'] else None,
            'roe': float(fin[0]['roe']) if fin and fin[0]['roe'] else None,
            'debt_ratio': float(fin[0]['debt_ratio']) if fin and fin[0]['debt_ratio'] else None,
            'revenue': float(fin[0]['revenue']) if fin and fin[0]['revenue'] else None,
            'profit': float(fin[0]['profit']) if fin and fin[0]['profit'] else None,
        } if fin else None,
    }
    return result


def get_skill_content(expert_id):
    path = Path(SKILLS_DIR) / expert_id / 'SKILL.md'
    if not path.exists():
        return None
    content = path.read_text(encoding='utf-8', errors='ignore')
    frontmatter = {}
    m = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if m:
        for line in m.group(1).split('\n'):
            if ':' in line:
                k, v = line.split(':', 1)
                frontmatter[k.strip()] = v.strip().strip('|').strip('"').strip("'")

    body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)
    body = re.sub(r'^## 附录.*?$', '', body, flags=re.MULTILINE | re.DOTALL)

    return {
        'full': content,
        'body': body.strip(),
        'name': frontmatter.get('name', expert_id),
        'description': frontmatter.get('description', ''),
    }


def call_llm(messages, max_tokens=2048):
    headers = {
        'Content-Type': 'application/json',
    }
    if LLM_API_KEY:
        headers['Authorization'] = f'Bearer {LLM_API_KEY}'

    payload = json.dumps({
        'model': LLM_MODEL,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': 0.7,
        'stream': False,
    }).encode()

    try:
        req = urllib.request.Request(LLM_API_URL, data=payload, headers=headers, method='POST')
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        choices = result.get('choices', [])
        if choices:
            return choices[0].get('message', {}).get('content', '')
    except Exception as e:
        raise RuntimeError(f'LLM调用失败: {e}')


@router.post('/chat')
def chat_expert(req: ChatRequest):
    skill = get_skill_content(req.expert_id)
    if not skill:
        return {'error': f'未找到专家 {req.expert_id}'}

    stock = get_stock_data(req.stock_code)

    system_prompt = f"""{skill['body']}

## 回答规则
你是「{skill['name']}」思维框架的化身。你以{skill['name']}的身份回答问题。

当用户需要分析股票时，你必须引用下方的**真实市场数据**来支撑你的判断。
永远不要编造数据——使用下方提供的数据，如果数据不足以回答，诚实说"数据不足以判断"。

你的回答要有此人的思维特征、表达风格和判断框架。
保持角色扮演，但重要事实判断必须基于真实数据。

## 当前股票数据
股票: {stock['stock_code']} {stock['stock_name']}
最新价: {stock['price']}
日期: {stock['date']}
MA50: {stock['ma50']}
MA150: {stock['ma150']}
距52周高点: {stock['pct_52w']}%
成交量: {stock['volume']}

财务数据（{stock['financials']['report_date'] if stock['financials'] else '无'}）:
营收增长率: {stock['financials']['revenue_growth'] if stock['financials'] else '无'}%
净利润增长率: {stock['financials']['profit_growth'] if stock['financials'] else '无'}%
ROE: {stock['financials']['roe'] if stock['financials'] else '无'}%
资产负债率: {stock['financials']['debt_ratio'] if stock['financials'] else '无'}%
营收: {stock['financials']['revenue'] if stock['financials'] else '无'}
净利润: {stock['financials']['profit'] if stock['financials'] else '无'}"""

    messages = [
        {'role': 'system', 'content': system_prompt},
    ]

    for h in req.history:
        messages.append({'role': 'user', 'content': h.get('question', '')})
        if h.get('answer'):
            messages.append({'role': 'assistant', 'content': h['answer']})

    messages.append({'role': 'user', 'content': req.question})

    try:
        answer = call_llm(messages)
        answer += DISCLAIMER
        return {
            'answer': answer,
            'stock': {k: v for k, v in stock.items() if k != 'financials'},
            'financials': stock.get('financials'),
        }
    except RuntimeError as e:
        fallback = generate_fallback_answer(skill, stock, req.question)
        return {
            'answer': fallback + DISCLAIMER,
            'stock': {k: v for k, v in stock.items() if k != 'financials'},
            'financials': stock.get('financials'),
            'note': str(e),
        }


def generate_fallback_answer(skill, stock, question):
    """Generate a template-based answer when LLM is unavailable."""
    name = skill['name']
    data = []
    if stock['price']:
        data.append(f"- 最新价: {stock['price']}")
    if stock['ma50'] and stock['ma150']:
        trend = "上升" if stock['price'] and stock['ma50'] and stock['price'] > stock['ma50'] else "下降或震荡"
        data.append(f"- 价格在MA50{'上方' if stock['price'] and stock['ma50'] and stock['price'] > stock['ma50'] else '下方'}，"
                    f"MA50={stock['ma50']}，MA150={stock['ma150']}，中期趋势{trend}")
    if stock['pct_52w']:
        data.append(f"- 当前价距52周高点: {stock['pct_52w']}%")
    if stock['financials']:
        f = stock['financials']
        if f.get('revenue_growth') is not None:
            data.append(f"- 营收增长率: {f['revenue_growth']:+.2f}%")
        if f.get('profit_growth') is not None:
            data.append(f"- 净利润增长率: {f['profit_growth']:+.2f}%")
        if f.get('roe') is not None:
            data.append(f"- ROE: {f['roe']:.2f}%")
        if f.get('debt_ratio') is not None:
            data.append(f"- 资产负债率: {f['debt_ratio']:.2f}%")

    return f"""**{name} 视角分析 {stock.get('stock_name', stock['stock_code'])}**

> ⚠️ AI服务未配置，以下为基于数据的模板分析

**关键数据：**
{chr(10).join(data)}

**分析要点：**
1. 以上数据展示了该股票当前的技术面和基本面状况
2. 请根据{name}的思维框架自行分析这些数据的含义
3. 如需AI驱动分析，请设置 EXPERT_LLM_URL 环境变量指向您的LLM服务
   (当前: {LLM_API_URL}, 模型: {LLM_MODEL})

*当前处于演示模式，连接LLM后可获得完整的专家推理分析。*"""
