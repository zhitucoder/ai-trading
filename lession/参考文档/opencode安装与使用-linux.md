# OpenCode 官网介绍 + 安装与使用指南

## 官网介绍

[OpenCode](https://opencode.ai/) 是一个开源 AI 编程代理（AI Coding Agent），可在终端、桌面应用或 IDE 扩展中使用。  
拥有 **16万+ GitHub Stars**、**900+ 贡献者**，每月 **750万+ 开发者** 使用。  
支持 **75+ LLM 提供商**（Claude、GPT、Gemini 等），内置 LSP 支持、多会话并行、会话分享等能力。

## 注册获取 API Key

有两种方式获取 API Key：

### 方式一：OpenCode Zen（推荐）

1. 打开终端运行以下命令安装后，进入交互界面：
   ```bash
   opencode
   ```
2. 在交互界面中输入命令 `/connect`，选择 **opencode**
3. 浏览器打开 [https://opencode.ai/auth](https://opencode.ai/auth)
4. 注册/登录账号，添加 billing 信息
5. 复制生成的 API Key
6. 回到终端粘贴 API Key 完成配置

### 方式二：使用其他模型提供商

直接在 `/connect` 中选择其他提供商（Anthropic Claude、OpenAI GPT、Google Gemini 等），输入对应的 API Key 即可。

---

# OpenCode + oh-my-opencode 安装指南

## 1. 安装 OpenCode 本体

```bash
curl -fsSL https://opencode.ai/install | bash
```

安装后运行以下命令验证：
```bash
opencode --version
```

## 2. 安装 oh-my-opencode（增强插件系统）

```bash
npm install -g oh-my-opencode
```

oh-my-opencode 提供：
- **Skills 技能市场** — 安装利弗莫尔、Minervini 等人物视角
- **MCP 服务** — 让 OpenCode 连接外部工具
- **多模型切换** — DeepSeek / GPT / Claude 等随意切换

## 3. 验证是否成功

```bash
opencode "你好"
```

能正常回复即表示安装配置成功。

## 4. 常用命令

| 命令 | 说明 |
|------|------|
| `opencode` | 启动交互式对话 |
| `opencode connect` | 配置或切换 OpenCode 模型 |
| `opencode session list` | 查看历史会话列表 |
| `opencode -s ses_xxx` | 回到指定历史会话继续对话 |
| `npm install -g oh-my-opencode` | 更新 oh-my-opencode |
| `npx opencode-usage --commander` | 查看 Token 使用量（首次自动安装），以后在 WebUI 查看 |
