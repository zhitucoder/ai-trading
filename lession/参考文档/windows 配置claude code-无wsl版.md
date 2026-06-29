# Windows 环境配置 Claude Code 完整指南

从零开始，在 Windows 上直接安装 Node.js、Claude Code，并配置 DeepSeek 模型。

---

# 一. 安装 Node.js

## 下载安装

前往 Node.js 官网下载 Windows 安装包（推荐 **LTS 长期支持版**）：

> https://nodejs.org/

下载 `.msi` 安装文件后双击运行，一路点 **Next** 完成安装。

## 验证是否安装完成

打开 PowerShell 或 CMD，执行：

```powershell
node -v
npm -v
```

如果能显示版本号（如 `v24.x.x` 和 `10.x.x`），说明安装成功。

---

# 二. 安装 Claude

## 官方安装说明

Claude Code 官方提供了多种安装方式，推荐参考官方文档：

> [Claude Code 官方快速入门](https://code.claude.com/docs/zh-CN/quickstart#native-install-recommended)

## 腾讯云安装 Claude

腾讯云提供了在中国大陆使用 Claude Code 的文档：

> [腾讯云 Claude Code 接入指南](https://cloud.tencent.com/document/product/1823/130070)

## 阿里云安装 Claude

阿里云百炼平台也支持 Claude Code 的接入和使用：

> [阿里云百炼 Claude Code 文档](https://bailian.console.aliyun.com/cn-beijing/?spm=a2ty02.30260213.resourceCenter.1.72e574a18d1fpq&tab=doc#/doc/?type=model&url=3023078)

## npm 安装

打开 PowerShell 或 CMD，执行：

```powershell
npm install -g @anthropic-ai/claude-code
```

C:\Users\zhang>npm install -g @anthropic-ai/claude-code

changed 2 packages in 2m
npm notice
npm notice New minor version of npm available! 11.9.0 -> 11.17.0
npm notice Changelog: https://github.com/npm/cli/releases/tag/v11.17.0
npm notice To update run: npm install -g npm@11.17.0
npm notice

## 检查

```powershell
claude --version
```

---

# 三. 配置模型

## 准备 API Key

前往 DeepSeek 官网注册并获取 API Key。

## 配置 settings.json

编辑 `%USERPROFILE%\.claude\settings.json`，配置 DeepSeek 模型：

```json
{
  "env": {
    "ANTHROPIC_API_KEY": "sk-xxx",
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-v4-flash",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-flash",
    "ANTHROPIC_MODEL": "deepseek-v4-flash",
    "ANTHROPIC_SMALL_FAST_MODEL": "deepseek-v4-flash"
  }
}
```

## 配置免登录

编辑 `%USERPROFILE%\.claude.json`：

跳过登录验证
编辑或新建 ~/.claude.json（Windows 路径：C:\Users\<用户名>\.claude.json），将 hasCompletedOnboarding 设为 true，跳过 Anthropic 官方登录验证。

```json
{
  "hasCompletedOnboarding": true
}
```

## 安装 VSCode Claude 插件

在 VSCode 扩展商店搜索 "Claude Code" 安装，安装后测试 Claude 是否正常使用。

---

# 四. 安装 Conda（选做）

需要自动化执行程序则安装，只是写文档跳过本步骤。

---

# 五. 安装 Git（选做）

版本控制与回退，防止 AI 乱改。

---

# 附：配置腾讯混元模型

```json
{
  "env": {
    "ANTHROPIC_API_KEY": "sk-tp-****",
    "ANTHROPIC_BASE_URL": "https://api.lkeap.cloud.tencent.com/plan/anthropic",
    "ANTHROPIC_MODEL": "hy3-preview"
  }
}
```
