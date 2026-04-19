"""
Batch allocation API routes
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlmodel import Session

from backend.database import get_session
from backend.models.user import User
from backend.auth.dependencies import get_current_active_user, get_current_superuser
from backend.schemas.batch_allocation import (
    BatchAllocationRequest, BatchAllocationResponse,
    ClaimTaskRequest, AllocationStatsResponse
)
from backend.crud import batch_allocation as allocation_crud
from backend.crud import batch as batch_crud

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/batches", tags=["Batch Allocations"])


@router.post("/{batch_id}/allocations", response_model=dict)
async def allocate_batch_users(
    batch_id: int,
    request: BatchAllocationRequest,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """分配批次给用户 - 仅管理员"""
    batch = batch_crud.get_batch_by_id(session, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    success, failed, errors = allocation_crud.allocate_batch_to_users(
        session, batch_id, request.user_ids, current_user.id
    )
    return {"success": success, "failed": failed, "errors": errors}


@router.get("/{batch_id}/allocations", response_model=BatchAllocationResponse)
async def get_batch_allocations(
    batch_id: int,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """查看批次分配情况 - 仅管理员"""
    batch = batch_crud.get_batch_by_id(session, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    allocations = allocation_crud.get_batch_allocations(session, batch_id)
    return BatchAllocationResponse(batch_id=batch_id, allocations=allocations)


@router.get("/{batch_id}/my-allocation", response_model=AllocationStatsResponse)
async def get_my_allocation(
    batch_id: int,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """获取我在该批次的领取限额统计"""
    stats = allocation_crud.get_user_allocation_stats(session, batch_id, current_user.id)
    if not stats:
        raise HTTPException(status_code=404, detail="No allocation found")

    return AllocationStatsResponse(**stats)


@router.post("/{batch_id}/claim-task", response_model=dict)
async def claim_task(
    batch_id: int,
    request: ClaimTaskRequest,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """认领任务"""
    success, message = allocation_crud.claim_task(
        session, request.task_id, current_user.id, batch_id
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"success": True, "message": message}


@router.get("/{batch_id}/claimable-tasks")
async def get_claimable_tasks(
    batch_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=5000),
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """获取批次中可领取的任务（未被认领的pending任务）"""
    # 验证用户有该批次的分配记录
    stats = allocation_crud.get_user_allocation_stats(session, batch_id, current_user.id)
    if not stats and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="No allocation for this batch")

    skip = (page - 1) * page_size
    tasks, total = allocation_crud.get_claimable_tasks(session, batch_id, skip, page_size)

    task_list = []
    for task in tasks:
        task_list.append({
            "id": task.id,
            "description": task.description,
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None
        })

    return {"tasks": task_list, "total": total, "page": page, "page_size": page_size}
