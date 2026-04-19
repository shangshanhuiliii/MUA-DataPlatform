# DroidBot Web 服务部署指南

本文档说明 DroidBot Web 服务的三种部署场景。

## 前置要求

- Docker 20.10+ 和 Docker Compose 2.0+（场景 2、3）
- Python 3.11+（场景 1）

## 环境变量配置

所有场景都需要配置 `.env` 文件。完整的环境变量说明请参考 `.env.example` 文件，其中包含：

- **MySQL 数据库配置**：连接信息和认证
- **JWT 认证配置**：密钥和过期时间
- **应用配置**：调试模式、CORS 等
- **默认管理员配置**：设置 `ADMIN_PASSWORD` 后，执行数据库迁移时会自动创建 admin 用户
- **服务器配置**：监听地址和端口
- **DroidBot 录制配置**：并发数、超时等
- **数据存储路径**：数据和录制目录
- **火山引擎云手机配置**（可选）：云手机服务凭证

## 场景 1：开发调试

适用于本地开发和调试，Web 服务通过命令行启动，便于代码热重载。

**详细步骤请参考：** [`../web/README.md`](../web/README.md)

## 场景 2：本地部署

适用于本地完整部署，MySQL 和 Web 服务均在容器中运行。

### 步骤

```bash
cd deploy/

# 1. 配置环境变量（参考 .env.example）
cp .env.example .env
vim .env  # 至少配置 MYSQL_ROOT_PASSWORD, MYSQL_PASSWORD, SECRET_KEY

# 2. 启动所有服务
docker-compose up -d --build # 使用 --build 会重新使用最新的代码构建

# 3. 初始化数据库（会自动创建默认管理员用户，如果设置了 ADMIN_PASSWORD）
docker-compose exec web bash -c "cd /app/web && alembic upgrade head"

# 4. 验证部署
docker-compose ps
curl http://localhost:8888
```

### 常用命令

```bash
# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 进入容器
docker-compose exec web bash
```

## 场景 3：云服务部署

适用于生产环境，使用已有的 MySQL 服务（如云数据库）。

### 本地操作

```bash
# 0. 设置 VERSION
# export VERSION={v1.0.0}, 参考语义化版本号

# 1. 构建镜像（从项目根目录执行）
docker build --platform linux/amd64 -t droidbot-web:latest -t driodbot-web:${VERSION} -f deploy/Dockerfile .

# 2. 导出镜像为 tar 包
docker save droidbot-web:${VERSION} -o deploy/droidbot-web.tar

# 3. 上传到云服务器
scp deploy/droidbot-web.tar user@your-server:/mua_platform/
scp deploy/docker-compose.cloud.yml user@your-server:/mua_platform/
scp deploy/.env.example user@your-server:/mua_platform/
scp /path/to/adb_key user@your-server:/mua_platform/  # 替换为实际 ADB vendor key 文件路径
```

### MySQL服务创建数据库（首次部署执行）

**首次部署需要先在 MySQL 中创建数据库和用户：**

```bash
# 连接到 MySQL 服务器（使用 root 或管理员账号）
mysql -h your-mysql-host -P 3306 -u root -p
```

```sql
-- 连接到 MySQL 服务器后执行
CREATE DATABASE IF NOT EXISTS droidbot_web CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'droidbot_user'@'%' IDENTIFIED BY 'your-password';
GRANT ALL PRIVILEGES ON droidbot_web.* TO 'droidbot_user'@'%';
FLUSH PRIVILEGES;
```

**然后执行部署步骤：**


### 云服务器部署

```bash
cd /mua_platform/

# 0. 创建 data 目录(可选)
mkdir -p data

# 1. 加载镜像
docker load -i droidbot-web.tar

# 2. 配置环境变量
cp .env.example .env.cloud
vim .env.cloud  # 配置 MYSQL_HOST, SECRET_KEY, DEBUG=False 等

# 3. 启动服务
docker-compose -f docker-compose.cloud.yml --env-file .env.cloud up -d

# 4. 初始化数据库表结构（首次部署必须执行，会自动创建默认管理员用户）
docker-compose -f docker-compose.cloud.yml --env-file .env.cloud exec web bash -c "cd /app/web && alembic upgrade head"

# 5. 验证部署
docker-compose -f docker-compose.cloud.yml --env-file .env.cloud ps
curl http://localhost:8888
```

### 常用命令

```bash
# 查看日志
docker-compose -f docker-compose.cloud.yml logs -f

# 停止服务
docker-compose -f docker-compose.cloud.yml down

# 更新服务（重新上传 tar 包后）
docker load -i droidbot-web.tar
docker-compose -f docker-compose.cloud.yml up -d
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `Dockerfile` | Web 服务镜像构建文件 |
| `docker-compose.yml` | 完整部署编排（场景 2） |
| `docker-compose.cloud.yml` | 云服务部署编排（场景 3） |
| `.env.example` | 环境变量配置模板 |
| `../.dockerignore` | 构建时忽略的文件（位于项目根目录） |

## 故障排查

### 数据库连接失败

```bash
# 检查环境变量
docker-compose exec web env | grep MYSQL

# 测试数据库连接（场景 2）
docker-compose exec mysql mysqladmin ping -h localhost -u root -p

# 测试网络连接（场景 3）
docker-compose -f docker-compose.cloud.yml exec web ping your-mysql-host
```

### 端口冲突

编辑 `.env` 文件，修改端口：
```bash
PORT=8889  # 改为其他端口
MYSQL_PORT=3307  # 改为其他端口（仅场景 2）
```

### 查看详细日志

```bash
# 场景 1
docker-compose -f web/docker/docker-compose.yml logs mysql

# 场景 2
docker-compose logs web

# 场景 3
docker-compose -f docker-compose.cloud.yml logs web
```

## 访问服务

- **Web 界面**: http://localhost:8888
- **API 文档**: http://localhost:8888/docs
