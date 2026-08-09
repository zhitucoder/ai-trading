lines = []
a = lines.append

a('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 760">')
a('<defs>')
a('  <radialGradient id="glow" cx="50%" cy="50%" r="55%">')
a('    <stop offset="0%" stop-color="#d4a574" stop-opacity="0.06"/>')
a('    <stop offset="100%" stop-color="#d4a574" stop-opacity="0"/>')
a('  </radialGradient>')
a('  <marker id="arr-gold" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="#d4a574"/></marker>')
a('  <marker id="arr-blue" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="#38bdf8"/></marker>')
a('  <marker id="arr-violet" markerWidth="9" markerHeight="6" refX="8" refY="3" orient="auto"><polygon points="0 0,9 3,0 6" fill="#a78bfa"/></marker>')
a('  <marker id="arr-rose" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="#f87171"/></marker>')
a('  <marker id="arr-amber" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="#fbbf24"/></marker>')
a('</defs>')
a('<style>')
a('  text { font-family: -apple-system,"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif; }')
a('  .ttl { font-family: Georgia,"Times New Roman",serif; font-size: 30px; font-weight: 700; fill: #f5d0a9; }')
a('  .sub { font-size: 16px; fill: #f0e9df; font-weight: 700; }')
a('  .lbl { font-family: Georgia,"Times New Roman",serif; font-size: 15px; font-weight: 700; fill: #e8c49a; opacity: 1; }')
a('  .nm { font-size: 17px; font-weight: 700; }')
a('  .sm { font-size: 14px; fill: #e0d9cf; font-weight: 600; }')
a('  .xs { font-size: 13px; fill: #e0d9cf; font-weight: 600; }')
a('  .al { font-size: 14px; fill: #f0e9df; font-weight: 700; }')
a('  .fn { font-family: "Cascadia Code","SF Mono","Courier New",monospace; font-size: 13px; fill: #e8e2d9; font-weight: 700; }')
a('  .repo { font-family: "Cascadia Code","SF Mono","Courier New",monospace; font-size: 14px; fill: #e8c49a; font-weight: 700; }')
a('  .vx { font-size: 16px; fill: #7dd3fc; font-weight: 700; }')
a('</style>')
a('<rect width="960" height="760" fill="url(#glow)"/>')

# 标题
a('<text x="480" y="42" text-anchor="middle" class="ttl">ai-trading 财报分析原理</text>')
a('<text x="480" y="70" text-anchor="middle" class="sub">三步理解：从「建库 · 蒸馏」到「一句话生成专业报告」</text>')

# ============ 容器1：准备基础环境 ============
a('<rect x="40" y="92" width="880" height="132" rx="10" fill="none" stroke="#d4a574" stroke-width="0.8" stroke-dasharray="6,4" opacity="0.6"/>')
a('<text x="52" y="114" class="lbl">① 准备基础环境 · 一次性搭建</text>')

# 蒸馏专家知识（左·紫）
a('<rect x="70" y="130" width="200" height="76" rx="7" fill="#111111" stroke="#a78bfa" stroke-width="2"/>')
a('<text x="84" y="156" class="nm" fill="#c4b5fd">蒸馏专家知识</text>')
a('<text x="84" y="176" class="sm">书籍 / 教科书 / 教授</text>')
a('<text x="84" y="194" class="xs">财务分析框架</text>')

# AI编程工具（中·琥珀）
a('<rect x="380" y="130" width="200" height="76" rx="7" fill="#111111" stroke="#fbbf24" stroke-width="2"/>')
a('<text x="394" y="156" class="nm" fill="#fcd34d">AI 编程工具</text>')
a('<text x="394" y="176" class="sm">VSCode · 建库脚本</text>')
a('<text x="394" y="194" class="xs">蒸馏管线 · 模型编排</text>')

