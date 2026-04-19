"""
Database connection configuration
"""
from sqlmodel import create_engine, Session, SQLModel
from sqlalchemy.orm import sessionmaker
import os

# 数据库配置
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER", "droidbot")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "droidbot_web")

# 构建数据库 URL
# 使用 pymysql 作为同步驱动（Alembic 需要）
DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"

# 创建引擎
engine = create_engine(
    DATABASE_URL,
    echo=True,  # 开发环境打印 SQL，生产环境设为 False
    pool_pre_ping=True,  # 连接池预检查
    pool_recycle=3600,  # 1小时回收连接
)

# 创建 SessionLocal 类
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


def create_db_and_tables():
    """创建所有表"""
    SQLModel.metadata.create_all(engine)


def get_session():
    """获取数据库会话（依赖注入）"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
