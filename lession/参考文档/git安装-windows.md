# Git 安装指南 — Windows

## 1. 下载

打开浏览器，访问：
https://git-scm.com/download/win

下载 Windows 版安装包（64-bit）。

## 2. 安装

双击安装包，一路默认选项即可。关键步骤注意：

- **Select Components** — 保留默认勾选（Git Bash、Git LFS 等）
- **Choosing the default editor** — 选 Notepad（记事本）即可
- **Adjusting your PATH** — 选 **"Git from the command line and also from 3rd-party software"**（推荐）
- **Choosing HTTPS transport backend** — 选 "Use the native Windows Secure Channel library"

## 3. 验证安装

打开「命令提示符」或「PowerShell」，输入：
```cmd
git --version
```

## 4. 配置用户名和邮箱

```cmd
git config --global user.name "你的名字"
git config --global user.email "你的邮箱@example.com"
```

## 5. 验证配置

```cmd
git config --list
```

## 注意事项

- 安装后如果 `git` 命令找不到，重启命令提示符
- Windows 用户在 WSL 里也需要安装 Git（见 Linux 版安装指南）
