# 板块数据设计文档

## 1. 概述

本系统从通达信本地数据文件中获取板块信息，包括行业、地区、概念、风格四类板块，并建立股票与板块的映射关系。

## 2. 数据来源

板块数据来源于通达信安装目录下的本地文件：

```
/mnt/d/programs/stock/T0002/hq_cache/
├── tdxzs.cfg              # 板块定义（605个板块）
├── infoharbor_block.dat   # 概念/风格/地区板块成分股
└── tdxhy.cfg              # 行业板块成分股
```

### 2.1 数据文件说明

#### tdxzs.cfg - 板块定义
- 格式：GBK编码的文本文件
- 每行格式：`板块名称|板块代码|分类|子分类|层级|通达信行业代码`
- 分类说明：
  - `2` = 行业板块（145个）
  - `3` = 地区板块（32个）
  - `4` = 概念板块（270个）
  - `5` = 风格板块（158个）

示例：
```
煤炭|880301|2|1|0|T0101
煤炭开采|880302|2|1|1|T010101
黑龙江|880201|3|1|0|1
机器人概念|880904|4|2|0|机器人概念
高分红股|880526|5|2|0|高分红股
```

#### infoharbor_block.dat - 概念/风格/地区板块成分股
- 格式：GBK编码的文本文件
- 结构：
  - 以 `#` 开头的行是板块头部：`#板块名称,成分股数量,板块代码,...`
  - 后续行是成分股列表：`市场代码#股票代码`（0=深圳，1=上海）

示例：
```
#GN_机器人概念,1198,880904,20230101,20260512,,
0#000408,0#000538,0#000708,...
1#600018,1#600030,...
```

#### tdxhy.cfg - 行业板块成分股
- 格式：GBK编码的文本文件
- 每行格式：`市场代码|股票代码|通达信行业代码|||扩展代码`
- 通达信行业代码采用层级结构（如 T010101 属于 T0101）

示例：
```
0|000001|T1001|||X500102
0|000002|T110201|||X530101
1|600519|T010101|||X120101
```

## 3. 数据库设计

### 3.1 sectors 表 - 板块定义

```sql
CREATE TABLE sectors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sector_code VARCHAR(10) NOT NULL COMMENT '板块指数代码',
    sector_name VARCHAR(50) NOT NULL COMMENT '板块名称',
    category VARCHAR(20) NOT NULL COMMENT '板块类型: industry/region/concept/style',
    category_cn VARCHAR(10) NOT NULL COMMENT '板块类型中文',
    sub_category INT COMMENT '子分类',
    level INT DEFAULT 0 COMMENT '层级: 0=一级, 1=二级',
    tdx_industry_code VARCHAR(20) COMMENT '通达信行业代码',
    stock_count INT DEFAULT 0 COMMENT '成分股数量',
    UNIQUE KEY uk_code (sector_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='板块定义表';
```

### 3.2 stock_sectors 表 - 股票板块映射

```sql
CREATE TABLE stock_sectors (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
    sector_code VARCHAR(10) NOT NULL COMMENT '板块指数代码',
    category VARCHAR(20) NOT NULL COMMENT '板块类型',
    UNIQUE KEY uk_stock_sector (stock_code, sector_code),
    KEY idx_sector (sector_code),
    KEY idx_stock (stock_code),
    KEY idx_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票-板块映射表';
```

## 4. 导入脚本

### 4.1 脚本位置

`src/import_sectors.py`

### 4.2 运行方式

```bash
/home/rick/miniconda3/envs/aitrading/bin/python src/import_sectors.py
```

### 4.3 导入流程

1. **解析板块定义**
   - 读取 `tdxzs.cfg`
   - 提取板块代码、名称、分类、层级等信息
   - 建立通达信行业代码到板块代码的映射

2. **解析概念/风格/地区板块成分股**
   - 读取 `infoharbor_block.dat`
   - 解析每个板块的成分股列表
   - 生成股票-板块映射

