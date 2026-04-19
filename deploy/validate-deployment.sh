#!/bin/bash
# validate-deployment.sh - 部署前验证脚本

set -e

echo "🔍 DroidBot Docker 部署环境验证"
echo "================================"
echo ""

# 检查 Docker
echo "1. 检查 Docker..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    echo "   ✓ Docker 已安装: $DOCKER_VERSION"
else
    echo "   ✗ Docker 未安装"
    echo "   请访问 https://docs.docker.com/get-docker/ 安装 Docker"
    exit 1
fi

# 检查 Docker Compose
echo ""
echo "2. 检查 Docker Compose..."
if docker compose version &> /dev/null; then
    COMPOSE_VERSION=$(docker compose version)
    echo "   ✓ Docker Compose 已安装: $COMPOSE_VERSION"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_VERSION=$(docker-compose --version)
    echo "   ✓ Docker Compose 已安装: $COMPOSE_VERSION"
else
    echo "   ✗ Docker Compose 未安装"
    echo "   请访问 https://docs.docker.com/compose/install/ 安装 Docker Compose"
    exit 1
fi

# 检查磁盘空间
echo ""
echo "3. 检查磁盘空间..."
AVAILABLE_SPACE=$(df -h . | awk 'NR==2 {print $4}')
echo "   可用空间: $AVAILABLE_SPACE"
echo "   建议至少 2GB 可用空间"

# 检查配置文件
echo ""
echo "4. 检查配置文件..."
if [ -f ".env" ]; then
    echo "   ✓ .env 文件存在"

    # 检查必需的环境变量
    REQUIRED_VARS=("MYSQL_PASSWORD")
    for var in "${REQUIRED_VARS[@]}"; do
        if grep -q "^${var}=" .env && ! grep -q "^${var}=your-" .env; then
            echo "   ✓ $var 已配置"
        else
            echo "   ⚠ $var 未配置或使用默认值"
        fi
    done
else
    echo "   ⚠ .env 文件不存在"
    echo "   请运行: cp .env.example .env"
    echo "   然后编辑 .env 文件配置必要的环境变量"
fi

# 检查 Dockerfile
echo ""
echo "5. 检查部署文件..."
FILES=("Dockerfile" "docker-compose.yml" ".dockerignore")
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✓ $file 存在"
    else
        echo "   ✗ $file 不存在"
    fi
done

echo ""
echo "================================"
echo "✓ 环境验证完成"
echo ""
echo "下一步："
echo "1. 如果 .env 文件不存在，请运行: cp .env.example .env"
echo "2. 编辑 .env 文件，配置数据库密码等必要参数"
echo "3. 选择部署场景："
echo "   - 完整部署: docker-compose up -d"
echo "   - 使用已有 MySQL: docker-compose -f docker-compose.cloud.yml up -d"
