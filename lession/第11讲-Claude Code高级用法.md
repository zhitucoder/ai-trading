# 第11讲：Claude Code 高级用法

> 目标：掌握 Claude Code 的配置、扩展与自定义能力
> 面向：零编程基础人员
> ⚠️ 免责声明：本课程内容为教学演示，所有分析仅为技术面和基本面的客观数据呈现，不构成任何投资建议。投资有风险，入市需谨慎。

---

## 11.1 Claude Code 安装

安装步骤参考：
- Linux / WSL 用户 → `参考文档/opencode安装与使用-linux.md`
- Windows 用户 → `参考文档/windows 配置claude code-wsl版.md`

核心命令就一行：

```bash
npm install -g @anthropic-ai/claude-code
```

安装后验证：

```bash
claude --version
```

---

## 11.2 配置 DeepSeek 模型

Claude Code 默认使用 Anthropic 的模型，但可以通过配置切换为 DeepSeek（更便宜、国内可用）。

创建配置文件 `~/.claude/settings.json`：

```json
{
  "env": {
    "ANTHROPIC_API_KEY": "sk-你的deepseek密钥",
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_MODEL": "deepseek-v4-pro"
  }
}
```

配置完成后，新建终端测试：

```bash
claude "你好"
```

能正常回复即表示配置成功。

> 可以同时配置多个模型，通过环境变量切换。参考文档中有完整的 settings.json 示例。

---

## 11.3 CLAUDE.md 项目说明书

CLAUDE.md 是 Claude Code 的项目说明书，分三个层级：

**全局作用域（所有项目共享）**
- 路径：`~/.claude/CLAUDE.md`
- 用途：放你个人的通用偏好，比如"我习惯用 Chinese，代码注释用中文"

**项目作用域（仅当前项目）**
- 路径：`项目根目录/CLAUDE.md`
- 用途：放当前项目的专属信息，比如数据库连接、项目结构、技术约束

**目录作用域（仅当前目录及子目录）**
- 路径：`项目根目录/子目录/CLAUDE.md`
- 用途：限定某个子目录的范围，比如在 `frontend/` 下放前端约束（Vue 3 规范、UI 框架），在 `backend/` 下放后端约束（API 设计规范、数据库操作规则）

**加载规则：** Claude Code 启动时按 全局 → 项目 → 目录 的顺序逐层加载，后者覆盖前者。三个层级配合使用，项目根目录放通用约束，子目录放专属约束。

---

## 11.4 Claude Code 扩展体系

Claude Code 有 4 种扩展机制：

### Skill（技能）

> **最常用、最实用。** 本课程第 10 讲的蒸馏专家就是 Skill 的典型应用。

Skill 是一份 Markdown 文件，教 Claude 如何扮演某个角色或执行某个任务。安装后，在对话中激活即可使用。

**安装 Skill：**
```bash
# 从 SkillHub 安装
skillhub install livermore-perspective

# 或从 GitHub 直接克隆
git clone https://github.com/xxx/skill-repo ~/.claude/skills/
```

**使用 Skill：**
在对话中引用技能名，Claude 会自动加载对应的指令。例如：
> "用 Livermore 的视角分析一下 600519"

**编写自己的 Skill：**
Skill 就是一个 Markdown 文件，放到 `~/.claude/skills/` 目录下即可。结构示例：

```markdown
# my-perspective

## 角色定位
你是 xxx，擅长 xxx

## 核心心法
1. xxx
2. xxx

## 表达风格
- 简洁直接
- 引用具体数据
```

添加后 Claude Code 启动时自动识别，无需重启。

### Hook（钩子）

在特定事件（如对话开始、工具调用前后）自动执行脚本。用于自动化工作流，比如每次对话前自动拉取最新数据。

### Plugin（插件）

Node.js 编写的扩展，可以添加自定义工具和功能。需要一定编程能力，适合高级用户。

### MCP（Model Context Protocol）

开放协议标准，让 Claude 连接外部工具和服务（数据库、浏览器、API 等）。MCP 是未来扩展的主要方向。

---

## 动手环节

1. 检查你的 `~/.claude/settings.json` 配置文件，确认 DeepSeek 模型配置正确
2. 在 `~/.claude/skills/` 下查看已安装的技能列表
3. 创建一个简单的自定义 Skill，比如"你是一个鲁迅风格的评论家"，保存后测试效果
