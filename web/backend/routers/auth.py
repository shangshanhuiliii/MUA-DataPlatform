from datetime import timedelta

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from backend.errors import AppError, app_error
from backend.database import get_session
from backend.models.user import User, UserCreate, UserResponse
from backend.schemas.auth import Token, LoginRequest
from backend.auth import (
    verify_password,
    create_access_token,
    create_refresh_token,
    get_current_active_user,
)
from backend.crud import user as user_crud
from backend.auth.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_COOKIE_NAME,
    REFRESH_TOKEN_EXPIRE_DAYS,
    decode_token_with_status,
)
from backend.session_config import workspace_state_manager

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_TOKEN_COOKIE_NAME, path="/api/auth")


def _resolve_user_from_payload(session: Session, payload: Optional[dict]) -> Optional[User]:
    if payload is None:
        return None
    username = payload.get("sub")
    if not username:
        return None

    user = user_crud.get_user_by_username(session, username)
    if user is None or not user.is_active:
        return None
    return user


def _resolve_request_user(session: Session, request: Request) -> Optional[User]:
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        return None

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None

    payload, token_status = decode_token_with_status(token, expected_type="access")
    if token_status != "ok":
        return None
    return _resolve_user_from_payload(session, payload)


def _resolve_refresh_cookie_user(session: Session, request: Request) -> Optional[User]:
    refresh_token_value = request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    if not refresh_token_value:
        return None

    payload, token_status = decode_token_with_status(refresh_token_value, expected_type="refresh")
    if token_status != "ok":
        return None
    return _resolve_user_from_payload(session, payload)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: UserCreate,
    session: Session = Depends(get_session)
):
    """
    用户注册

    - **username**: 用户名（3-50字符，唯一）
    - **email**: 邮箱（唯一）
    - **password**: 密码（至少8字符）
    - **full_name**: 全名（可选）
    """
    # 检查用户名是否已存在
    existing_user = user_crud.get_user_by_username(session, user_create.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )

    # 检查邮箱是否已存在
    existing_email = user_crud.get_user_by_email(session, user_create.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # 创建用户
    db_user = user_crud.create_user(session, user_create)
    return db_user


@router.post("/login", response_model=Token)
async def login(
    login_data: LoginRequest,
    response: Response,
    session: Session = Depends(get_session)
):
    """
    用户登录

    - **username**: 用户名
    - **password**: 密码

    返回 JWT access token
    """
    # 查找用户
    user = user_crud.get_user_by_username(session, login_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 验证密码
    if not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户是否激活
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # 更新最后登录时间
    user_crud.update_last_login(session, user.id)

    # 创建 access token
    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})
    _set_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/token", response_model=Token)
async def login_for_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    """
    OAuth2 兼容的 token 端点（用于 Swagger UI）

    使用表单数据登录，返回 access token
    """
    # 查找用户
    user = user_crud.get_user_by_username(session, form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 验证密码
    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户是否激活
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # 更新最后登录时间
    user_crud.update_last_login(session, user.id)

    # 创建 access token
    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})
    _set_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    获取当前登录用户信息

    需要在请求头中提供有效的 JWT token：
    Authorization: Bearer <token>
    """
    return current_user


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    """
    刷新 JWT access token

    使用 refresh cookie 续签 access token，并刷新浏览器中的 refresh cookie。
    当前实现为无服务端持久化状态的 stateless refresh，不提供旧 refresh token replay 防护。
    """
    refresh_token_value = request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    if not refresh_token_value:
        raise app_error(status.HTTP_401_UNAUTHORIZED, "AUTH_EXPIRED", "Refresh token expired")

    payload, token_status = decode_token_with_status(refresh_token_value, expected_type="refresh")
    if token_status == "expired":
        _clear_refresh_cookie(response)
        raise app_error(status.HTTP_401_UNAUTHORIZED, "AUTH_EXPIRED", "Refresh token expired")
    if payload is None:
        _clear_refresh_cookie(response)
        raise app_error(status.HTTP_401_UNAUTHORIZED, "AUTH_EXPIRED", "Refresh token invalid")

    username = payload.get("sub")
    if not username:
        _clear_refresh_cookie(response)
        raise app_error(status.HTTP_401_UNAUTHORIZED, "AUTH_EXPIRED", "Refresh token invalid")

    user = user_crud.get_user_by_username(session, username)
    if user is None or not user.is_active:
        _clear_refresh_cookie(response)
        raise app_error(status.HTTP_401_UNAUTHORIZED, "AUTH_EXPIRED", "Refresh token user is unavailable")

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    new_refresh_token = create_refresh_token(data={"sub": user.username})
    _set_refresh_cookie(response, new_refresh_token)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    x_workspace_id: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
    session: Session = Depends(get_session),
):
    """
    清理当前浏览器会话的 refresh cookie。

    当前实现不维护服务端 refresh session 状态；logout 会尽力通过 access token
    或 refresh cookie 识别当前用户并释放 workspace，同时清理浏览器侧 refresh cookie。
    """
    current_user = _resolve_request_user(session, request)
    if current_user is None:
        current_user = _resolve_refresh_cookie_user(session, request)

    if x_workspace_id and current_user is not None:
        try:
            workspace = await workspace_state_manager.require_workspace(x_workspace_id, user_id=current_user.id)
        except AppError:
            workspace = None
        if workspace is not None:
            await workspace_state_manager.release_workspace(workspace.workspace_id)

    _clear_refresh_cookie(response)
    return {"message": "Logged out"}
