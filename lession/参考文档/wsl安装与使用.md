# WSL 安装与使用指南

> 适用人群：Windows 10/11 用户
> Mac 用户跳过本步骤，macOS 本身自带 Unix 环境。

WSL（Windows Subsystem for Linux）是微软官方开发的 Windows 兼容层，让你能在 Windows 上直接运行 Linux 环境，不需要安装虚拟机或双系统。

---

## 一、系统要求

- Windows 10 版本 2004 及以上（内部版本 19041 及以上）
- 或 Windows 11 任意版本
- 内存建议 **16GB 以上**（后续跑 MySQL 和数据导入比较吃内存）

---

## 二、安装 WSL

### 一条命令安装

以**管理员身份**打开 PowerShell 或 CMD（右键 → 以管理员身份运行），执行：

```powershell
wsl --install
```

这条命令会自动完成以下操作：
- 启用 WSL 功能
- 启用虚拟机平台
- 下载并安装 Ubuntu（默认发行版）
- 设置 Linux 内核

### 安装完成后

1. **重启电脑**（可能需要重启 2 次）
2. 重启后系统会弹出 Ubuntu 初始化窗口，设置 Linux 用户名和密码
3. 这个用户名和密码是 Linux 系统的登录凭据，**不需要和 Windows 账号一致**

### 验证安装

打开 PowerShell 或 CMD（普通权限即可），执行：

```powershell
wsl -l -v
```

应该看到类似下面的信息：

```
  NAME      STATE           VERSION
* Ubuntu    Running         2
```

> STATE 显示 Stop 也是正常的，启动 WSL 时它会自动启动。

---

## 三、WSL 常用命令

| 命令 | 说明 |
|------|------|
| `wsl` 或 `bash` | 进入 WSL 终端 |
| `wsl -l -v` | 查看已安装的 Linux 发行版和状态 |
| `wsl --set-version Ubuntu 2` | 将 Ubuntu 切换到 WSL 2（推荐） |
| `wsl --set-default-version 2` | 设置默认使用 WSL 2 |
| `exit` | 退出 WSL 终端 |
| `wsl --shutdown` | 关闭 WSL（释放内存） |
| `wsl --status` | 查看 WSL 整体状态 |

---

## 四、WSL 的文件位置

WSL 里的文件存在虚拟磁盘中，**不要直接在 Windows 资源管理器里修改 WSL 内部文件**，可能导致权限问题。

**正确做法：**
- WSL 内部的文件 → 在 WSL 终端里通过 Linux 命令操作
- 需要和 Windows 共享的文件 → 放在 `/mnt/c/` 目录下（即 Windows 的 C 盘）

```
/mnt/c/Users/你的用户名/   →  Windows 的 C:\Users\你的用户名\
/mnt/d/                   →  Windows 的 D 盘
```

---

## 五、如果 C 盘空间不够，将 WSL 移到 D 盘

WSL 默认装在 C 盘，初始约 5GB，随着使用可能增长到 **50GB 以上**。C 盘空间紧张的建议装完就迁移。

**迁移步骤：**

```powershell
# 1. 将 WSL 导出到 D 盘
wsl --export Ubuntu D:\wsl\ubuntu.tar

# 2. 注销当前的 WSL
wsl --unregister Ubuntu

# 3. 从备份文件导入到 D 盘指定位置
wsl --import Ubuntu D:\wsl\ubuntu\ D:\wsl\ubuntu.tar --version 2

# 4. 验证是否成功
wsl -l -v
```

迁移完成后，原来的导出文件 `D:\wsl\ubuntu.tar` 可以删除。

---

## 六、常见问题

**Q：`wsl --install` 报错"不支持虚拟化"？**
A：进 BIOS 开启 Intel VT-x（Intel）或 AMD-V（AMD）虚拟化技术。

**Q：安装后输入 `wsl` 进不去？**
A：尝试 `wsl --set-version Ubuntu 2` 切换 WSL 2 版本，然后重启。

**Q：WSL 怎么卸载？**
A：在 PowerShell 中执行 `wsl --unregister Ubuntu` 即可删除。

**Q：WSL 里的 Ubuntu 怎么更新软件？**
A：进入 WSL 后执行：
```bash
sudo apt update && sudo apt upgrade -y
```

**Q：怎么在 VSCode 里用 WSL？**
A：装好 VSCode 后，在扩展商店搜索安装 **Remote - WSL** 插件。之后在 WSL 终端里进入项目目录，输入 `code .` 即可自动在 VSCode 中打开并连接到 WSL 环境。
