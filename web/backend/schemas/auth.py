"""
Authentication schemas
"""
from pydantic import BaseModel


class Token(BaseModel):
    """Token 响应模型"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None


class TokenData(BaseModel):
    """Token 数据模型"""
    username: str | None = None


class LoginRequest(BaseModel):
    """登录请求模型"""
    username: str
    password: str
