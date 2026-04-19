## 环境配置

以 uv 管理的虚拟环境为例：

```bash
# 使用 python>=3.11版本
uv venv --python=3.11

source .venv/bin/activate

# 基础安装（不含 web 服务依赖）
uv pip install -e .

# 包含 web 服务依赖
uv pip install -e ".[web]"
```

## 录制编辑工具（Web服务）启动

参考 `web/README.md`.

## 服务部署

参考 `deploy/README.md`
