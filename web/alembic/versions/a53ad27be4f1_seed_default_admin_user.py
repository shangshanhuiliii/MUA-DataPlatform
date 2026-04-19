"""seed_default_admin_user

Revision ID: a53ad27be4f1
Revises: c6c55efd4bea
Create Date: 2026-01-21 10:57:21.769971

"""
from typing import Sequence, Union
from datetime import datetime
import os

from alembic import op
import sqlalchemy as sa
from passlib.context import CryptContext


# revision identifiers, used by Alembic.
revision: str = 'a53ad27be4f1'
down_revision: Union[str, Sequence[str], None] = 'c6c55efd4bea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 密码哈希（与 backend/auth/security.py 保持一致）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def upgrade() -> None:
    """创建默认管理员用户（如果设置了 ADMIN_PASSWORD 环境变量）"""
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        print("ℹ️  ADMIN_PASSWORD not set, skipping default admin creation")
        return

    admin_email = os.getenv("ADMIN_EMAIL", "admin@localhost")

    # 检查 admin 用户是否已存在
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT id FROM users WHERE username = :username"),
        {"username": "admin"}
    ).fetchone()

    if result:
        print("ℹ️  Admin user already exists, skipping")
        return

    # 哈希密码
    password_bytes = admin_password.encode('utf-8')[:72]
    password_hash = pwd_context.hash(password_bytes)
    now = datetime.utcnow()

    # 插入管理员用户
    conn.execute(
        sa.text("""
            INSERT INTO users (username, email, password_hash, full_name, is_active, is_superuser, created_at, updated_at)
            VALUES (:username, :email, :password_hash, :full_name, :is_active, :is_superuser, :created_at, :updated_at)
        """),
        {
            "username": "admin",
            "email": admin_email,
            "password_hash": password_hash,
            "full_name": "Administrator",
            "is_active": True,
            "is_superuser": True,
            "created_at": now,
            "updated_at": now,
        }
    )
    print(f"✅ Default admin user 'admin' created with email: {admin_email}")


def downgrade() -> None:
    """删除默认管理员用户"""
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM users WHERE username = :username"),
        {"username": "admin"}
    )
    print("🗑️  Default admin user 'admin' deleted")
