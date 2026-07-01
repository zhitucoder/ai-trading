# Miniconda 安装指南 — Linux

## 1. 下载安装

```bash
# 下载 Miniconda 安装包（Python 3.12）
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

# 运行安装（一路 yes）
bash Miniconda3-latest-Linux-x86_64.sh
```

## 2. 激活 conda

安装完成后，关闭终端重新打开，或执行：
```bash
source ~/.bashrc
```

看到命令行前面出现 `(base)` 即表示成功：
```
(base) rick@ubuntu:~$
```

## 3. 验证安装

```bash
conda --version
```

## 4. 配置国内镜像（可选，加速下载）

```bash
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --set show_channel_urls yes
```

## 5. 创建项目环境

```bash
conda create -n aitrading python=3.12 -y
conda activate aitrading
```

之后所有操作都在 `aitrading` 环境下进行。
