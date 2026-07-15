from fastapi import APIRouter
from pydantic import BaseModel
from ..database import query as db_query
from ..security.prompt_guard import get_guard
import os, json, re
from pathlib import Path
from datetime import datetime, date, timedelta

router = APIRouter()

LATEST_DATE = None

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

LLM_API_URL = os.environ.get('EXPERT_LLM_URL', '')
LLM_MODEL = os.environ.get('EXPERT_LLM_MODEL', '')
LLM_API_KEY = os.environ.get('EXPERT_LLM_KEY', '')

class AskRequest(BaseModel):
    question: str
    history: list = []

class AskResponse(BaseModel):
    answer: str
    sections: list = []
    error: str = ''
    note: str = ''

def get_latest_date():
    global LATEST_DATE
    if LATEST_DATE is None:
        r = db_query("SELECT MAX(trade_date) AS d FROM daily_kline")
        LATEST_DATE = r[0]['d'] if r else None
    return str(LATEST_DATE)[:10] if LATEST_DATE else ''

def get_stock_name(code):
    r = db_query("SELECT stock_name FROM stocks WHERE stock_code = %s", [code])
    return r[0]['stock_name'] if r else ''

def get_stock_code(name):
    r = db_query("SELECT stock_code FROM stocks WHERE stock_name LIKE %s LIMIT 1", [f'%{name}%'])
    return r[0]['stock_code'] if r else None

def safe_select(sql, params=None):
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith('SELECT') and not sql_stripped.startswith('WITH') and not sql_stripped.startswith('SHOW'):
        return None
    try:
        return db_query(sql, params or ())
    except Exception as e:
        return None

TOOLS_DESC = """
你是一个A股智能分析助手，可以使用以下工具来回答用户的问题。

可用工具:
1. query_database(sql: str) - 执行SELECT SQL查询数据库。表结构: stocks(股票), daily_kline(日K线), fin_income(利润表), fin_balance_sheet(资产负债表), fin_cash_flow(现金流量表), fin_quarterly(季度数据), fin_ratios(财务比率), stock_shares(股本), sectors(板块), stock_sectors(股票板块映射)
2. get_stock_code(name: str) - 根据股票名称获取股票代码
3. get_stock_name(code: str) - 根据股票代码获取股票名称
4. get_kline(stock_code: str, days: int = 60) - 获取股票K线数据(OHLCV)
5. search_web(query: str) - 搜索网络获取最新信息

回答规则:
- 使用中文回答
- 数据查询结果要清晰呈现，重要数字突出显示
- 如果是列表/排行类问题，用表格展示
- 如果是趋势分析，可以请求显示K线图
- 用户问"涨了多少"等涉及价格变化的，搜索网络确认最新行情
- 始终注明数据来源和日期
- 查询时使用最新交易日: {latest_date}
"""

def build_react_agent():
    global LLM_API_KEY, LLM_API_URL, LLM_MODEL

    if not LLM_API_KEY or not LLM_API_URL:
        return None

    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

    import urllib.request, urllib.error

    llm = ChatOpenAI(
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        base_url=LLM_API_URL.replace('/chat/completions', '/v1'),
        temperature=0.1,
        timeout=60,
    )

    @tool
    def query_database(sql: str) -> str:
        """执行SQL查询数据库。只支持SELECT。输入完整的SQL语句。"""
        results = safe_select(sql)
        if results is None:
            return "错误：只支持SELECT查询"
        if not results:
            return "查询结果为空"
        return json.dumps([dict(r) for r in results], ensure_ascii=False, default=str)

    @tool
    def get_stock_code_from_name(name: str) -> str:
        """根据股票中文名称或简称获取6位股票代码。输入: 股票名称"""
        code = get_stock_code(name)
        if code:
            return f"{name} 的股票代码是 {code}"
        return f"未找到股票: {name}"

    @tool
    def get_stock_name_from_code(code: str) -> str:
        """根据6位股票代码获取股票中文名称。输入: 6位股票代码"""
        name = get_stock_name(code)
        if name:
            return f"{code} 的股票名称是 {name}"
        return f"未找到股票代码: {code}"

    @tool
    def get_kline_data(stock_code: str, days: int = 60) -> str:
        """获取股票的K线行情数据(OHLCV)，用于绘制K线图。输入: 股票代码, 天数"""
        rows = db_query("""
            SELECT trade_date, open_price, high_price, low_price, close_price, volume, amount
            FROM daily_kline
            WHERE stock_code = %s
            ORDER BY trade_date DESC LIMIT %s
        """, [stock_code, days])
        if not rows:
            return "无K线数据"
        rows.reverse()
        return json.dumps([{k: str(v) if isinstance(v, (datetime, date)) else float(v) if v else 0
                            for k, v in dict(r).items()} for r in rows], ensure_ascii=False)

    @tool
    def search_web(query: str) -> str:
        """搜索网络获取实时信息。输入: 搜索关键词"""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
                if results:
                    return json.dumps([{
                        'title': r.get('title', ''),
                        'body': r.get('body', ''),
                        'href': r.get('href', ''),
                    } for r in results], ensure_ascii=False)
                return "未找到搜索结果"
        except Exception as e:
            return f"搜索失败: {e}"

    tools = [query_database, get_stock_code_from_name, get_stock_name_from_code, get_kline_data, search_web]
    system_prompt = TOOLS_DESC.format(latest_date=get_latest_date())

    agent = create_react_agent(llm, tools, prompt=system_prompt)
    return agent