# 大模型（右·金）
a('<rect x="690" y="130" width="200" height="76" rx="7" fill="#141414" stroke="#d4a574" stroke-width="2.5"/>')
a('<text x="704" y="154" class="nm" fill="#f5d0a9">大模型 · LLM</text>')
a('<text x="704" y="174" class="sm">DeepSeek · GLM · Qwen</text>')
a('<text x="704" y="192" class="sm">Kimi · GPT-5</text>')

# 箭头：AI编程工具 → 蒸馏专家知识（左）
a('<path d="M 380 168 L 274 168" fill="none" stroke="#fbbf24" stroke-width="2.5" marker-end="url(#arr-violet)"/>')
a('<text x="327" y="159" text-anchor="middle" class="al">蒸馏</text>')
# 箭头：AI编程工具 → 大模型（右）
a('<path d="M 580 168 L 686 168" fill="none" stroke="#fbbf24" stroke-width="2.5" marker-end="url(#arr-gold)"/>')
a('<text x="633" y="159" text-anchor="middle" class="al">注入</text>')

# ============ 股票数据库（中间层 · 蓝色圆柱体） ============
a('<rect x="360" y="248" width="240" height="72" rx="8" fill="#111111" stroke="#38bdf8" stroke-width="2.5"/>')
a('<ellipse cx="402" cy="274" rx="15" ry="6" fill="none" stroke="#7dd3fc" stroke-width="2"/>')
a('<path d="M 387 274 L 387 302 M 417 274 L 417 302" fill="none" stroke="#7dd3fc" stroke-width="2"/>')
a('<path d="M 387 302 A 15 6 0 0 0 417 302" fill="none" stroke="#7dd3fc" stroke-width="2"/>')
a('<line x1="387" y1="283" x2="417" y2="283" stroke="#7dd3fc" stroke-width="1.5"/>')
a('<line x1="387" y1="292" x2="417" y2="292" stroke="#7dd3fc" stroke-width="1.5"/>')
a('<text x="438" y="268" class="nm" fill="#7dd3fc">股票数据库</text>')
a('<text x="438" y="288" class="sm">K线 · 财报 · 板块</text>')
a('<text x="438" y="305" class="xs">股本 · 分红</text>')

# 箭头：AI编程工具 → 数据库（向下 · 写入）
a('<line x1="480" y1="206" x2="480" y2="244" stroke="#fbbf24" stroke-width="3" marker-end="url(#arr-blue)"/>')
a('<text x="490" y="230" class="al">写入</text>')

# ============ 容器2：运行 Agent ============
a('<rect x="40" y="338" width="880" height="330" rx="10" fill="none" stroke="#d4a574" stroke-width="0.8" stroke-dasharray="6,4" opacity="0.6"/>')
a('<text x="52" y="360" class="lbl">② 运行 · 一句话驱动 Agent</text>')

# 用户指令
a('<rect x="50" y="390" width="230" height="80" rx="7" fill="#111111" stroke="#f87171" stroke-width="2"/>')
a('<text x="64" y="418" class="nm" fill="#fda4af">一句话指令</text>')
a('<text x="64" y="438" class="sm">「分析 贵州茅台」</text>')
a('<text x="64" y="456" class="xs">自然语言 · 零门槛</text>')

# Agent 核心（金色双边框）
a('<rect x="320" y="378" width="290" height="120" rx="8" fill="#141414" stroke="#d4a574" stroke-width="3"/>')
a('<rect x="326" y="384" width="278" height="108" rx="6" fill="none" stroke="#d4a574" stroke-width="0.8" opacity="0.6"/>')
a('<text x="465" y="406" text-anchor="middle" class="nm" fill="#f5d0a9">教授角色 · 智能体</text>')
a('<text x="465" y="428" text-anchor="middle" class="sm">大模型大脑 + 专家框架</text>')
a('<text x="465" y="448" text-anchor="middle" class="fn">解析 → 规划 → ReAct 推理</text>')
a('<text x="465" y="468" text-anchor="middle" class="xs">推理 → 调用 → 观察 → 再推理</text>')

