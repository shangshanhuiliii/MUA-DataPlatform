"""
CRUD operations for BatchAllocation model
"""
from typing import Optional, List, Tuple
from sqlmodel import Session, select, func
from datetime import datetime

from backend.models.batch import Batch, DEFAULT_CLAIM_LIMIT_PER_USER
from backend.models.batch_allocation import BatchAllocation
from backend.models.task import Task
from backend.models.task_assignment import TaskAssignment
from backend.models.user import User


def _get_claim_limit_per_user(batch: Batch) -> int:
    """获取批次认领上限，兼容历史空值数据。"""
    return (
        batch.claim_limit_per_user
        if batch.claim_limit_per_user is not None
        else DEFAULT_CLAIM_LIMIT_PER_USER
    )


def allocate_batch_to_users(
    session: Session,
    batch_id: int,
    user_ids: List[int],
    allocated_by: int
) -> Tuple[int, int, List[str]]:
    """为多个用户分配批次"""
    success = 0
    failed = 0
    errors = []

    # 删除不在新分配列表中的用户分配记录
    existing_allocations = session.exec(
        select(BatchAllocation).where(BatchAllocation.batch_id == batch_id)
    ).all()
    for allocation in existing_allocations:
        if allocation.user_id not in user_ids:
            session.delete(allocation)

    # 验证用户存在
    for user_id in user_ids:
        user = session.get(User, user_id)
        if not user:
            errors.append(f"User {user_id} not found")
            failed += 1
            continue

        # 检查是否已存在分配
        existing = session.exec(
            select(BatchAllocation)
            .where(BatchAllocation.batch_id == batch_id)
            .where(BatchAllocation.user_id == user_id)
        ).first()

        if existing:
            # 刷新分配时间
            existing.allocated_at = datetime.utcnow()
            session.add(existing)
            success += 1
        else:
            # 创建新分配关系
            allocation = BatchAllocation(
                batch_id=batch_id,
                user_id=user_id,
                allocated_by=allocated_by,
                allocated_at=datetime.utcnow()
            )
            session.add(allocation)
            success += 1

    session.commit()
    return success, failed, errors


def get_user_allocation_stats(
    session: Session,
    batch_id: int,
    user_id: int
) -> Optional[dict]:
    """获取用户在指定批次的领取限额统计"""
    batch = session.get(Batch, batch_id)
    if not batch:
        return None

    allocation = session.exec(
        select(BatchAllocation)
        .where(BatchAllocation.batch_id == batch_id)
        .where(BatchAllocation.user_id == user_id)
    ).first()

    if not allocation:
        return None

    # 计算当前占用数：已认领且未完成的任务
    occupied = session.exec(
        select(func.count(TaskAssignment.id))
        .join(Task, TaskAssignment.task_id == Task.id)
        .where(TaskAssignment.user_id == user_id)
        .where(Task.batch_id == batch_id)
        .where(Task.status != 'completed')
    ).one()

    claim_limit_per_user = _get_claim_limit_per_user(batch)

    return {
        'claim_limit_per_user': claim_limit_per_user,
        'occupied': occupied,
        'available': max(claim_limit_per_user - occupied, 0)
    }


def claim_task(
    session: Session,
    task_id: int,
    user_id: int,
    batch_id: int
) -> Tuple[bool, str]:
    """认领任务（带并发控制）"""
    batch = session.get(Batch, batch_id)
    if not batch:
        return False, "批次不存在"

    # 1. 获取分配记录
    allocation = session.exec(
        select(BatchAllocation)
        .where(BatchAllocation.batch_id == batch_id)
        .where(BatchAllocation.user_id == user_id)
    ).first()

    if not allocation:
        return False, "无分配记录"

    # 2. 计算当前占用数（未完成任务数）
    occupied = session.exec(
        select(func.count(TaskAssignment.id))
        .join(Task, TaskAssignment.task_id == Task.id)
        .where(TaskAssignment.user_id == user_id)
        .where(Task.batch_id == batch_id)
        .where(Task.status != 'completed')
    ).one()

    claim_limit_per_user = _get_claim_limit_per_user(batch)
    if claim_limit_per_user <= 0:
        return False, "批次领取限额无效"

    if occupied >= claim_limit_per_user:
        return False, "已达到领取限额"

    # 3. 锁定任务，检查可用性
    task = session.exec(
        select(Task)
        .where(Task.id == task_id)
        .where(Task.batch_id == batch_id)
        .where(Task.status == "pending")
        .with_for_update()
    ).first()

    if not task:
        return False, "任务不可用"

    # 4. 检查未被认领
    existing = session.exec(
        select(TaskAssignment)
        .where(TaskAssignment.task_id == task_id)
    ).first()

    if existing:
        return False, "任务已被认领"

    # 5. 创建分配记录
    assignment = TaskAssignment(
        task_id=task_id,
        user_id=user_id,
        assigned_by=user_id,
        assigned_at=datetime.utcnow()
    )
    session.add(assignment)
    session.commit()

    return True, "认领成功"


def get_batch_allocations(session: Session, batch_id: int) -> List[dict]:
    """获取批次的所有分配记录（管理员查看）"""
    batch = session.get(Batch, batch_id)
    batch_claim_limit_per_user = _get_claim_limit_per_user(batch) if batch else 0

    allocations = session.exec(
        select(BatchAllocation, User)
        .join(User, BatchAllocation.user_id == User.id)
        .where(BatchAllocation.batch_id == batch_id)
    ).all()

    results = []
    for allocation, user in allocations:
        # 计算当前占用数
        occupied = session.exec(
            select(func.count(TaskAssignment.id))
            .join(Task, TaskAssignment.task_id == Task.id)
            .where(TaskAssignment.user_id == user.id)
            .where(Task.batch_id == batch_id)
            .where(Task.status != 'completed')
        ).one()

        results.append({
            'user_id': user.id,
            'username': user.username,
            'occupied': occupied,
            'available': max(batch_claim_limit_per_user - occupied, 0),
            'allocated_at': allocation.allocated_at
        })

    return results


def get_claimable_tasks(
    session: Session,
    batch_id: int,
    skip: int = 0,
    limit: int = 50
) -> Tuple[List[Task], int]:
    """获取批次中可领取的任务（未被认领的pending任务）"""
    from sqlalchemy import exists

    # 未被认领 = 没有 TaskAssignment 记录
    base_query = (
        select(Task)
        .where(Task.batch_id == batch_id)
        .where(Task.status == "pending")
        .where(
            ~exists(
                select(TaskAssignment.id)
                .where(TaskAssignment.task_id == Task.id)
            )
        )
    )

    # 总数
    count_query = select(func.count()).select_from(base_query.subquery())
    total = session.exec(count_query).one()

    # 分页
    tasks = session.exec(
        base_query.order_by(Task.id).offset(skip).limit(limit)
    ).all()

    return list(tasks), total
