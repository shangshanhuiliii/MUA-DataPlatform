"""
CRUD operations for Recording model
"""
from typing import Optional, List, Tuple
from sqlmodel import Session, select, func
from sqlalchemy import cast, String
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta

from backend.models.recording import Recording
from backend.models.task import Task
from backend.models.user import User

ALLOWED_RECORDING_SORT_FIELDS = (
    "id",
    "directory_name",
    "task_description",
    "created_at",
    "recorded_by_username",
)


def create_recording(
    session: Session,
    task_id: int,
    directory_name: str,
    recorded_by: int
) -> Recording:
    """创建录制记录"""
    recording, _ = ensure_recording(
        session,
        task_id=task_id,
        directory_name=directory_name,
        recorded_by=recorded_by
    )
    return recording


def ensure_recording(
    session: Session,
    task_id: int,
    directory_name: str,
    recorded_by: int
) -> Tuple[Recording, bool]:
    """按目录名幂等创建录制记录"""
    existing = get_recording_by_directory(session, directory_name)
    if existing:
        return existing, False

    recording = Recording(
        task_id=task_id,
        directory_name=directory_name,
        recorded_by=recorded_by,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    session.add(recording)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = get_recording_by_directory(session, directory_name)
        if existing:
            return existing, False
        raise

    session.refresh(recording)
    return recording, True


def get_recording_by_id(session: Session, recording_id: int) -> Optional[Recording]:
    """根据 ID 获取录制记录"""
    return session.get(Recording, recording_id)


def get_recordings(
    session: Session,
    user_id: Optional[int] = None,
    is_admin: bool = False,
    task_id: Optional[int] = None,
    keyword: Optional[str] = None,
    batch_id: Optional[int] = None,
    recorded_by_filter: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[Recording], int]:
    """获取录制记录列表

    Args:
        user_id: 用户 ID（非管理员时必须）
        is_admin: 是否为管理员
        task_id: 按任务筛选
        batch_id: 按批次筛选（通过 Task 关联）
        recorded_by_filter: 按录制人筛选（仅管理员）
        date_from: 录制时间起始
        date_to: 录制时间截止
        skip: 跳过数量
        limit: 返回数量
        sort_by: 排序字段
        sort_order: asc/desc

    Returns:
        (录制列表, 总数)
    """
    statement = select(Recording)

    sort_columns = {
        "id": Recording.id,
        "directory_name": Recording.directory_name,
        "task_description": Task.description,
        "created_at": Recording.created_at,
        "recorded_by_username": User.username,
    }
    sort_by = sort_by if sort_by in sort_columns else "created_at"
    sort_column = sort_columns[sort_by]
    sort_desc = (sort_order or "desc").lower() != "asc"

    # 跟踪已 join 的表，避免重复 join
    task_joined = False
    user_joined = False

    if sort_by == "task_description":
        statement = statement.join(Task, Task.id == Recording.task_id)
        task_joined = True
    elif sort_by == "recorded_by_username":
        statement = statement.join(User, User.id == Recording.recorded_by)
        user_joined = True

    # keyword 搜索时需要 join Task
    if keyword and not task_joined:
        statement = statement.join(Task, Task.id == Recording.task_id)
        task_joined = True

    # batch_id 筛选时需要 join Task
    if batch_id is not None and not task_joined:
        statement = statement.join(Task, Task.id == Recording.task_id)
        task_joined = True

    # 非管理员只能看到自己的录制
    if not is_admin and user_id:
        statement = statement.where(Recording.recorded_by == user_id)

    if task_id:
        statement = statement.where(Recording.task_id == task_id)

    if keyword:
        statement = statement.where(
            Recording.directory_name.ilike(f"%{keyword}%")
            | Task.description.ilike(f"%{keyword}%")
            | cast(Recording.id, String).ilike(f"%{keyword}%")
        )

    if batch_id is not None:
        statement = statement.where(Task.batch_id == batch_id)

    # 录制人筛选（仅管理员有意义；非管理员已被上面的 recorded_by == user_id 过滤）
    if is_admin and recorded_by_filter is not None:
        statement = statement.where(Recording.recorded_by == recorded_by_filter)

    if date_from:
        statement = statement.where(Recording.created_at >= date_from)
    if date_to:
        next_day = date_to + timedelta(days=1)
        statement = statement.where(Recording.created_at < next_day)

    # 获取总数
    count_stmt = select(func.count()).select_from(statement.order_by(None).subquery())
    total = session.exec(count_stmt).one()

    primary_order = sort_column.desc() if sort_desc else sort_column.asc()
    secondary_order = Recording.id.desc() if sort_desc else Recording.id.asc()

    # 排序 + 分页
    statement = statement.order_by(primary_order, secondary_order).offset(skip).limit(limit)
    recordings = list(session.exec(statement).all())

    return recordings, total


def update_recording(
    session: Session,
    recording_id: int,
    directory_name: Optional[str] = None
) -> Optional[Recording]:
    """更新录制记录"""
    recording = get_recording_by_id(session, recording_id)
    if not recording:
        return None

    if directory_name is not None:
        recording.directory_name = directory_name
    recording.updated_at = datetime.utcnow()

    session.add(recording)
    session.commit()
    session.refresh(recording)
    return recording


def delete_recording(session: Session, recording_id: int) -> bool:
    """删除录制记录"""
    recording = get_recording_by_id(session, recording_id)
    if not recording:
        return False

    session.delete(recording)
    session.commit()
    return True


def get_recording_with_details(
    session: Session,
    recording_id: int
) -> Optional[dict]:
    """获取录制记录详情（包含任务和用户信息）"""
    recording = get_recording_by_id(session, recording_id)
    if not recording:
        return None

    task = session.get(Task, recording.task_id)
    user = session.get(User, recording.recorded_by)

    return {
        "recording": recording,
        "task_description": task.description if task else "",
        "recorded_by_username": user.username if user else ""
    }


def get_task_description(session: Session, task_id: int) -> str:
    """获取任务描述"""
    task = session.get(Task, task_id)
    return task.description if task else ""


def get_username(session: Session, user_id: int) -> str:
    """获取用户名"""
    user = session.get(User, user_id)
    return user.username if user else ""


def get_recording_by_directory(session: Session, directory_name: str) -> Optional[Recording]:
    """根据目录名获取录制记录"""
    statement = select(Recording).where(Recording.directory_name == directory_name)
    return session.exec(statement).first()