# 箭头：Agent → 数据库（向上 · 读取）
a('<line x1="465" y1="378" x2="465" y2="322" stroke="#38bdf8" stroke-width="3" marker-end="url(#arr-blue)"/>')
a('<text x="476" y="352" class="al">读取</text>')

# 箭头：Agent → 大模型（智能体调用大模型）
a('<path d="M 610 402 C 720 402, 800 332, 795 210" fill="none" stroke="#d4a574" stroke-width="2.5" stroke-dasharray="6,4" marker-end="url(#arr-gold)"/>')
a('<text x="742" y="332" class="al">调用大脑</text>')

# 右侧工具：网络搜索 + 资料整理
a('<rect x="680" y="390" width="230" height="64" rx="7" fill="#111111" stroke="#a78bfa" stroke-width="2"/>')
a('<text x="694" y="416" class="nm" fill="#c4b5fd">网络搜索</text>')
a('<text x="694" y="436" class="sm">行业 · 新闻 · 业绩预告</text>')

a('<rect x="680" y="472" width="230" height="64" rx="7" fill="#111111" stroke="#6ee7b7" stroke-width="2"/>')
a('<text x="694" y="498" class="nm" fill="#a7f3d0">资料整理</text>')
a('<text x="694" y="518" class="sm">清洗 · 汇总 · 交叉验证</text>')

# 报告输出
a('<rect x="320" y="542" width="290" height="96" rx="8" fill="#161616" stroke="#5a9e6f" stroke-width="2.5"/>')
a('<text x="465" y="572" text-anchor="middle" class="nm" fill="#a7f3d0">专业股票分析报告</text>')
a('<text x="465" y="594" text-anchor="middle" class="sm">六维画像 · 2 ~ 5 分钟</text>')
a('<text x="465" y="612" text-anchor="middle" class="xs">AI 自动生成 · 图表 + 数据 + 逻辑</text>')
a('<text x="465" y="629" text-anchor="middle" class="fn">markdown / 公众号 / 截图</text>')

# 箭头：用户 → Agent
a('<line x1="280" y1="430" x2="316" y2="430" stroke="#f87171" stroke-width="2.5" marker-end="url(#arr-rose)"/>')
a('<text x="298" y="421" text-anchor="middle" class="al">指令</text>')

# 箭头：Agent → 工具（两条，无回传）
a('<path d="M 610 418 L 676 418" fill="none" stroke="#d4a574" stroke-width="2.5" marker-end="url(#arr-gold)"/>')
a('<text x="643" y="410" text-anchor="middle" class="al">搜</text>')
a('<path d="M 610 500 L 676 500" fill="none" stroke="#d4a574" stroke-width="2.5" marker-end="url(#arr-gold)"/>')
a('<text x="643" y="492" text-anchor="middle" class="al">整</text>')

# 箭头：Agent → 报告
a('<line x1="465" y1="498" x2="465" y2="538" stroke="#d4a574" stroke-width="2.5" marker-end="url(#arr-gold)"/>')
a('<text x="475" y="522" class="al">生成报告</text>')

# ============ 底部横幅：项目地址 + 交流 ============
a('<rect x="40" y="686" width="880" height="54" rx="10" fill="#141414" stroke="#d4a574" stroke-width="1.2" opacity="0.9"/>')
a('<text x="80" y="710" text-anchor="start" class="repo">gitee.com/zhitucoder/ai-trading</text>')
a('<text x="80" y="728" text-anchor="start" class="xs">开源 AI 财报分析系统 · 自动解析上市公司财报</text>')
a('<text x="878" y="719" text-anchor="end" class="vx">欢迎交流 vx：fillWithEnergy</text>')

a('</svg>')

with open('/tmp/agent_diagram/agent_analysis.svg', 'w') as f:
    f.write('\n'.join(lines))
print('SVG generated')
