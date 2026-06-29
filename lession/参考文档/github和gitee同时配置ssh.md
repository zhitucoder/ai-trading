# GitHub 和 Gitee 同时配置 SSH

> 适用场景：一台电脑同时用 GitHub 和 Gitee，免密提交代码

## 1. 生成 GitHub 专用密钥

```bash
ssh-keygen -t ed25519 -C "你的邮箱@example.com" -f ~/.ssh/id_ed25519_github
```

一路按回车即可（不用设密码）。

## 2. 生成 Gitee 专用密钥

```bash
ssh-keygen -t ed25519 -C "你的邮箱@example.com" -f ~/.ssh/id_ed25519_gitee
```

同样一路按回车。

## 3. 配置 config 文件

```bash
vi ~/.ssh/config
```

写入以下内容：
```
Host github.com
  HostName github.com
  IdentityFile ~/.ssh/id_ed25519_github
  User git

Host gitee.com
  HostName gitee.com
  IdentityFile ~/.ssh/id_ed25519_gitee
  User git
```

## 4. 复制公钥分别添加到各平台

**GitHub：**
```bash
cat ~/.ssh/id_ed25519_github.pub
```
复制输出的文本，粘贴到 https://github.com/settings/keys → "New SSH Key"

**Gitee：**
```bash
cat ~/.ssh/id_ed25519_gitee.pub
```
复制输出的文本，粘贴到 https://gitee.com/profile/sshkeys → "添加 SSH Key"

## 5. 验证配置

```bash
ssh -T git@github.com
# 应该看到：Hi 用户名! You've successfully authenticated...

ssh -T git@gitee.com
# 应该看到：Hi 用户名! You've successfully authenticated...
```

## 6. 测试免密提交

克隆仓库时用 SSH 地址：

```bash
# GitHub
git clone git@github.com:你的用户名/仓库名.git

# Gitee
git clone git@gitee.com:你的用户名/仓库名.git
```

后续 push / pull 均不需要输入密码。
