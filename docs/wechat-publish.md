# 公众号发布工作流

## 排版生成

- 工具：`/home/rick/.claude/skills/wechat-article-typeset/wechat-copy.js`
- 命令：`node wechat-copy.js <input.md> --preset "<预设名>"`
- 输出：`article.preset.html` + `wechat-preview-url.txt`（在与 input.md 同级目录）
- 预览链接格式：`https://edit.shiker.tech/copy.html?id=xxx`
- 用户在浏览器打开 → 点击「复制到剪贴板」→ 粘贴到公众号后台

### 推荐预设

| 文章类型 | 推荐预设 |
|---------|---------|
| 财经分析/深度研报 | 墨色书香、智慧蓝左边线 |
| 教程/技术分享 | 极简黑白、青绿左边线 |
| 观点/金句/短评 | 大字报风、橙心 |
| 品牌故事/人物 | 暖色色块、奶油杏色块 |

---

## 配图生成工作流

### 图片规格

| 类型 | 尺寸 | 比例 | 视口 |
|------|------|------|------|
| 头条封面 | 1800 × 766 px | 2.35:1 | `--viewport-size=1800,766` |
| 正文宽图 | 1920 × 1080 px | 16:9 | `--viewport-size=1920,1080` |

### 完整步骤

1. **创建 HTML**
   - 在 `/tmp/opencode/` 下编写自定义 HTML
   - 字体必须放大到适合手机阅读（见下方「文字角色对应」）
   - 配色参考下方「预设配色方案」

2. **截图**
   ```bash
   cd /home/rick/.claude/skills/claude-design-card
   npx playwright screenshot "file:///tmp/opencode/xxx.html" output.png \
     --viewport-size=W,H --wait-for-timeout=1500
   ```

3. **上传图床（ImgBB）**
   ```bash
   curl -s -F "source=@file.png" -F "type=file" -F "action=upload" \
     "https://imgbb.com/json" | python3 -c "import sys,json; print(json.load(sys.stdin)['image']['url'])"
   ```
   **注意**：
   - ImgBB 偶尔 CDN 延迟（返回 404 几分钟后变 200），等待 5-10 秒重试
   - 若 ImgBB 返回旧链接（内容哈希去重），在 `/tmp/opencode/` 下重新保存 PNG 再上传强制新链接

4. **插入文章**
   - 在 Markdown 中用 `![](https://i.ibb.co/xxx/xxx.png)` 嵌入

5. **刷新预览**
   - 重新运行 `wechat-copy.js` 生成新预览链接

---

## 封面排版规则

- 核心文字必须在中央正方形安全区（766 × 766 px），手机朋友圈不裁切
- 左右 padding 不宜过宽（建议 0 200px），给标题留空间
- 标题 96px+，副标题 72px+，底部 tagline 32px+

---

## 预设配色方案

| 风格名 | 底色 | 强调色 | 文字 | 适用场景 |
|--------|------|--------|------|---------|
| 编辑杂志风（蓝金） | `#1A1A2E` | `#E2B714` 金 | `#FFFFFF` | 通用财经分析 |
| **炭黑金** ✅ 推荐 | `#1C1C1E` | `#D4AF37` 香槟金 | `#FFFFFF` / `#999999` | 高端财经质感 |
| 暖灰高级 | `#F5F0EB` | `#E17055` 珊瑚橙 | `#2D2D2D` / `#6B6B6B` | 温暖编辑风 |
| 极简专业 | `#F5F5F5` | `#2563EB` 蓝 | `#374151` | 干净理性 |

---

## 文字角色对应（手机阅读尺寸）

| 角色 | 字号 | 样式 |
|------|------|------|
| 标签（如"AI教学 · 财报分析"） | 36px | 强调色，间距 6px |
| 章节号（壹/贰/叁...） | 52px | 强调色，间距 8px，加粗 |
| 主标题 | 110px | 白色/深灰，900 字重 |
| 说明文字 | 48px | 次级色 |
| 数据数字 | 90px | 强调色，900 字重 |
| 数据标签 | 32px | 灰色 |

---

## 文章头部/脚部规范

- **作者**：K哥
- **头部**：标题 + 副标题（见具体文章）
- **脚部**：
  - AI 生成免责声明（"本文由AI生成，不构成投资建议"）
  - GitHub 链接：`https://github.com/zhitucoder/ai-trading`
  - 回复提示（如"想学"或"111"）

---

## 图片覆盖更新流程

当需要更新配图中的文字（如替换作者名、调整标题）时：

1. 修改 `/tmp/opencode/` 下的 HTML 源文件
2. 重新 Playwright 截图（相同视口尺寸）
3. 上传到 ImgBB（用新 PNG 避免去重命中旧图）
4. 替换 Markdown 中的图片 URL
5. 重新生成预览链接
