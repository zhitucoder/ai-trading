# Miniconda 安装指南 — Windows

## 1. 下载安装包

打开浏览器，访问：
官网地址：https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe
清华镜像（推荐国内）：https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Windows-x86_64.exe

下载 **Miniconda3 Windows 64-bit** 安装包（`.exe` 文件）。

## 2. 安装

双击安装包，一路默认选项即可。注意勾选：
- ✅ Add Miniconda3 to my PATH environment variable（勾选此项）
- ✅ Register Miniconda3 as my default Python

## 3. 验证安装

打开「命令提示符」或「PowerShell」，输入：
```cmd
conda --version
```

显示版本号即为成功。

## 4. 配置国内镜像（可选，加速下载）

```cmd
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --set show_channel_urls yes
```

## 5. 创建项目环境

```cmd
conda create -n aitrading python=3.12 -y
conda activate aitrading
```

之后所有操作都在 `aitrading` 环境下进行。

## 注意事项

- 如果安装后 `conda` 命令找不到，重启命令提示符
- Windows 用户安装 Miniconda 后，在 WSL 里还需要再装一份（WSL 是独立 Linux 环境）
