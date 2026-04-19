# DroidBot Web Service Docker Image
# 使用官方 uv 镜像（基于 Python 3.11）
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# 设置工作目录
WORKDIR /app

# 使用阿里云镜像源（国内网络）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖（包括 ADB）
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    wget \
    unzip \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    adb \
    && rm -rf /var/lib/apt/lists/*


# 复制项目文件
COPY . .

RUN export UV_HTTP_TIMEOUT=300 && uv pip install --system --no-cache -e .[web] \
    -i http://pypi.hobot.cc/hobot-local/simple \
    --extra-index-url=http://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host pypi.hobot.cc \
    --trusted-host mirrors.aliyun.com

# 暴露端口（默认 8888，可通过环境变量配置）
EXPOSE 8888

# 设置工作目录到 web
WORKDIR /app/web

# 启动命令
CMD ["python", "main.py"]
