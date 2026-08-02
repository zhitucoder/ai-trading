import json
import os
import re
from datetime import datetime
from pathlib import Path

from ..database import query, execute
from .profile import generate_profile

POSITIONING_CN = {
    'unchanged': '定位未变',
    'transforming': '转型中',
    'diversifying': '跨界延伸',
    'pivoting': '战略转向',
    'unknown': '定位待补充',
}

CHAIN_CN = {
    'upstream': '上游',
    'midstream': '中游',
    'downstream': '下游',
}

VALID_STATUS = set(POSITIONING_CN.keys())
VALID_CHAIN = set(CHAIN_CN.keys())


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


# ── 读取 / 写入 ──

def get_stock_intro(stock_code):
    """查询 stock_intro 表，返回 intro dict；无记录返回 None。"""
    row = query(
        "SELECT intro, positioning_status, positioning_label, chain_position, source, updated_at "
        "FROM stock_intro WHERE stock_code = %s", [stock_code])
    if not row:
        return None
    r = row[0]
    if not r['intro']:
        return None
    return {
        'text': r['intro'],
        'positioning_status': r['positioning_status'],
        'positioning_label': r['positioning_label'],
        'chain_position': r['chain_position'],
        'source': r['source'],
        'updated_at': str(r['updated_at']) if r['updated_at'] else None,
    }


def upsert_stock_intro(stock_code, name, intro, positioning_status='unknown',
                       positioning_label=None, chain_position=None, source='ai'):
    """写入/覆盖一条介绍。source 为 manual 时不被覆盖。"""
    if positioning_status not in VALID_STATUS:
        positioning_status = 'unknown'
    if chain_position not in VALID_CHAIN:
        chain_position = None
    if not intro or not intro.strip():
        return
    intro = intro.strip()[:500]
    execute("""
        INSERT INTO stock_intro (stock_code, stock_name, intro, positioning_status, positioning_label, chain_position, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            stock_name = VALUES(stock_name),
            intro = VALUES(intro),
            positioning_status = VALUES(positioning_status),
            positioning_label = VALUES(positioning_label),
            chain_position = VALUES(chain_position),
            source = VALUES(source)
    """, [stock_code, name, intro, positioning_status, positioning_label, chain_position, source])


def update_intro_if_not_manual(stock_code, name, intro, positioning_status='unknown',
                               positioning_label=None, chain_position=None, source='ai'):
    """AI/模板写入：跳过 source='manual' 的记录，避免覆盖人工精修。"""
    row = query("SELECT source FROM stock_intro WHERE stock_code = %s", [stock_code])
    if row and row[0]['source'] == 'manual':
        return
    upsert_stock_intro(stock_code, name, intro, positioning_status, positioning_label, chain_position, source)


# ── 模板兜底 ──

def _pick_industry(code, sectors):
    """优先选最具体的行业（level 最大）；无法判定时退回第一个。"""
    inds = sectors.get('industry') or []
    if not inds:
        return ''
    codes = [s.get('code') for s in inds if s.get('code')]
    if not codes:
        return inds[0].get('name', '')
    rows = query(
        "SELECT sector_code, sector_name FROM sectors "
        "WHERE sector_code IN (%s) ORDER BY level DESC, sector_code" % ','.join(['%s'] * len(codes)),
        codes)
    if not rows:
        return inds[0].get('name', '')
    return rows[0]['sector_name']


def build_template_intro(profile):
    """基于画像数据拼一条介绍，不调用 LLM。返回 (text, status, label)。"""
    code = profile.get('code') or ''
    name = profile.get('name') or ''
    sectors = profile.get('sectors') or {}
    industry = _pick_industry(code, sectors)
    concepts = [c.get('name', '') for c in (sectors.get('concept') or [])][:4]
    fin = profile.get('fin_data') or {}
    stage = profile.get('stage') or {}
    tags = [t.get('name', '') for t in (profile.get('biz_tags') or [])]

    rev_g = fin.get('revenue_growth_rate')
    profit_g = fin.get('net_profit_growth_rate')
    gm = fin.get('gross_margin')
    debt = fin.get('debt_ratio')
    rev_cagr = fin.get('revenue_cagr_5y')
    tenbagger = any('十倍股' in t for t in tags)

    parts = []
    if industry:
        if rev_cagr is not None and rev_cagr >= 20:
            status_word = '龙头'
        elif rev_g is not None and rev_g >= 10:
            status_word = '领先'
        else:
            status_word = '代表企业'
        parts.append(f'{industry}{status_word}')

    near = []
    if rev_g is not None:
        near.append(f'营收同比{rev_g:+.1f}%')
    if profit_g is not None:
        near.append(f'净利同比{profit_g:+.1f}%')
    if gm is not None:
        near.append(f'毛利率{gm:.1f}%')
    if near:
        parts.append('、'.join(near))

    if tenbagger:
        parts.append('近年涨幅超十倍')
    if stage.get('name'):
        parts.append(f'当前处于{stage["name"]}')

    if concepts:
        parts.append('涉及' + '、'.join(concepts[:3]))

    text = '。'.join(parts)
    if text:
        text += '。'
    if len(text) > 110:
        text = text[:107] + '…'

    status = 'unknown'
    label = None
    if industry:
        status = 'unchanged'
        label = industry

    return text, status, label, None


