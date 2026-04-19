"""
Batch management API routes
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlmodel import Session

from backend.database import get_session
from backend.models.batch import DEFAULT_CLAIM_LIMIT_PER_USER
from backend.models.user import User
from backend.auth.dependencies import get_current_active_user, get_current_superuser
from backend.schemas.batch import (
    BatchCreate, BatchUpdate, BatchResponse, BatchListResponse,
    BatchAssignRequest, BatchStatistics
)
from backend.crud import batch as batch_crud

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/batches", tags=["Batches"])


@router.post("", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def create_batch(
    request: BatchCreate,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """创建批次（仅管理员）"""
    batch = batch_crud.create_batch(session, request.name, request.description, current_user.id)
    stats = batch_crud.get_batch_statistics(session, batch.id)
    return BatchResponse(
        id=batch.id,
        name=batch.name,
        description=batch.description,
        claim_limit_per_user=(
            batch.claim_limit_per_user
            if batch.claim_limit_per_user is not None
            else DEFAULT_CLAIM_LIMIT_PER_USER
        ),
        created_by=batch.created_by,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        statistics=BatchStatistics(**stats)
    )


@router.get("", response_model=BatchListResponse)
async def get_batches(
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """获取批次列表"""
    skip = (page - 1) * page_size
    batches, total = batch_crud.get_batches(session, skip, page_size, sort_by, sort_order)

    batch_responses = []
    for batch in batches:
        stats = batch_crud.get_batch_statistics(session, batch.id)
        batch_responses.append(BatchResponse(
            id=batch.id,
            name=batch.name,
            description=batch.description,
            claim_limit_per_user=(
                batch.claim_limit_per_user
                if batch.claim_limit_per_user is not None
                else DEFAULT_CLAIM_LIMIT_PER_USER
            ),
            created_by=batch.created_by,
            created_at=batch.created_at,
            updated_at=batch.updated_at,
            statistics=BatchStatistics(**stats)
        ))

    return BatchListResponse(batches=batch_responses, total=total, page=page, page_size=page_size)


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: int,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """获取批次详情"""
    batch = batch_crud.get_batch_by_id(session, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    stats = batch_crud.get_batch_statistics(session, batch.id)
    return BatchResponse(
        id=batch.id,
        name=batch.name,
        description=batch.description,
        claim_limit_per_user=(
            batch.claim_limit_per_user
            if batch.claim_limit_per_user is not None
            else DEFAULT_CLAIM_LIMIT_PER_USER
        ),
        created_by=batch.created_by,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        statistics=BatchStatistics(**stats)
    )


@router.put("/{batch_id}", response_model=BatchResponse)
async def update_batch(
    batch_id: int,
    request: BatchUpdate,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """更新批次（仅管理员）"""
    batch = batch_crud.update_batch(session, batch_id, request)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    stats = batch_crud.get_batch_statistics(session, batch.id)
    return BatchResponse(
        id=batch.id,
        name=batch.name,
        description=batch.description,
        claim_limit_per_user=(
            batch.claim_limit_per_user
            if batch.claim_limit_per_user is not None
            else DEFAULT_CLAIM_LIMIT_PER_USER
        ),
        created_by=batch.created_by,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        statistics=BatchStatistics(**stats)
    )


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_batch(
    batch_id: int,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """删除批次（仅管理员）"""
    if not batch_crud.delete_batch(session, batch_id):
        raise HTTPException(status_code=404, detail="Batch not found")
    return None


@router.post("/{batch_id}/assignments")
async def assign_batch(
    batch_id: int,
    request: BatchAssignRequest,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """批次级别分配用户（仅管理员）"""
    batch = batch_crud.get_batch_by_id(session, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    success, failed, errors = batch_crud.assign_batch_to_users(session, batch_id, request.user_ids, current_user.id)
    return {"success": success, "failed": failed, "errors": errors}
