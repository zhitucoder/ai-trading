# Git 安装指南 — Linux / WSL

## 1. 安装

```bash
sudo apt update && sudo apt install -y git
```

## 2. 验证安装

```bash
git --version
```

显示版本号即为成功，例如 `git version 2.34.1`。

## 3. 配置用户名和邮箱（首次使用必须设置）

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱@example.com"
```

## 4. 验证配置

```bash
git config --list
```

应该能看到你设置的名字和邮箱。
