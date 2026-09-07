#!/home/rick/miniconda3/envs/aitrading/bin/python
"""运价主题文章 → 公众号版 + 预览链接（不含趋势图，保留已有图表）。

用法:
  python3 build_freight_wechat.py
"""
import sys, os, re, base64, subprocess
from pathlib import Path

PUB = "/home/rick/.claude/skills/ai-trading-wechat-publish/scripts/publish.py"
WECHAT_COPY = "/home/rick/.claude/skills/wechat-article-typeset/wechat-copy.js"
PLAYWRIGHT_DIR = "/home/rick/.claude/skills/claude-design-card"
COVER_SIZE = "1800,766"

sys.path.insert(0, str(Path(PUB).parent))
import publish as pub  # 复用 gen_cover_html / gen_table_html / screenshot / crop_image

SRC = Path("/home/rick/workspace/ai-trading/analysis/20260906/雪球发布/运价与招商轮船中远海能_雪球版.md")
OUTDIR = SRC.parent
OUT = OUTDIR / "运价与招商轮船中远海能_公众号.md"
TMP = Path("/tmp/opencode")
TMP.mkdir(parents=True, exist_ok=True)

ENDING = '''
---

**💬互动征集：想看哪家公司的 AI 蒸馏专家分析？**
评论区留下公司名称 / 股票代码，浩哥每周精选 2-3 家，下期发布分析。

---

ai_trading 开源 AI 财报分析系统，**两分钟**生成行业/个股深度分析，**查看** GitHub/Gitee：zhitucoder/ai-trading。

**免责声明：**内容由 zhitucoder/ai_trading 系统AI生成，AI 存在模型幻觉，**仅供学习参考，不构成投资建议**。
'''

def main():
    content = SRC.read_text(encoding='utf-8')
    basename = SRC.stem

    # ── 1. 封面 ──
    print("[build] 生成封面...")
    title = "两次油运大周期<br>如何用BDTI精准抄底航运股？"
    sub = "2021谷底 · 2022暴涨 · 2026再创新高"
    data = "相关r 0.84 · 0.77 · BDTI是提前预判的钥匙"
    meta = "招商轮船601872 · 中远海能600026 · 油运双雄"
    cover_html = TMP / f"{basename}_cover.html"
    cover_png = TMP / f"{basename}_cover.png"
    pub.gen_cover_html(title, sub, data, meta, cover_html)
    pub.screenshot(cover_html, cover_png, COVER_SIZE)
    cover_b64 = "data:image/png;base64," + base64.b64encode(cover_png.read_bytes()).decode()
    print("  封面完成")

    # ── 2. 表格 → 暗调截图 ──
    print("[build] 截图表格...")
    lines = content.split('\n')
    tables = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith('|'):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                tbl.append(lines[i]); i += 1
            if len(tbl) >= 3:
                tables.append(tbl)
        else:
            i += 1

    def replace_table(match):
        idx = len(replace_table.count)
        replace_table.count += 1
        html_path = pub.gen_table_html(match, idx, TMP)
        png_path = TMP / f"table_{basename}_{idx}.png"
        pub.screenshot(html_path, png_path, "1400,500")
        pub.crop_image(png_path)
        return "![表格截图](data:image/png;base64," + base64.b64encode(png_path.read_bytes()).decode() + ")"
    replace_table.count = 0

    # 用占位符替换每个表格
    new_lines = []
    ti = 0
    for line in lines:
        if line.strip().startswith('|'):
            new_lines.append(line)
        else:
            new_lines.append(line)
    # 逐表替换
    result = content
    for tbl in tables:
        block = '\n'.join(tbl)
        idx = replace_table.count
        replace_table.count += 1
        html_path = pub.gen_table_html(tbl, idx, TMP)
        png_path = TMP / f"table_{basename}_{idx}.png"
        pub.screenshot(html_path, png_path, "1400,500")
        pub.crop_image(png_path)
        img = "![相关度表格](data:image/png;base64," + base64.b64encode(png_path.read_bytes()).decode() + ")"
        result = result.replace(block, img, 1)
    print(f"  {len(tables)} 张表格已转截图")

    # ── 3. 组装 ──
    # 封面插到最前
    result = result.strip()
    # 插入封面
    result = "![封面](data:image/png;base64," + cover_b64.split('base64,')[1] + ")\n\n---\n\n" + result
    # 加文末模板
    result = result.rstrip() + "\n\n" + ENDING
    # 引号统一中文
    result = result.replace('"', '\u201c').replace('"', '\u201d').replace('&quot;', '\u201c')

    OUT.write_text(result, encoding='utf-8')
    print(f"[build] 公众号文件: {OUT}")

    # ── 4. 生成预览 ──
    print("[build] 生成预览...")
    r = subprocess.run(['node', WECHAT_COPY, str(OUT), '--preset', '墨色书香'],
                       cwd=str(OUTDIR), capture_output=True, text=True)
    for line in r.stdout.strip().split('\n'):
        if 'edit.shiker.tech' in line:
            print(f"[build] 预览链接: {line.strip()}")

    # ── 5. 封面存档 ──
    cover_dst = Path("/mnt/d/pic/运价与招商轮船中远海能_cover.png")
    cover_dst.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(cover_png, cover_dst)
    print(f"[build] 封面已存: {cover_dst}")

if __name__ == '__main__':
    main()
