"""
CRUD operations for User model
"""
from typing import Optional, List, Dict
from sqlmodel import Session, select, func
from datetime import datetime

from backend.models.user import User, UserCreate, UserUpdate
from backend.models.task_assignment import TaskAssignment
from backend.models.recording import Recording
from backend.auth.security import get_password_hash


def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    """根据 ID 获取用户"""
    return session.get(User, user_id)


def get_user_by_username(session: Session, username: str) -> Optional[User]:
    """根据用户名获取用户"""
    statement = select(User).where(User.username == username)
    return session.exec(statement).first()


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    """根据邮箱获取用户"""
    statement = select(User).where(User.email == email)
    return session.exec(statement).first()


def get_users(
    session: Session,
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None
) -> List[User]:
    """获取用户列表"""
    statement = select(User)

    if is_active is not None:
        statement = statement.where(User.is_active == is_active)

    statement = statement.offset(skip).limit(limit)
    return list(session.exec(statement).all())


def create_user(session: Session, user_create: UserCreate) -> User:
    """创建用户"""
    # 创建用户对象
    db_user = User(
        username=user_create.username,
        email=user_create.email,
        password_hash=get_password_hash(user_create.password),
        full_name=user_create.full_name,
        is_superuser=user_create.is_superuser,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def update_user(
    session: Session,
    user_id: int,
    user_update: UserUpdate
) -> Optional[User]:
    """更新用户"""
    db_user = get_user_by_id(session, user_id)
    if not db_user:
        return None

    # 更新字段
    update_data = user_update.dict(exclude_unset=True)

    # 如果包含密码，需要哈希处理
    if 'password' in update_data:
        password = update_data.pop('password')
        if password:  # 只有当密码不为空时才更新
            db_user.password_hash = get_password_hash(password)

    for field, value in update_data.items():
        setattr(db_user, field, value)

    db_user.updated_at = datetime.utcnow()

    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_references(session: Session, user_id: int) -> Dict[str, int]:
    """检查用户的关联数据数量"""
    references = {}

    # 检查任务分配（作为被分配人）
    assignment_count = session.exec(
        select(func.count(TaskAssignment.id)).where(TaskAssignment.user_id == user_id)
    ).one()
    if assignment_count > 0:
        references["task_assignments"] = assignment_count

    # 检查录制记录
    recording_count = session.exec(
        select(func.count(Recording.id)).where(Recording.recorded_by == user_id)
    ).one()
    if recording_count > 0:
        references["recordings"] = recording_count

    return references


def delete_user(session: Session, user_id: int) -> tuple[bool, Optional[Dict[str, int]]]:
    """
    删除用户

    Returns:
        (True, None) - 删除成功
        (False, None) - 用户不存在
        (False, references) - 存在关联数据，无法删除
    """
    db_user = get_user_by_id(session, user_id)
    if not db_user:
        return False, None

    # 检查关联数据
    references = get_user_references(session, user_id)
    if references:
        return False, references

    session.delete(db_user)
    session.commit()
    return True, None


def update_last_login(session: Session, user_id: int) -> None:
    """更新最后登录时间"""
    db_user = get_user_by_id(session, user_id)
    if db_user:
        db_user.last_login = datetime.utcnow()
        session.add(db_user)
        session.commit()
