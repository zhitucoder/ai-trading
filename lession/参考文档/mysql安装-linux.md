# MySQL 安装指南 — Linux / WSL

## MySQL 是什么

MySQL 是世界上最流行的**开源关系型数据库**，简单说就是一个**存数据的大仓库**——它把数据按照"表"的结构组织起来，方便你存、查、改、删。

本课程用 MySQL 来存储 A 股的历史行情数据（K 线、交易量、财务指标等），后续的量化策略分析和 AI 模型都会从这个数据库里读数据。

> 你不需要会 SQL（数据库查询语言），后面 Claude 会自动帮你操作数据库。你只需要按下面的步骤把 MySQL 装好就行。

---

## 1. 安装 MySQL 8.0

```bash
sudo apt update
sudo apt install -y mysql-server-8.0
```

如果系统源没有 MySQL 8.0，先添加官方源：

```bash
# 下载 MySQL APT 配置包
wget https://dev.mysql.com/get/mysql-apt-config_0.8.29-1_all.deb
sudo dpkg -i mysql-apt-config_0.8.29-1_all.deb
# 选择 MySQL 8.0，OK 确认
sudo apt update
sudo apt install -y mysql-server
```

## 2. 启动 MySQL 服务

```bash
sudo service mysql start
```

设置开机自启：

```bash
sudo systemctl enable mysql
```

## 3. 设置 root 密码

安装过程中会提示设置 root 密码。如果没提示，安装后执行：

```bash
sudo mysql
```

进入 MySQL 后设置密码：

```sql
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'aitrading123';
FLUSH PRIVILEGES;
exit
```

## 4. 验证登录

```bash
mysql -u root -p
```

输入密码 `aitrading123`，能看到 `mysql>` 提示符即为成功。

## 5. 创建数据库

```sql
CREATE DATABASE ai_trading CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
exit
```

## 6. 验证数据库

```bash
mysql -u root -p -e "SHOW DATABASES;"
```

看到 `ai_trading` 在列表中即可。
