# DroidBot Web

基于 FastAPI 的 Web 服务，用于管理 Android 自动化任务的录制和回放。

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置密码和密钥：

```bash
# 生成数据库密码
openssl rand -base64 32
# 将输出结果粘贴到 MYSQL_ROOT_PASSWORD 和 MYSQL_PASSWORD

# 生成 JWT 密钥
openssl rand -hex 32
# 将输出结果粘贴到 SECRET_KEY
```

如需使用云手机功能，配置火山引擎凭证：
```bash
VOLC_ACCESSKEY=your_access_key
VOLC_SECRETKEY=your_secret_key
VOLC_REGION=cn-north-1
```

### 2. 启动 MySQL

```bash
docker-compose -f docker/docker-compose.yml up -d

# 等待健康检查通过
docker-compose -f docker/docker-compose.yml ps
```

### 3. 安装依赖并启动

```bash
# 在项目更目录下
cd ${project_root} 

# 使用 uv 初始化虚拟环境
uv pip install -e ".[web]"

# 进入 web 目录下
cd web

# 第一次启动时初始化 MySQL 服务
alembic upgrade head
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8888
```

访问: http://localhost:8888

## 常用命令

```bash
# Docker 管理
docker-compose -f docker/docker-compose.yml up -d      # 启动
docker-compose -f docker/docker-compose.yml logs -f    # 查看日志
docker-compose -f docker/docker-compose.yml down       # 停止
docker-compose -f docker/docker-compose.yml down -v    # 停止并删除数据（危险）

# 数据库迁移
alembic revision --autogenerate -m "描述"
alembic upgrade head
alembic downgrade -1

# 数据库备份/恢复
docker exec droidbot_mysql mysqldump -u root -p droidbot_web > backup.sql
docker exec -i droidbot_mysql mysql -u root -p droidbot_web < backup.sql

# 开发服务器
uvicorn backend.main:app --reload --port 8888
```

## 故障排查

```bash
# 检查 MySQL 容器
docker-compose -f docker/docker-compose.yml ps
docker-compose -f docker/docker-compose.yml logs mysql

# 测试数据库连接
mysql -h 127.0.0.1 -P 3306 -u droidbot_user -p
docker exec -it droidbot_mysql mysql -u root -p

# 检查端口占用
lsof -i :3306
lsof -i :8888
```

## 文档

- [系统概述](docs/00-overview.md) - 技术栈、环境配置
- [用户管理](docs/01-user-management.md) - 用户认证和权限
- [任务管理](docs/02-task-management.md) - 任务和录制数据
- [云手机管理](docs/03-cloud-device-management.md) - 火山引擎云手机设备管理