agent_instance = None

def get_agent():
    global agent_instance
    if agent_instance is None:
        agent_instance = build_react_agent()
    return agent_instance

def extract_sections(text):
    """Parse markdown text to detect tables and chart-worthy data."""
    sections = [{'type': 'text', 'content': text}]
    return sections

def format_agent_response(text):
    lines = text.strip().split('\n')
    answer_parts = []
    table_data = None
    in_table = False
    table_rows = []

    for line in lines:
        stripped = line.strip()

        if '|' in stripped and stripped.startswith('|'):
            in_table = True
            cols = [c.strip() for c in stripped.split('|')[1:-1]]
            table_rows.append(cols)
            continue
        else:
            if in_table and len(table_rows) >= 2:
                if len(table_rows[0]) > 1:
                    table_data = {
                        'headers': table_rows[0],
                        'rows': table_rows[1:],
                    }
            in_table = False
            table_rows = []
            answer_parts.append(line)

    if in_table and len(table_rows) >= 2:
        if len(table_rows[0]) > 1:
            table_data = {
                'headers': table_rows[0],
                'rows': table_rows[1:],
            }

    answer = '\n'.join(answer_parts).strip()
    sections = [{'type': 'text', 'content': answer}]
    if table_data:
        sections.append({'type': 'table', 'data': table_data})

    return answer, sections

def check_kline_intent(text, history):
    combined = text
    for h in history[-3:]:
        if isinstance(h, dict) and h.get('question'):
            combined += ' ' + h['question']
    kline_keywords = ['k线', '走势', '行情', '涨跌', '股价', '价格', '趋势', 'chart', 'kline', '多少了']
    return any(kw in combined for kw in kline_keywords)

def try_extract_stock_code(text):
    codes = re.findall(r'\b(\d{6})\b', text)
    for code in codes:
        name = get_stock_name(code)
        if name:
            return code, name
    known_codes = {'茅台': '600519', '贵州茅台': '600519', '五粮液': '000858',
                   '盐湖': '000792', '盐湖股份': '000792', '平安': '601318',
                   '中国平安': '601318', '招商银行': '600036', '宁德时代': '300750',
                   '比亚迪': '002594', '万科': '000002', '格力': '000651',
                   '格力电器': '000651', '隆基': '601012', '隆基绿能': '601012',
                   '中信证券': '600030', '中国船舶': '600150', '茅台': '600519'}
    for kw, code in known_codes.items():
        if kw in text:
            return code, get_stock_name(code)
    return None, None

def detect_response_type(text):
    if text.startswith('{') or text.startswith('['):
        return 'json'
    return 'text'

@router.post('/ask', response_model=AskResponse)
def ask_question(req: AskRequest):
    guard = get_guard()
    guard_res = guard.check(req.question)
    if not guard_res.is_safe:
        return AskResponse(
            answer=guard.refusal(guard_res),
            error='PROMPT_BLOCKED',
            note='输入命中安全策略，已拦截，未调用大模型。',
        )

    agent = get_agent()
    if not agent:
        return AskResponse(
            answer='智能问数服务未配置。请在 .env 中配置以下环境变量:\n'
                   '- EXPERT_LLM_URL (如: https://api.deepseek.com/chat/completions)\n'
                   '- EXPERT_LLM_MODEL (如: deepseek-v4-flash)\n'
                   '- EXPERT_LLM_KEY (API密钥)',
            error='LLM未配置',
        )

    messages = []
    for h in req.history[-6:]:
        if h.get('question'):
            messages.append({'role': 'user', 'content': h['question']})
        if h.get('answer'):
            messages.append({'role': 'assistant', 'content': h['answer']})

    messages.append({'role': 'user', 'content': req.question})

    try:
        result = agent.invoke({'messages': messages})
        last_msg = result['messages'][-1]
        answer_text = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)

        answer, sections = format_agent_response(answer_text)

        stock_code, stock_name = try_extract_stock_code(req.question)
        chart_data = None
        if stock_code and check_kline_intent(req.question, req.history):
            rows = db_query("""
                SELECT trade_date, open_price, high_price, low_price, close_price, volume
                FROM daily_kline
                WHERE stock_code = %s
                ORDER BY trade_date DESC LIMIT 120
            """, [stock_code])
            if rows and len(rows) >= 5:
                rows.reverse()
                chart_data = [{
                    'date': str(r['trade_date']),
                    'open': float(r['open_price']),
                    'high': float(r['high_price']),
                    'low': float(r['low_price']),
                    'close': float(r['close_price']),
                    'volume': int(r['volume']),
                } for r in rows]
                sections.append({'type': 'chart', 'data': chart_data, 'stock_name': stock_name or stock_code})

        return AskResponse(answer=answer, sections=sections)

    except Exception as e:
        return AskResponse(
            answer=f'处理查询时出错: {str(e)}',
            error=str(e),
        )
