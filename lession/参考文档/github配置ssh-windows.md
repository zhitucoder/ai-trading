# GitHub SSH 配置 — Windows

## 1. 打开 PowerShell

按 `Win + X`，选择 **"终端管理员"** 或 **"Windows PowerShell"**。

## 2. 生成 SSH 密钥

```powershell
ssh-keygen -t ed25519 -C "你的邮箱@example.com"
```

**这条命令的意思：**
- `ssh-keygen` = SSH 密钥生成工具
- `-t ed25519` = 指定密钥算法为 Ed25519（比传统 RSA 更安全、更短、更快）
- `-C "..."` = 给密钥加个备注（填邮箱，GitHub 上用来识别是哪台机器的密钥）

一路按回车即可（不用设密码）。

## 3. 复制公钥内容

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

终端会显示一段以 `ssh-ed25519` 开头的文本，选中复制它。

## 4. 添加到 GitHub

1. 浏览器打开 https://github.com/settings/keys
2. 点击 **"New SSH Key"**
3. **Title** 随便填（例如 "My Windows"）
4. **Key** 粘贴刚才复制的内容
5. 点击 **"Add SSH Key"**

## 5. 验证配置

```powershell
ssh -T git@github.com
```

看到以下信息即成功：
```
Hi 你的用户名! You've successfully authenticated, but GitHub does not provide shell access.
```

## 6. 测试免密提交

```powershell
# 克隆仓库时用 SSH 地址（不是 HTTPS）
git clone git@github.com:你的用户名/仓库名.git

# 后续 push / pull 不需要输入密码
```

## 注意事项

- Windows 10 1809 以上版本自带 OpenSSH 客户端，不需要额外安装

- WSL 内的 Git 需要单独配置 SSH（见 Linux 版）
