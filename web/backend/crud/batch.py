"""
CRUD operations for Batch model
"""
from typing import Optional, List, Tuple
from sqlmodel import Session, select, func
from datetime import datetime

from backend.models.batch import Batch, DEFAULT_CLAIM_LIMIT_PER_USER
from backend.models.task import Task
from backend.models.task_assignment import TaskAssignment
from backend.models.batch_allocation import BatchAllocation
from backend.models.user import User
from backend.schemas.batch import BatchUpdate
from backend.crud import task as task_crud


def create_batch(session: Session, name: str, description: Optional[str], created_by: int) -> Batch:
    """创建批次"""
    batch = Batch(
        name=name,
        description=description,
        claim_limit_per_user=DEFAULT_CLAIM_LIMIT_PER_USER,
        created_by=created_by,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


def get_batch_by_id(session: Session, batch_id: int) -> Optional[Batch]:
    """根据 ID 获取批次"""
    return session.get(Batch, batch_id)


def get_batches(
    session: Session,
    skip: int = 0,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc"
) -> Tuple[List[Batch], int]:
    """获取批次列表"""
    query = select(Batch)

    # 排序
    if sort_order == "desc":
        query = query.order_by(getattr(Batch, sort_by).desc())
    else:
        query = query.order_by(getattr(Batch, sort_by))

    # 总数
    total = session.exec(select(func.count(Batch.id))).one()

    # 分页
    query = query.offset(skip).limit(limit)
    batches = session.exec(query).all()

    return list(batches), total


def update_batch(
    session: Session,
    batch_id: int,
    batch_update: BatchUpdate
) -> Optional[Batch]:
    """更新批次"""
    batch = session.get(Batch, batch_id)
    if not batch:
        return None

    update_data = batch_update.dict(exclude_unset=True)
    if "claim_limit_per_user" in update_data and update_data["claim_limit_per_user"] is None:
        update_data["claim_limit_per_user"] = DEFAULT_CLAIM_LIMIT_PER_USER

    for field, value in update_data.items():
        setattr(batch, field, value)

    batch.updated_at = datetime.utcnow()
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


def delete_batch(session: Session, batch_id: int) -> bool:
    """删除批次（同时删除批次下的所有任务及关联数据）"""
    batch = session.get(Batch, batch_id)
    if not batch:
        return False

    # 1. 删除批次分配记录
    stmt = select(BatchAllocation).where(BatchAllocation.batch_id == batch_id)
    allocations = session.exec(stmt).all()
    for allocation in allocations:
        session.delete(allocation)
    session.flush()

    # 2. 删除任务分配记录（通过任务关联）
    stmt = select(TaskAssignment).join(Task).where(Task.batch_id == batch_id)
    assignments = session.exec(stmt).all()
    for assignment in assignments:
        session.delete(assignment)
    session.flush()

    # 3. 删除批次下的所有任务
    stmt = select(Task).where(Task.batch_id == batch_id)
    tasks = session.exec(stmt).all()
    for task in tasks:
        session.delete(task)
    session.flush()

    # 4. 删除批次
    session.delete(batch)
    session.commit()
    return True


def get_batch_statistics(session: Session, batch_id: int) -> dict:
    """获取批次统计信息"""
    # 任务总数和各状态任务数
    stmt = select(Task.status, func.count(Task.id)).where(Task.batch_id == batch_id).group_by(Task.status)
    results = session.exec(stmt).all()

    stats = {"total": 0, "pending": 0, "in_progress": 0, "completed": 0}
    for status, count in results:
        stats[status] = count
        stats["total"] += count

    # 分配用户数
    stmt = select(func.count(func.distinct(TaskAssignment.user_id))).join(Task).where(Task.batch_id == batch_id)
    assigned_user_count = session.exec(stmt).one()
    stats["assigned_user_count"] = assigned_user_count

    # 分配用户名列表（从TaskAssignment获取，与assigned_user_count一致）
    stmt = select(func.distinct(User.username)).join(TaskAssignment, TaskAssignment.user_id == User.id).join(Task, TaskAssignment.task_id == Task.id).where(Task.batch_id == batch_id)
    assigned_usernames = session.exec(stmt).all()
    stats["assigned_usernames"] = list(assigned_usernames)

    # 已有批次分配的用户名列表（从BatchAllocation获取）
    stmt = select(func.distinct(User.username)).join(BatchAllocation, BatchAllocation.user_id == User.id).where(BatchAllocation.batch_id == batch_id)
    allocated_usernames = session.exec(stmt).all()
    stats["allocated_usernames"] = list(allocated_usernames)

    return stats


def assign_batch_to_users(session: Session, batch_id: int, user_ids: List[int], assigned_by: int) -> Tuple[int, int, List[str]]:
    """批次级别分配用户"""
    # 获取批次下所有任务
    stmt = select(Task.id).where(Task.batch_id == batch_id)
    task_ids = [task_id for task_id in session.exec(stmt).all()]

    if not task_ids:
        return 0, 0, ["Batch has no tasks"]

    # 调用批量分配任务
    return task_crud.batch_assign_tasks(session, task_ids, user_ids, assigned_by)
