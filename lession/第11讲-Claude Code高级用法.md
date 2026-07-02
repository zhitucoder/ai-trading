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

## 11.3 常用内置命令

### Claude Code 命令

| 命令 | 作用 |
|------|------|
| `/init` | 初始化项目，生成 CLAUDE.md 项目说明书。Claude 会询问项目信息，自动创建配置文件，让后续对话了解项目上下文 |
| `/rewind` | 回退到上一步对话。用错了命令、Claude 做了不该做的事、或想换个方向时使用 |
| `/compact` | 压缩对话历史，清除早期上下文但保留关键信息。当对话变长、Claude 开始"失忆"时使用，可减少 token 消耗 |
| `/clear` | 清空当前对话，从头开始。Claude 会忘记之前的所有上下文 |

### OpenCode 命令

| 命令 | 作用 |
|------|------|
| `/connect` | 连接正在运行的终端会话，让 OpenCode 接管已有任务的上下文 |
| `/init` | 初始化 AGENTS.md 项目知识库，生成项目结构说明书 |
| `/compact` | 压缩对话上下文，清理早期内容，节省 token |
| `/clear` | 清空对话，重新开始 |

**CLI 命令（终端直接执行）：**

| 命令 | 说明 |
|------|------|
| `opencode` | 启动交互式对话 |
| `opencode connect` | 配置或切换 OpenCode 模型 |
| `opencode session list` | 查看历史会话列表 |
| `opencode -s ses_xxx` | 回到指定历史会话继续对话 |

### 计划模式（两种工作流）

Claude Code 进入计划模式有两种方式：

- 输入 `/plan` 命令
- 或单击 GUI 界面右上角的 "Plan" 按钮

计划模式下，Claude 不会直接写代码，而是先生成方案，确认后再执行。推荐两种工作流：

**工作流一：采访我**
Claude 轮流向你提问，搞清楚需求细节（"输入输出是什么？""边界情况有哪些？"），采访完成后整理成计划文件，你确认后执行。

**工作流二：先生成设计文档**
Claude 先输出需求设计文档和技术设计文档，你审查确认后再生成执行计划，最后才写代码。适合复杂功能，设计文档可作为项目存档。

无论哪种方式，对比直接让 Claude 写代码，都可以避免：
- 方向错了全部重来的浪费
- 写了大量不需要的代码
- 中途改需求导致的重复劳动

---

## 11.4 CLAUDE.md 项目说明书

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

## 11.5 Claude Code 扩展体系

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
