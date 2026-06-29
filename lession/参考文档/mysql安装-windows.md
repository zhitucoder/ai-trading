# MySQL 安装指南 — Windows

## MySQL 是什么

MySQL 是世界上最流行的**开源关系型数据库**，简单说就是一个**存数据的大仓库**——它把数据按照"表"的结构组织起来，方便你存、查、改、删。

本课程用 MySQL 来存储 A 股的历史行情数据（K 线、交易量、财务指标等），后续的量化策略分析和 AI 模型都会从这个数据库里读数据。

> 你不需要会 SQL（数据库查询语言），后面 Claude 会自动帮你操作数据库。你只需要按下面的步骤把 MySQL 装好就行。

---

## 1. 下载

打开浏览器，访问：
https://dev.mysql.com/downloads/installer/

下载 **MySQL Installer for Windows**（选择 8.0 版本，约 400MB）。

## 2. 安装

双击安装包，选择 **"Server only"** 安装类型：

- **Type and Networking** — 保持默认（Standalone MySQL Server / Development Machine）
- **Authentication Method** — 选 **"Use Legacy Authentication Method"**（兼容性更好）
- **Accounts and Roles** — 设置 root 密码为 `aitrading123`
- **Windows Service** — 保持默认，勾选 "Start the MySQL Server at System Startup"

一路 Next 完成安装。

## 3. 验证安装

打开「命令提示符」或「PowerShell」：

```cmd
mysql -u root -p
```

输入密码 `aitrading123`，看到 `mysql>` 提示符即为成功。

## 4. 创建数据库

在 MySQL 提示符下执行：

```sql
CREATE DATABASE ai_trading CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
exit
```

## 5. 验证数据库

```cmd
mysql -u root -p -e "SHOW DATABASES;"
```

看到 `ai_trading` 在列表中即可。

## 注意事项

- 如果 `mysql` 命令找不到，将 MySQL 安装目录下的 `bin` 文件夹添加到系统 PATH 环境变量
- 默认安装路径：`C:\Program Files\MySQL\MySQL Server 8.0\bin`
- Windows 用户在 WSL 里需要再装一份 MySQL（见 Linux 版安装指南）
