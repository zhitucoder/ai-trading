#!/home/rick/miniconda3/envs/aitrading/bin/python3
"""基金持仓联动文章公众号发布脚本。

与 publish.py 的区别：本类文章的配图是本地"关系图 PNG"（非 trend API 图），
需将本地 PNG 转 base64 嵌入；表格转暗调截图；封面5行版式。

用法:
  python3 publish_linkage.py <md文件> --title 封面公司名 --sub 封面slogan --data 业绩数据 --meta 底部信息
"""

import sys, re, base64, subprocess, shutil
from pathlib import Path

sys.path.insert(0, '/home/rick/.claude/skills/ai-trading-wechat-publish/scripts')
from publish import (gen_cover_html, gen_table_html, screenshot, crop_image,
                     COVER_SIZE, TABLE_VIEWPORT)

PLAYWRIGHT_DIR = "/home/rick/.claude/skills/claude-design-card"
WECHAT_COPY = "/home/rick/.claude/skills/wechat-article-typeset/wechat-copy.js"
tmpdir = Path('/tmp/opencode')

ENDING = '''
---

**💬互动征集：想看哪家公司的AI蒸馏专家分析？**
评论区留下公司名称/股票代码，浩哥每周精选2-3家，下期发布分析。

---

ai_trading 开源 AI 财报分析系统，**两分钟**生成行业/个股深度分析，**查看** GitHub/Gitee：zhitucoder/ai-trading。

**免责声明：**内容由 zhitucoder/ai_trading 系统AI生成，AI 存在模型幻觉，**仅供学习参考，不构成投资建议**。
'''


def log(msg):
    print(f"[publish] {msg}")


def main():
    src = Path(sys.argv[1])
    outdir = src.parent
    outfile = outdir / f'{src.stem}_公众号.md'

    cover_args = {}
    argv = sys.argv[2:]
    for i in range(len(argv)):
        if argv[i] in ('--title', '--sub', '--data', '--meta') and i + 1 < len(argv):
            cover_args[argv[i][2:]] = argv[i + 1]

    content = src.read_text(encoding='utf-8')

    # ── 1. 封面 ──
    log("生成封面...")
    title = cover_args.get('title', src.stem[:8])
    sub = cover_args.get('sub', '基金持仓分析')
    data = cover_args.get('data', '')
    meta = cover_args.get('meta', '')
    cover_html = tmpdir / f'cover_{src.stem}.html'
    cover_png = tmpdir / f'cover_{src.stem}.png'
    gen_cover_html(title, sub, data, meta, cover_html)
    screenshot(cover_html, cover_png, COVER_SIZE)
    cover_b64 = 'data:image/png;base64,' + base64.b64encode(cover_png.read_bytes()).decode()

    # ── 2. 关系图 PNG → base64 ──
    log("处理关系图...")
    result = content
    # 找出所有 ![](xxx.png) 本地引用并转 base64
    def replace_local_img(m):
        alt, path = m.group(1), m.group(2)
        p = Path(path)
        if not p.is_absolute():
            p = outdir / p
        if p.exists() and p.suffix.lower() == '.png':
            b64 = 'data:image/png;base64,' + base64.b64encode(p.read_bytes()).decode()
            return f'![{alt}]({b64})'
        return m.group(0)
    result = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_local_img, result)

    # ── 3. 表格截图 ──
    log("截图表格...")
    lines = result.split('\n')
    tables = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith('|'):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                tbl.append(lines[i])
                i += 1
            if len(tbl) >= 3:
                tables.append(tbl)
        else:
            i += 1
    table_b64s = {}
    for idx, tbl in enumerate(tables):
        hp = gen_table_html(tbl, idx, tmpdir)
        pp = tmpdir / f'table_{idx}.png'
        screenshot(hp, pp, TABLE_VIEWPORT)
        crop_image(pp)
        table_b64s['\n'.join(tbl)] = 'data:image/png;base64,' + base64.b64encode(pp.read_bytes()).decode()
    log(f"  共 {len(tables)} 张表格")

    # ── 4. 插入封面 ──
    lines2 = result.split('\n')
    inserted = False
    for j in range(min(40, len(lines2))):
        if lines2[j].strip().startswith('---'):
            lines2.insert(j, '\n![]({})\n'.format(cover_b64))
            inserted = True
            break
    if not inserted:
        lines2.insert(0, '![]({})\n'.format(cover_b64))
    result = '\n'.join(lines2)

    # ── 5. 替换表格 ──
    for tbl_text, b64 in table_b64s.items():
        result = result.replace(tbl_text, '![]({})'.format(b64))

    # ── 6. 结尾 ──
    if '**免责声明：**' in result:
        result = result.rsplit('**免责声明：**', 1)[0]
    result = result.rstrip() + ENDING
    outfile.write_text(result, encoding='utf-8')
    log(f"公众号文件: {outfile}")

    # ── 7. 预览 ──
    log("生成预览...")
    r2 = subprocess.run(['node', WECHAT_COPY, str(outfile), '--preset', '墨色书香'],
                        cwd=str(outdir), capture_output=True, text=True)
    for line in r2.stdout.strip().split('\n'):
        if 'edit.shiker.tech' in line:
            log(f"预览链接: {line.strip()}")

    # ── 8. 封面保存 ──
    cover_dst = Path(f'/mnt/d/pic/{src.stem}_cover.png')
    shutil.copy(cover_png, cover_dst)
    log(f"封面已保存: {cover_dst}")
    log("完成！")


if __name__ == '__main__':
    main()
