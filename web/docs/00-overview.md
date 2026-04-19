# DroidBot Web 系统概述

## 简介

DroidBot Web 是一个基于 FastAPI 的 Web 服务，用于管理 Android 自动化任务的录制和回放。系统支持多用户协作、任务分配、录制数据管理和云手机设备管理（火山引擎 ACEP）。

## 技术栈

| 组件 | 方案 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | 高性能异步 Web 框架 |
| ORM | SQLModel | 融合 SQLAlchemy + Pydantic |
| 数据库 | MySQL 8.0 | 关系型数据库 |
| 数据库驱动 | pymysql | 同步 MySQL 驱动 |
| 数据库迁移 | Alembic | 管理数据库版本 |
| 密码加密 | passlib + bcrypt | 密码哈希 |
| JWT 认证 | python-jose | Token 生成和验证 |

## API 设计规范

本项目 API 遵循 RESTful 设计原则：

- URL 使用名词表示资源（如 `/users`、`/tasks`、`/cloud-devices`）
- HTTP 方法表示操作（GET 查询、POST 创建、PUT/PATCH 更新、DELETE 删除）
- 批量删除使用查询参数传递 ID（如 `DELETE /api/cloud-devices?ids=1,2,3`）

## 环境配置

在 `web/` 目录下创建 `.env` 文件（可复制 `.env.example`）：

```env
# MySQL 数据库配置
MYSQL_ROOT_PASSWORD=your-root-password-here
MYSQL_DATABASE=droidbot_web
MYSQL_USER=droidbot_user
MYSQL_PASSWORD=your-mysql-password-here
MYSQL_HOST=localhost
MYSQL_PORT=3306

# JWT 认证配置
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# 应用配置
DEBUG=False
CORS_ORIGINS=["http://localhost:8888","http://127.0.0.1:8888"]

# 服务器配置
HOST=0.0.0.0
PORT=8888

# DroidBot 录制配置
DROIDBOT_THREADED_RECORDING=false
LOG_LEVEL=INFO
MAX_CONCURRENT_DEVICES=5
RECORDING_TIMEOUT=300
RECORDING_CLEANUP_INTERVAL=60

# 数据存储路径
DATA_DIR=./data
RECORD_DIR=./data/record

# 火山引擎云手机配置（可选）
VOLC_ACCESSKEY=your_access_key
VOLC_SECRETKEY=your_secret_key
VOLC_REGION=cn-north-1
```

### 配置说明

#### 数据库配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| MYSQL_ROOT_PASSWORD | MySQL root 密码 | - |
| MYSQL_DATABASE | 数据库名称 | droidbot_web |
| MYSQL_USER | 数据库用户名 | droidbot_user |
| MYSQL_PASSWORD | 数据库密码 | - |
| MYSQL_HOST | MySQL 服务器地址 | localhost |
| MYSQL_PORT | MySQL 端口 | 3306 |

#### 认证配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| SECRET_KEY | JWT 签名密钥 | - |
| ALGORITHM | JWT 算法 | HS256 |
| ACCESS_TOKEN_EXPIRE_MINUTES | Token 过期时间（分钟） | 30 |

#### 应用配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DEBUG | 调试模式 | False |
| CORS_ORIGINS | 允许的跨域来源 | ["*"] |
| HOST | 服务器监听地址 | 0.0.0.0 |
| PORT | 服务器端口 | 8888 |

#### 录制配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DROIDBOT_THREADED_RECORDING | 是否启用多线程录制 | false |
| LOG_LEVEL | 日志级别 | INFO |
| MAX_CONCURRENT_DEVICES | 最大并发设备数 | 5 |
| RECORDING_TIMEOUT | 录制超时时间（秒） | 300 |
| RECORDING_CLEANUP_INTERVAL | 录制清理间隔（秒） | 60 |

#### 数据存储配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DATA_DIR | 数据目录 | ./data |
| RECORD_DIR | 录制数据目录 | ./data/record |
| TASK_CSV_PATH | 任务 CSV 文件路径 | ./data/task.csv |

#### 火山引擎云手机配置（可选）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| VOLC_ACCESSKEY | 火山引擎 Access Key | - |
| VOLC_SECRETKEY | 火山引擎 Secret Key | - |
| VOLC_REGION | 火山引擎区域 | cn-north-1 |

### 生成 SECRET_KEY

```bash
# 生成数据库密码
openssl rand -base64 32
# 将输出结果粘贴到 MYSQL_ROOT_PASSWORD 和 MYSQL_PASSWORD

# 生成 JWT 密钥
openssl rand -hex 32
# 将输出结果粘贴到 SECRET_KEY
```

## 项目结构

```
web/
├── backend/
│   ├── models/          # SQLModel 数据模型
│   ├── schemas/         # Pydantic 请求/响应模型
│   ├── database/        # 数据库连接配置
│   ├── crud/            # CRUD 操作
│   ├── auth/            # 认证模块
│   ├── routers/         # API 路由
│   ├── services/        # 业务逻辑服务
│   ├── utils/           # 工具函数
│   ├── config.py        # 应用配置
│   └── main.py          # 应用入口
├── static/              # 前端静态资源
│   ├── css/             # 样式文件
│   └── js/              # JavaScript 文件
│       ├── api/         # API 客户端
│       └── components/  # UI 组件
├── templates/           # HTML 模板
├── data/                # 运行时数据目录
├── docker/              # Docker 配置
└── docs/                # 文档
```

## 文档索引

- [用户管理](01-user-management.md) - 用户认证和权限控制
- [任务管理](02-task-management.md) - 任务和录制数据管理
- [云手机管理](03-cloud-device-management.md) - 火山引擎云手机设备管理
- [批次管理](04-batch-management.md) - 批次管理和任务认领
- [前端开发规范](05-frontend-conventions.md) - 前端请求规范和 API 客户端方法列表