# ── AI 生成 ──

def _call_llm(messages, max_tokens=800, temperature=0.5):
    import urllib.request
    headers = {'Content-Type': 'application/json'}
    if LLM_API_KEY:
        headers['Authorization'] = f'Bearer {LLM_API_KEY}'
    payload = json.dumps({
        'model': LLM_MODEL,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'stream': False,
    }).encode()
    req = urllib.request.Request(LLM_API_URL, data=payload, headers=headers, method='POST')
    resp = urllib.request.urlopen(req, timeout=90)
    result = json.loads(resp.read())
    choices = result.get('choices', [])
    if choices:
        return choices[0].get('message', {}).get('content', '')
    return ''


def _extract_json(text):
    """从 LLM 输出中提取 JSON 对象。"""
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _build_llm_input(code):
    profile = generate_profile(code)
    if not profile or 'error' in profile:
        return None, profile
    fin = profile.get('fin_data') or {}
    sectors = profile.get('sectors') or {}
    annual = profile.get('annual_data') or {}
    revenue_growth = annual.get('revenue_growth') or []
    profit_growth = annual.get('profit_growth') or []
    rev_series = [{'year': g.get('year'), 'rate': g.get('rate')} for g in revenue_growth[:6]]
    profit_series = [{'year': g.get('year'), 'rate': g.get('rate')} for g in profit_growth[:6]]

    summary = {
        '代码': code,
        '名称': profile.get('name'),
        '行业': [s.get('name') for s in (sectors.get('industry') or [])],
        '概念': [s.get('name') for s in (sectors.get('concept') or [])][:6],
        '最近季度营收增速%': fin.get('revenue_growth_rate'),
        '最近季度净利增速%': fin.get('net_profit_growth_rate'),
        '毛利率%': fin.get('gross_margin'),
        '负债率%': fin.get('debt_ratio'),
        '近5年营收CAGR%': fin.get('revenue_cagr_5y'),
        '近5年净利CAGR%': fin.get('net_profit_cagr_5y'),
        'ROE%': fin.get('roe'),
        '近6年营收同比序列': rev_series,
        '近6年净利同比序列': profit_series,
        '业务标签': [t.get('name') for t in (profile.get('biz_tags') or [])][:10],
        'SEPA阶段': (profile.get('stage') or {}).get('name'),
        '报告期': fin.get('report_date'),
    }
    return profile, summary


def generate_intro_llm(code, retries=2):
    """调用 LLM 生成介绍。返回 (text, status, label, chain, used_fallback)。"""
    profile, summary = _build_llm_input(code)
    if not profile:
        return None, None, None, None, True
    text, status, label, chain = build_template_intro(profile)

    system = (
        '你是一位顶级投资人视角的A股分析师。撰写公司介绍时要有冲击力、直白犀利，'
        '用具体数字和具象比喻（如"印钞机""定价权""旱涝保收"），避免官腔和泛泛而谈。'
        '基于提供的真实财务数据撰写，绝不编造数据、绝不捏造营收构成。'
    )
    user = f"""请以投资视角为以下上市公司撰写一段约100字的中文公司介绍。

数据：
{json.dumps(summary, ensure_ascii=False, indent=2)}

写作要求：
1. 严格 80~120 字
2. 开头用一句有冲击力的话点出公司本质（垄断地位、定价权、护城河、印钞属性等）
3. 用具体财务数字支撑（毛利率、净利率、增速、ROE、负债率），并尽量用具象化表达
4. 包含公司定位：过去是什么 → 现在是什么（若数据不足以判断定位变化，只写当前定位）
5. 定位状态只取枚举之一：
   - unchanged 定位未变（主业与市场认知一致）
   - transforming 转型中（从旧主业转向新方向，过渡期）
   - diversifying 跨界延伸（主业之外延伸新业务线）
   - pivoting 战略转向（明确调转船头，新方向为主导）
   - unknown 无法判定
6. positioning_label 用"过去 → 现在"精炼概括（如"安防 → 智能物联+AIoT"），无法概括则为 null
7. chain_position 判断该公司在其所处产业链中的位置，只取枚举之一：
   - upstream 上游（原材料/资源/零部件/基础层）
   - midstream 中游（制造/加工/集成/应用层承上启下）
   - downstream 下游（品牌/渠道/终端/直接面向客户）
   - 无法判定则为 null
8. 只输出 JSON，格式：
{{"intro": "...", "positioning_status": "...", "positioning_label": "...", "chain_position": "..."}}
"""

    last_err = None
    for _ in range(retries + 1):
        try:
            raw = _call_llm([
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user},
            ])
            data = _extract_json(raw)
            if not data:
                last_err = 'JSON解析失败'
                continue
            intro = str(data.get('intro', '')).strip()
            st = str(data.get('positioning_status', '')).strip()
            lb = data.get('positioning_label')
            if lb is not None:
                lb = str(lb).strip() or None
            cp = data.get('chain_position')
            if cp is not None:
                cp = str(cp).strip() or None
                if cp not in VALID_CHAIN:
                    cp = None
            if not intro:
                last_err = 'intro为空'
                continue
            if len(intro) > 130:
                intro = intro[:127] + '…'
            return intro, st, lb, cp, False
        except Exception as e:
            last_err = str(e)

    return text, status, label, chain, True