3. **解析行业板块成分股**
   - 读取 `tdxhy.cfg`
   - 根据通达信行业代码的层级关系，同时映射到一级和二级行业板块
   - 例如：T010101（白酒）同时映射到 880381（白酒）和 880380（酿酒）

4. **写入数据库**
   - 先写入 `sectors` 表
   - 再批量写入 `stock_sectors` 表（每批5000条）

### 4.4 数据统计

导入完成后统计：
- 板块总数：605 个
  - 行业板块：145 个
  - 地区板块：32 个
  - 概念板块：270 个
  - 风格板块：158 个
- 股票-板块映射：82,485 条

## 5. 股票画像集成

### 5.1 查询函数

`src/app/strategies/profile.py` 中新增 `get_stock_sectors()` 函数：

```python
def get_stock_sectors(code):
    """获取股票所属板块信息"""
    rows = query('''
        SELECT ss.sector_code, s.sector_name, s.category, s.category_cn
        FROM stock_sectors ss
        JOIN sectors s ON s.sector_code = ss.sector_code
        WHERE ss.stock_code = %s
        ORDER BY s.category, s.level, ss.sector_code
    ''', [code])
    
    result = {'industry': [], 'region': [], 'concept': [], 'style': []}
    for r in rows:
        cat = r['category']
        if cat in result:
            result[cat].append({
                'code': r['sector_code'],
                'name': r['sector_name'],
            })
    return result
```

### 5.2 画像输出

`generate_profile()` 函数返回结果中新增 `sectors` 字段：

```json
{
  "code": "600519",
  "name": "贵州茅台",
  "sectors": {
    "industry": [
      {"code": "880380", "name": "酿酒"},
      {"code": "880381", "name": "白酒"},
      {"code": "880983", "name": "TDX 消费"}
    ],
    "region": [],
    "concept": [
      {"code": "880515", "name": "通达信88"},
      {"code": "880564", "name": "白酒概念"}
    ],
    "style": [
      {"code": "880526", "name": "高分红股"},
      {"code": "880721", "name": "北上重仓"},
      {"code": "880801", "name": "基金重仓"},
      {"code": "880821", "name": "大盘股"},
      {"code": "880835", "name": "绩优股"},
      {"code": "880847", "name": "行业龙头"}
    ]
  }
}
```

## 6. 常用查询示例

### 6.1 查询某股票的所有板块

```sql
SELECT s.category_cn, s.sector_code, s.sector_name
FROM stock_sectors ss
JOIN sectors s ON s.sector_code = ss.sector_code
WHERE ss.stock_code = '600519'
ORDER BY s.category, s.level;
```

### 6.2 查询某板块的所有成分股

```sql
SELECT ss.stock_code, st.stock_name
FROM stock_sectors ss
JOIN stocks st ON st.stock_code = ss.stock_code
WHERE ss.sector_code = '880564'  -- 白酒概念
ORDER BY ss.stock_code;
```

### 6.3 统计各板块成分股数量

```sql
SELECT s.category_cn, s.sector_name, COUNT(*) as stock_count
FROM stock_sectors ss
JOIN sectors s ON s.sector_code = ss.sector_code
GROUP BY s.sector_code
ORDER BY s.category, stock_count DESC;
```

## 7. 数据更新

板块数据需要定期更新，建议：
- 每月更新一次（通达信会在客户端启动时自动更新本地文件）
- 更新步骤：
  1. 打开通达信客户端，确保板块数据已同步
  2. 运行 `python src/import_sectors.py`
  3. 脚本会自动重建表并导入最新数据

## 8. 注意事项

1. **文件路径**：脚本中硬编码了通达信安装路径 `/mnt/d/programs/stock/`，如果路径变化需要修改脚本
2. **编码问题**：通达信文件使用 GBK 编码，脚本已处理编码转换
3. **行业层级**：行业板块有一级和二级之分，导入时会自动建立父子关系映射
4. **数据完整性**：部分板块可能没有成分股数据（如某些新板块），这是正常的
