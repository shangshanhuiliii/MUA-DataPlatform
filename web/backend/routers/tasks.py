"""
Task management API routes
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Response, Query, status
from sqlmodel import Session
from typing import Optional, List
from datetime import datetime
from backend.database import get_session
from backend.models.user import User
from backend.auth.dependencies import get_current_active_user, get_current_superuser
from backend.schemas.task import (
    TaskInfoResponse, UpdateTaskInfoRequest,
    TaskCreate, TaskUpdate, TaskResponse, TaskListResponse,
    TaskAssignRequest, TaskAssignResponse,
    BulkUploadRequest, BulkUploadResponse, UserBrief,
    BatchDeleteRequest, BatchDeleteResponse,
    BatchAssignRequest, BatchAssignResponse, BatchMoveRequest
)
from backend.crud import task as task_crud
from backend.services.task_service import TaskService
from backend.session_config import current_recording_from_header, current_recording_from_header_for_write

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Tasks"])


# ============================================================================
# Task Management API (New)
# ============================================================================

@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: TaskCreate,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """创建任务（仅管理员）"""
    task = task_crud.create_task(session, request.description, current_user.id, request.batch_id)
    return TaskResponse(
        id=task.id,
        description=task.description,
        status=task.status,
        batch_id=task.batch_id,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
        assigned_users=[],
        recording_count=0
    )


@router.get("/tasks", response_model=TaskListResponse)
async def get_tasks(
    status: Optional[str] = Query(None),
    batch_id: int = Query(None),
    keyword: Optional[str] = Query(None),
    assigned_user: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """获取任务列表

    - 管理员：返回所有任务
    - 普通用户：返回分配给自己的任务
    """
    # 处理空字符串，转换为 None
    if status == "":
        status = None
    # 验证非空值
    elif status and status not in ["pending", "in_progress", "completed"]:
        raise HTTPException(status_code=400, detail="Invalid status value")

    if sort_by not in task_crud.ALLOWED_TASK_SORT_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid sort field")

    skip = (page - 1) * page_size
    tasks, total = task_crud.get_tasks(
        session,
        user_id=current_user.id,
        is_admin=current_user.is_superuser,
        status=status,
        batch_id=batch_id,
        keyword=keyword,
        assigned_user_id=assigned_user,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order
    )

    task_ids = [task.id for task in tasks]
    assigned_users_map = task_crud.get_tasks_assigned_users_map(session, task_ids)
    recording_counts_map = task_crud.get_tasks_recording_counts(session, task_ids)

    task_responses = []
    for task in tasks:
        assigned_users = assigned_users_map.get(task.id, [])
        recording_count = recording_counts_map.get(task.id, 0)
        task_responses.append(TaskResponse(
            id=task.id,
            description=task.description,
            status=task.status,
            batch_id=task.batch_id,
            created_by=task.created_by,
            created_at=task.created_at,
            updated_at=task.updated_at,
            assigned_users=[UserBrief(id=u.id, username=u.username) for u in assigned_users],
            recording_count=recording_count
        ))

    return TaskListResponse(
        tasks=task_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """获取任务详情"""
    task = task_crud.get_task_by_id(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 权限检查：非管理员只能查看分配给自己的任务
    if not current_user.is_superuser:
        if not task_crud.is_task_assigned_to_user(session, task_id, current_user.id):
            raise HTTPException(status_code=403, detail="You don't have access to this task")

    assigned_users = task_crud.get_task_assigned_users(session, task.id)
    recording_count = task_crud.get_task_recording_count(session, task.id)

    return TaskResponse(
        id=task.id,
        description=task.description,
        status=task.status,
        batch_id=task.batch_id,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
        assigned_users=[UserBrief(id=u.id, username=u.username) for u in assigned_users],
        recording_count=recording_count
    )


@router.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    request: TaskUpdate,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """更新任务（仅管理员）"""
    task = task_crud.update_task(
        session, task_id,
        description=request.description,
        status=request.status,
        batch_id=request.batch_id
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    assigned_users = task_crud.get_task_assigned_users(session, task.id)
    recording_count = task_crud.get_task_recording_count(session, task.id)

    return TaskResponse(
        id=task.id,
        description=task.description,
        status=task.status,
        batch_id=task.batch_id,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
        assigned_users=[UserBrief(id=u.id, username=u.username) for u in assigned_users],
        recording_count=recording_count
    )


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """删除任务（仅管理员）"""
    # 检查是否有关联的录制数据
    recording_count = task_crud.get_task_recording_count(session, task_id)
    if recording_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete task with {recording_count} recordings. Delete recordings first."
        )

    if not task_crud.delete_task(session, task_id):
        raise HTTPException(status_code=404, detail="Task not found")

    return None


@router.post("/tasks/{task_id}/assignments", response_model=TaskAssignResponse)
async def assign_task(
    task_id: int,
    request: TaskAssignRequest,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """分配任务给用户（仅管理员）"""
    task = task_crud.get_task_by_id(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    assigned_users = task_crud.assign_task(
        session, task_id, request.user_ids, current_user.id
    )

    return TaskAssignResponse(
        task_id=task_id,
        assigned_users=assigned_users,
        message="Task assigned successfully"
    )


@router.delete("/tasks/{task_id}/assignments/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_task(
    task_id: int,
    user_id: int,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """取消任务分配（仅管理员）"""
    if not task_crud.unassign_task(session, task_id, user_id):
        raise HTTPException(status_code=404, detail="Assignment not found")

    return None


@router.post("/tasks/batch", response_model=BulkUploadResponse, status_code=status.HTTP_201_CREATED)
async def bulk_upload_tasks(
    request: BulkUploadRequest,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """批量上传任务（仅管理员）"""
    success, failed, errors = task_crud.bulk_create_tasks(
        session, request.tasks, current_user.id, request.batch_id
    )

    return BulkUploadResponse(
        success=success,
        failed=failed,
        errors=errors
    )


@router.delete("/tasks", response_model=BatchDeleteResponse)
async def batch_delete_tasks(
    ids: str = Query(..., description="逗号分隔的任务ID列表，如: 1,2,3"),
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """批量删除任务（仅管理员）"""
    # 解析 ID 列表
    try:
        task_ids = [int(id.strip()) for id in ids.split(",") if id.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task IDs format")

    if not task_ids:
        raise HTTPException(status_code=400, detail="No task IDs provided")

    success, failed, errors = task_crud.batch_delete_tasks(
        session, task_ids
    )

    return BatchDeleteResponse(
        success=success,
        failed=failed,
        errors=errors
    )


@router.patch("/tasks/assignments", response_model=BatchAssignResponse)
async def batch_assign_tasks(
    request: BatchAssignRequest,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """批量分配任务给用户（仅管理员）"""
    try:
        success, failed, errors = task_crud.batch_assign_tasks(
            session, request.task_ids, request.user_ids, current_user.id
        )

        return BatchAssignResponse(
            success=success,
            failed=failed,
            errors=errors
        )
    except Exception as e:
        logger.error(f"Batch assign tasks failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tasks/batch-move")
async def batch_move_tasks(
    request: BatchMoveRequest,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """批量移动任务到其他批次（仅管理员）"""
    success, failed, errors = task_crud.batch_move_tasks(
        session, request.task_ids, request.target_batch_id
    )
    return {"success": success, "failed": failed, "errors": errors}


# ============================================================================
# Task Info API (Session-based, existing)
# ============================================================================

@router.get("/task-info")
async def get_task_info(
    recording_name: str = Depends(current_recording_from_header)
) -> TaskInfoResponse:
    """获取当前 recording 的 task-info.yaml 内容
    """
    try:
        task_info = TaskService.get_task_info(recording_name)

        if task_info is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task info not found for recording '{recording_name}'"
            )

        return TaskInfoResponse(
            recording=recording_name,
            task_info=task_info
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Dataset validation error: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get task info: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get task info: {str(e)}"
        )


@router.put("/task-info")
async def update_task_info(
    request: UpdateTaskInfoRequest,
    recording_name: str = Depends(current_recording_from_header_for_write)
) -> TaskInfoResponse:
    """更新当前 recording 的 task-info.yaml 内容
    """
    try:
        updated_content = TaskService.update_task_info(
            recording_name,
            request.task_info_yaml
        )

        return TaskInfoResponse(
            recording=recording_name,
            task_info=updated_content
        )

    except HTTPException:
        raise
    except FileNotFoundError as e:
        logger.error(f"Task info not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        logger.error(f"Invalid task info format: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update task info: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update task info: {str(e)}"
        )
