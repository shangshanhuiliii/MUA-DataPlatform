"""
User management API routes
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session

from backend.database import get_session
from backend.models.user import User, UserCreate, UserUpdate, UserResponse
from backend.auth import get_current_active_user, get_current_superuser
from backend.crud import user as user_crud

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    is_active: bool | None = Query(None, description="筛选激活状态"),
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """
    获取用户列表

    - 管理员：返回所有用户
    - 普通用户：只返回自己的信息
    - **skip**: 跳过的记录数（分页）
    - **limit**: 返回的最大记录数
    - **is_active**: 筛选激活状态（可选）
    """
    if current_user.is_superuser:
        # 管理员返回所有用户
        users = user_crud.get_users(session, skip=skip, limit=limit, is_active=is_active)
    else:
        # 普通用户只返回自己的信息
        users = [current_user]

    return users


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """
    获取指定用户信息

    - 普通用户只能查看自己的信息
    - 管理员可以查看任何用户的信息
    """
    # 检查权限：只能查看自己或管理员可以查看所有
    if user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    user = user_crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_create: UserCreate,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """
    创建新用户（仅管理员）

    - **username**: 用户名（3-50字符，唯一）
    - **email**: 邮箱（唯一）
    - **password**: 密码（至少8字符）
    - **full_name**: 全名（可选）
    - **is_superuser**: 是否为管理员
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


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """
    更新用户信息

    - 普通用户只能更新自己的信息（不能修改 is_superuser）
    - 管理员可以更新任何用户的信息
    """
    # 检查权限
    if user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    # 获取目标用户
    target_user = user_crud.get_user_by_id(session, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # 普通用户不能修改 is_superuser 状态（检查是否尝试改变值）
    if not current_user.is_superuser and user_update.is_superuser is not None:
        if user_update.is_superuser != target_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify superuser status"
            )

    # 更新用户
    updated_user = user_crud.update_user(session, user_id, user_update)
    return updated_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """
    删除用户（仅管理员）

    - 不能删除自己
    - 不能删除有关联数据的用户
    """
    # 不能删除自己
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )

    # 删除用户
    success, references = user_crud.delete_user(session, user_id)

    if references:
        # 构建友好的错误信息
        ref_messages = []
        if "task_assignments" in references:
            ref_messages.append(f"{references['task_assignments']} 条任务分配记录")
        if "recordings" in references:
            ref_messages.append(f"{references['recordings']} 条录制记录")

        detail = f"无法删除该用户，存在关联数据：{'、'.join(ref_messages)}。请先处理这些数据后再删除用户。"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return None
