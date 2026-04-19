from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from backend.errors import app_error
from backend.database import get_session
from backend.models.user import User
from backend.auth.security import decode_token_with_status

# OAuth2 密码流
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
oauth2_optional_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session)
) -> User:
    """获取当前登录用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload, token_status = decode_token_with_status(token, expected_type="access")
    if token_status == "expired":
        raise app_error(
            status.HTTP_401_UNAUTHORIZED,
            "AUTH_EXPIRED",
            "Access token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload is None:
        raise credentials_exception

    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception

    # 从数据库查询用户
    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()

    if user is None:
        raise credentials_exception

    return user


async def get_optional_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_optional_scheme),
    session: Session = Depends(get_session),
) -> Optional[User]:
    authorization = request.headers.get("Authorization")
    if not token:
        if authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None

    payload, token_status = decode_token_with_status(token, expected_type="access")
    if token_status == "expired":
        raise app_error(
            status.HTTP_401_UNAUTHORIZED,
            "AUTH_EXPIRED",
            "Access token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username: Optional[str] = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """获取当前激活的用户"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """获取当前超级管理员用户"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user
