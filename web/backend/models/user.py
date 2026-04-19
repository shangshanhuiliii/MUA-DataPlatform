"""
User model using SQLModel
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    """用户模型 - 同时用于数据库和 API"""
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, max_length=50, index=True)
    email: str = Field(unique=True, max_length=100, index=True)
    password_hash: str = Field(max_length=255)
    full_name: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = Field(default=True, index=True)
    is_superuser: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None


class UserCreate(SQLModel):
    """用户创建请求模型"""
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(max_length=100)
    password: str = Field(min_length=8, max_length=100)
    full_name: Optional[str] = None
    is_superuser: bool = False


class UserUpdate(SQLModel):
    """用户更新请求模型"""
    email: Optional[str] = Field(default=None, max_length=100)
    password: Optional[str] = Field(default=None, min_length=8, max_length=100)
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None


class UserResponse(SQLModel):
    """用户响应模型（不包含密码）"""
    id: int
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime]
