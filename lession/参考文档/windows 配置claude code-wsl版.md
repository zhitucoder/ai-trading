# Windows 环境配置 Claude Code 完整指南

从零开始，在 Windows 上通过 WSL 安装 Node.js、Claude Code，并配置 DeepSeek 模型。

---

# 一. Windows（Win10 以上）安装 WSL

给 Win 机器装上 Linux 环境（Mac 机器跳过本步骤）。写程序必备，写文档的就不需要。

## 注意事项

- 内存：建议 16GB 以上，MySQL + 全量数据导入较吃内存
- 磁盘：WSL 默认装到 C 盘。初始约 5GB，随着使用持续增大（安装依赖包、数据库、Python 库等），**可能超过 50GB**。C 盘空间紧张的建议装完就移到 D 盘

## 安装命令

```bash
wsl --install
```

安装完成需要重启，可能需要重启 2 次。

## 检查是否安装完成

```bash
wsl -l -v
```

应该看到下面这种信息，STATE 是 Stop 也是正常的：

```
C:\Users\zhang>wsl -l -v
  NAME      STATE           VERSION
* Ubuntu    Running         2
```

## 如果 C 盘空间不够，装完后移到 D 盘

```bash
wsl --export Ubuntu D:\wsl\ubuntu.tar
wsl --unregister Ubuntu
wsl --import Ubuntu D:\wsl\ubuntu\ D:\wsl\ubuntu.tar --version 2
```

<p style="color: red; font-size: 1.3em; font-weight: bold;">⚠️ 下面操作都是在 WSL 环境运行。</p>

---

# 二. 安装 Node.js

## 更新系统并安装 curl

```bash
sudo apt update && sudo apt install -y curl
```

## 添加 Node.js v24 官方源

```bash
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
```

## 安装 Node.js v24

```bash
sudo apt install -y nodejs
```

## 验证是否安装完成

```bash
node -v
npm -v
```

---

# 三. 安装 Claude

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

```bash
npm install -g @anthropic-ai/claude-code
```

## 检查

```bash
claude --version
```

---

# 四. 配置模型

## 准备 API Key

前往 DeepSeek 官网注册并获取 API Key。

## 配置 settings.json

编辑 `~/.claude/settings.json`，配置 DeepSeek 模型：

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

编辑 `~/.claude.json`：

```json
{
  "hasCompletedOnboarding": true
}
```

## 安装 VSCode Claude 插件

安装后在 VSCode 中测试 Claude 是否正常使用。

---

# 五. 安装 Conda（选做）

需要自动化执行程序则安装，只是写文档跳过本步骤。

---

# 六. 安装 Git（选做）

版本控制与回退，防止 AI 乱改。

---

# 附：配置腾讯混元模型

```bash
rick@theOne:~/.claude$ cat settings.json
```

```json
{
  "env": {
    "ANTHROPIC_API_KEY": "sk-tp-****",
    "ANTHROPIC_BASE_URL": "https://api.lkeap.cloud.tencent.com/plan/anthropic",
    "ANTHROPIC_MODEL": "hy3-preview"
  }
}

