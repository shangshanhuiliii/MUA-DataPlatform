"""
CRUD operations for Task and TaskAssignment models
"""
from typing import Optional, List, Tuple, Dict
from collections import defaultdict
from sqlmodel import Session, select, func
from sqlalchemy import cast, String
from datetime import datetime, timedelta

from backend.models.task import Task
from backend.models.task_assignment import TaskAssignment
from backend.models.recording import Recording
from backend.models.user import User

ALLOWED_TASK_SORT_FIELDS = (
    "id",
    "description",
    "status",
    "created_at",
    "assigned_count",
    "recording_count",
)


def create_task(session: Session, description: str, created_by: int, batch_id: Optional[int] = None) -> Task:
    """创建任务"""
    task = Task(
        description=description,
        batch_id=batch_id,
        created_by=created_by,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def get_task_by_id(session: Session, task_id: int) -> Optional[Task]:
    """根据 ID 获取任务"""
    return session.get(Task, task_id)


def get_tasks(
    session: Session,
    user_id: Optional[int] = None,
    is_admin: bool = False,
    status: Optional[str] = None,
    batch_id: Optional[int] = None,
    keyword: Optional[str] = None,
    assigned_user_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc"
) -> Tuple[List[Task], int]:
    """获取任务列表

    Args:
        user_id: 用户 ID（非管理员时必须）
        is_admin: 是否为管理员
        status: 按状态筛选
        batch_id: 按批次筛选
        assigned_user_id: 按分配用户筛选（仅管理员）
        date_from: 创建时间起始（仅管理员）
        date_to: 创建时间截止（仅管理员）
        skip: 跳过数量
        limit: 返回数量

    Returns:
        (任务列表, 总数)
    """
    statement = select(Task)

    # 非管理员只能看到分配给自己的任务
    if not is_admin and user_id:
        statement = statement.join(TaskAssignment).where(TaskAssignment.user_id == user_id)

    if status:
        statement = statement.where(Task.status == status)

    if batch_id is not None:
        statement = statement.where(Task.batch_id == batch_id)

    if keyword:
        statement = statement.where(
            Task.description.ilike(f"%{keyword}%") | cast(Task.id, String).ilike(f"%{keyword}%")
        )

    # 用户筛选（仅管理员可按任意用户筛选）
    if is_admin and assigned_user_id:
        statement = statement.join(TaskAssignment, TaskAssignment.task_id == Task.id).where(
            TaskAssignment.user_id == assigned_user_id
        )

    if date_from:
        statement = statement.where(Task.created_at >= date_from)
    if date_to:
        next_day = date_to + timedelta(days=1)
        statement = statement.where(Task.created_at < next_day)

    # 获取总数
    count_stmt = select(func.count()).select_from(statement.subquery())
    total = session.exec(count_stmt).one()

    recording_count_subquery = (
        select(func.count(Recording.id))
        .where(Recording.task_id == Task.id)
        .correlate(Task)
        .scalar_subquery()
    )
    assigned_count_subquery = (
        select(func.count(TaskAssignment.id))
        .where(TaskAssignment.task_id == Task.id)
        .correlate(Task)
        .scalar_subquery()
    )

    sort_columns = {
        "id": Task.id,
        "description": Task.description,
        "status": Task.status,
        "created_at": Task.created_at,
        "assigned_count": assigned_count_subquery,
        "recording_count": recording_count_subquery
    }
    sort_by = sort_by if sort_by in sort_columns else "created_at"
    sort_column = sort_columns[sort_by]
    sort_desc = (sort_order or "desc").lower() != "asc"
    primary_order = sort_column.desc() if sort_desc else sort_column.asc()
    secondary_order = Task.id.desc() if sort_desc else Task.id.asc()

    # 排序 + 分页
    statement = (
        statement
        .order_by(primary_order, secondary_order)
        .offset(skip)
        .limit(limit)
    )
    tasks = list(session.exec(statement).all())

    return tasks, total


def update_task(
    session: Session,
    task_id: int,
    description: Optional[str] = None,
    status: Optional[str] = None,
    batch_id: Optional[int] = None
) -> Optional[Task]:
    """更新任务"""
    task = get_task_by_id(session, task_id)
    if not task:
        return None

    if description is not None:
        task.description = description
    if status is not None:
        task.status = status
    if batch_id is not None:
        task.batch_id = batch_id
    task.updated_at = datetime.utcnow()

    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def delete_task(session: Session, task_id: int) -> bool:
    """删除任务"""
    task = get_task_by_id(session, task_id)
    if not task:
        return False

    # 删除关联的分配记录
    session.exec(select(TaskAssignment).where(TaskAssignment.task_id == task_id))
    for assignment in session.exec(select(TaskAssignment).where(TaskAssignment.task_id == task_id)).all():
        session.delete(assignment)

    session.delete(task)
    session.commit()
    return True


def get_task_assigned_users(session: Session, task_id: int) -> List[User]:
    """获取任务分配的用户列表"""
    statement = (
        select(User)
        .join(TaskAssignment, User.id == TaskAssignment.user_id)
        .where(TaskAssignment.task_id == task_id)
    )
    return list(session.exec(statement).all())


def get_tasks_assigned_users_map(
    session: Session,
    task_ids: List[int]
) -> Dict[int, List[User]]:
    """批量获取任务的分配用户"""
    if not task_ids:
        return {}

    statement = (
        select(TaskAssignment.task_id, User)
        .join(User, User.id == TaskAssignment.user_id)
        .where(TaskAssignment.task_id.in_(task_ids))
        .order_by(TaskAssignment.task_id)
    )

    result: Dict[int, List[User]] = defaultdict(list)
    for task_id, user in session.exec(statement):
        result[task_id].append(user)
    return result


def get_task_recording_count(session: Session, task_id: int) -> int:
    """获取任务的录制数量"""
    statement = select(func.count()).where(Recording.task_id == task_id)
    return session.exec(statement).one()


def get_tasks_recording_counts(session: Session, task_ids: List[int]) -> Dict[int, int]:
    """批量获取任务的录制数量"""
    if not task_ids:
        return {}

    statement = (
        select(Recording.task_id, func.count())
        .where(Recording.task_id.in_(task_ids))
        .group_by(Recording.task_id)
    )
    counts = session.exec(statement).all()
    return {task_id: count for task_id, count in counts}


def assign_task(
    session: Session,
    task_id: int,
    user_ids: List[int],
    assigned_by: int
) -> List[int]:
    """分配任务给用户（替换现有分配）"""
    # 删除现有分配
    for assignment in session.exec(select(TaskAssignment).where(TaskAssignment.task_id == task_id)).all():
        session.delete(assignment)

    # 创建新分配
    for user_id in user_ids:
        assignment = TaskAssignment(
            task_id=task_id,
            user_id=user_id,
            assigned_by=assigned_by,
            assigned_at=datetime.utcnow()
        )
        session.add(assignment)

    session.commit()
    return user_ids


def unassign_task(session: Session, task_id: int, user_id: int) -> bool:
    """取消任务分配"""
    statement = select(TaskAssignment).where(
        TaskAssignment.task_id == task_id,
        TaskAssignment.user_id == user_id
    )
    assignment = session.exec(statement).first()
    if not assignment:
        return False

    session.delete(assignment)
    session.commit()
    return True


def is_task_assigned_to_user(session: Session, task_id: int, user_id: int) -> bool:
    """检查任务是否分配给用户"""
    statement = select(TaskAssignment).where(
        TaskAssignment.task_id == task_id,
        TaskAssignment.user_id == user_id
    )
    return session.exec(statement).first() is not None


def bulk_create_tasks(
    session: Session,
    descriptions: List[str],
    created_by: int,
    batch_id: Optional[int] = None
) -> Tuple[int, int, List[str]]:
    """批量创建任务

    Returns:
        (成功数, 失败数, 错误列表)
    """
    success = 0
    failed = 0
    errors = []

    for i, desc in enumerate(descriptions):
        desc = desc.strip()
        if not desc:
            failed += 1
            errors.append(f"Task {i+1}: Description is empty")
            continue
        if len(desc) > 1000:
            failed += 1
            errors.append(f"Task {i+1}: Description too long (max 1000 characters)")
            continue

        try:
            task = Task(
                description=desc,
                batch_id=batch_id,
                created_by=created_by,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.add(task)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(f"Task {i+1}: {str(e)}")

    session.commit()
    return success, failed, errors


def batch_delete_tasks(
    session: Session,
    task_ids: List[int]
) -> Tuple[int, int, List[str]]:
    """批量删除任务

    Returns:
        (成功数, 失败数, 错误列表)
    """
    success = 0
    failed = 0
    errors = []

    for task_id in task_ids:
        task = get_task_by_id(session, task_id)
        if not task:
            failed += 1
            errors.append(f"Task {task_id}: Not found")
            continue

        # 检查是否有关联的录制数据
        recording_count = get_task_recording_count(session, task_id)
        if recording_count > 0:
            failed += 1
            errors.append(f"Task {task_id}: Has {recording_count} recordings")
            continue

        # 删除关联的分配记录
        for assignment in session.exec(select(TaskAssignment).where(TaskAssignment.task_id == task_id)).all():
            session.delete(assignment)

        session.delete(task)
        success += 1

    session.commit()
    return success, failed, errors


def batch_assign_tasks(
    session: Session,
    task_ids: List[int],
    user_ids: List[int],
    assigned_by: int
) -> Tuple[int, int, List[str]]:
    """批量分配任务给用户

    user_ids 为空列表时，取消所有分配
    user_ids 非空时，增量添加分配（保留现有分配）

    Returns:
        (成功数, 失败数, 错误列表)
    """
    # 先验证所有用户是否存在
    for user_id in user_ids:
        user = session.get(User, user_id)
        if not user:
            return 0, len(task_ids), [f"User {user_id} not found"]

    success = 0
    failed = 0
    errors = []

    for task_id in task_ids:
        task = get_task_by_id(session, task_id)
        if not task:
            failed += 1
            errors.append(f"Task {task_id}: Not found")
            continue

        try:
            if not user_ids:
                # 空列表：取消所有分配
                for assignment in session.exec(select(TaskAssignment).where(TaskAssignment.task_id == task_id)).all():
                    session.delete(assignment)
            else:
                # 非空列表：增量添加（跳过已存在的分配）
                for user_id in user_ids:
                    existing = session.exec(
                        select(TaskAssignment).where(
                            TaskAssignment.task_id == task_id,
                            TaskAssignment.user_id == user_id
                        )
                    ).first()
                    if not existing:
                        assignment = TaskAssignment(
                            task_id=task_id,
                            user_id=user_id,
                            assigned_by=assigned_by,
                            assigned_at=datetime.utcnow()
                        )
                        session.add(assignment)

            success += 1
        except Exception as e:
            failed += 1
            errors.append(f"Task {task_id}: {str(e)}")

    session.commit()
    return success, failed, errors


def batch_move_tasks(
    session: Session,
    task_ids: List[int],
    target_batch_id: Optional[int]
) -> Tuple[int, int, List[str]]:
    """批量移动任务到其他批次

    Returns:
        (成功数, 失败数, 错误列表)
    """
    success = 0
    failed = 0
    errors = []

    for task_id in task_ids:
        task = get_task_by_id(session, task_id)
        if not task:
            failed += 1
            errors.append(f"Task {task_id}: Not found")
            continue

        try:
            task.batch_id = target_batch_id
            task.updated_at = datetime.utcnow()
            session.add(task)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(f"Task {task_id}: {str(e)}")

    session.commit()
    return success, failed, errors
