"""
Recording management API routes
"""
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, Response, status
from sqlmodel import Session

from backend.database import get_session
from backend.errors import AppError
from backend.models.user import User
from backend.auth.dependencies import get_current_active_user, get_current_superuser
from backend.schemas.recording import (
    RecordingCreate, RecordingUpdate, RecordingResponse, RecordingListResponse,
    CurrentRecordingResponse, RecordingExceptionListResponse,
    RepairRecordingExceptionRequest, RepairRecordingExceptionResponse
)
from backend.crud import recording as recording_crud
from backend.crud import task as task_crud
from backend.services import recording_exception_service
from backend.session_config import (
    get_workspace_data,
    get_workspace_data_for_write,
    workspace_state_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recordings", tags=["Recordings"])


def _assert_existing_recording_access(recording, current_user: User):
    """对已存在 recording 按其真实归属做权限校验。"""
    if current_user.is_superuser:
        return

    if recording.recorded_by != current_user.id:
        raise HTTPException(status_code=403, detail="You don't have access to this recording")


def _filter_recording_lock_conflict_for_user(error: AppError, current_user: User) -> AppError:
    if error.code != "RECORDING_LOCK_CONFLICT":
        return error

    extra = dict(error.extra)
    holder_ip_full = extra.get("holder_ip_full")
    if holder_ip_full and not current_user.is_superuser:
        extra.pop("holder_ip_full", None)
        extra["holder_ip_reason"] = "ip_hidden_by_policy"
        if extra.get("diagnostic_reason_summary") is None:
            extra["diagnostic_reason_summary"] = "role_limited_visibility"
        if extra.get("lock_diagnostic_message") is None and extra.get("lock_diagnostic_level") == "normal":
            extra["lock_diagnostic_message"] = "锁存在，但部分占用者信息因权限限制不可见。"

    if not current_user.is_superuser:
        extra.pop("holder_user_agent", None)

    error.extra = extra
    return error


@router.post("", response_model=RecordingResponse, status_code=status.HTTP_201_CREATED)
async def create_recording(
    request: RecordingCreate,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """创建录制记录"""
    existing = recording_crud.get_recording_by_directory(session, request.directory_name)

    if existing is not None:
        recording = existing
        created = False
    else:
        task = task_crud.get_task_by_id(session, request.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if not current_user.is_superuser:
            if not task_crud.is_task_assigned_to_user(session, request.task_id, current_user.id):
                raise HTTPException(status_code=403, detail="You don't have access to this task")

        recording, created = recording_crud.ensure_recording(
            session,
            task_id=request.task_id,
            directory_name=request.directory_name,
            recorded_by=current_user.id
        )

    if not created:
        _assert_existing_recording_access(recording, current_user)
        response.status_code = status.HTTP_200_OK

    task_description = recording_crud.get_task_description(session, recording.task_id)
    recorded_by_username = recording_crud.get_username(session, recording.recorded_by)

    return RecordingResponse(
        id=recording.id,
        task_id=recording.task_id,
        task_description=task_description,
        directory_name=recording.directory_name,
        recorded_by=recording.recorded_by,
        recorded_by_username=recorded_by_username,
        created_at=recording.created_at,
        updated_at=recording.updated_at
    )


@router.get("", response_model=RecordingListResponse)
async def get_recordings(
    task_id: int = Query(None),
    keyword: Optional[str] = Query(None),
    batch_id: Optional[int] = Query(None),
    recorded_by: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """获取录制记录列表

    - 管理员：返回所有录制
    - 普通用户：返回自己的录制
    """
    if sort_by not in recording_crud.ALLOWED_RECORDING_SORT_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid sort field")

    skip = (page - 1) * page_size
    recordings, total = recording_crud.get_recordings(
        session,
        user_id=current_user.id,
        is_admin=current_user.is_superuser,
        task_id=task_id,
        keyword=keyword,
        batch_id=batch_id,
        recorded_by_filter=recorded_by,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order
    )

    recording_responses = []
    for rec in recordings:
        task_desc = recording_crud.get_task_description(session, rec.task_id)
        username = recording_crud.get_username(session, rec.recorded_by)
        recording_responses.append(RecordingResponse(
            id=rec.id,
            task_id=rec.task_id,
            task_description=task_desc,
            directory_name=rec.directory_name,
            recorded_by=rec.recorded_by,
            recorded_by_username=username,
            created_at=rec.created_at,
            updated_at=rec.updated_at
        ))

    return RecordingListResponse(
        recordings=recording_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/exceptions", response_model=RecordingExceptionListResponse)
async def get_recording_exceptions(
    keyword: Optional[str] = Query(None),
    exception_type: Optional[str] = Query(None, pattern="^(missing_db_record|invalid_relationship)$"),
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """获取录制异常列表（仅管理员）"""
    _ = current_user
    items = recording_exception_service.list_recording_exceptions(
        session,
        keyword=keyword,
        exception_type=exception_type
    )
    return RecordingExceptionListResponse(items=items, total=len(items))


@router.post("/exceptions/repair", response_model=RepairRecordingExceptionResponse)
async def repair_recording_exception(
    request: RepairRecordingExceptionRequest,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """修复录制异常（仅管理员）"""
    try:
        result = recording_exception_service.repair_recording_exception(
            session,
            directory_name=request.directory_name,
            task_id=request.task_id,
            recorded_by=request.recorded_by,
            repaired_by=current_user.id
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail.endswith("not found") else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc

    recording = result["recording"]
    task_description = recording_crud.get_task_description(session, recording.task_id)
    recorded_by_username = recording_crud.get_username(session, recording.recorded_by)

    return RepairRecordingExceptionResponse(
        action=result["action"],
        assignment_created=result["assignment_created"],
        message="Recording exception repaired successfully",
        recording=RecordingResponse(
            id=recording.id,
            task_id=recording.task_id,
            task_description=task_description,
            directory_name=recording.directory_name,
            recorded_by=recording.recorded_by,
            recorded_by_username=recorded_by_username,
            created_at=recording.created_at,
            updated_at=recording.updated_at
        )
    )


# ============================================================================
# Current Recording 管理（带互斥锁）
# 注意：这些路由必须在 /{recording_id} 之前定义，否则 /current 会被匹配为 recording_id
# ============================================================================

@router.get("/current", response_model=CurrentRecordingResponse)
async def get_current_recording(
    workspace = Depends(get_workspace_data),
    db_session: Session = Depends(get_session)
):
    """获取当前选中的录制"""
    current = workspace.current_recording
    if not current:
        return CurrentRecordingResponse(current=None, recording=None)

    # 尝试从数据库获取录制详情
    recording = recording_crud.get_recording_by_directory(db_session, current)
    if recording:
        task_desc = recording_crud.get_task_description(db_session, recording.task_id)
        username = recording_crud.get_username(db_session, recording.recorded_by)
        return CurrentRecordingResponse(
            current=current,
            recording=RecordingResponse(
                id=recording.id,
                task_id=recording.task_id,
                task_description=task_desc,
                directory_name=recording.directory_name,
                recorded_by=recording.recorded_by,
                recorded_by_username=username,
                created_at=recording.created_at,
                updated_at=recording.updated_at
            )
        )

    return CurrentRecordingResponse(current=current, recording=None)


@router.post("/current/{directory_name:path}")
async def set_current_recording(
    directory_name: str,
    current_user: User = Depends(get_current_active_user),
    workspace = Depends(get_workspace_data_for_write),
    db_session: Session = Depends(get_session)
):
    """设置当前活动录制（带互斥锁）"""
    # 验证目录是否存在
    from backend.config import Config
    recording_path = Config.DATA_DIR / directory_name
    if not recording_path.exists():
        raise HTTPException(status_code=404, detail=f"Recording directory '{directory_name}' not found")

    try:
        workspace = await workspace_state_manager.set_current_recording(workspace.workspace_id, directory_name)
    except AppError as error:
        raise _filter_recording_lock_conflict_for_user(error, current_user) from error

    # 获取录制详情（如果存在于数据库）
    recording = recording_crud.get_recording_by_directory(db_session, directory_name)
    recording_response = None
    if recording:
        task_desc = recording_crud.get_task_description(db_session, recording.task_id)
        username = recording_crud.get_username(db_session, recording.recorded_by)
        recording_response = RecordingResponse(
            id=recording.id,
            task_id=recording.task_id,
            task_description=task_desc,
            directory_name=recording.directory_name,
            recorded_by=recording.recorded_by,
            recorded_by_username=username,
            created_at=recording.created_at,
            updated_at=recording.updated_at
        )

    return {
        "message": "Recording switched successfully",
        "current": directory_name,
        "workspace_id": workspace.workspace_id,
        "recording": recording_response
    }


@router.delete("/current")
async def release_current_recording_endpoint(
    workspace = Depends(get_workspace_data_for_write)
):
    """释放当前录制"""
    await workspace_state_manager.release_current_recording(workspace.workspace_id)
    return {"message": "Current recording released", "workspace_id": workspace.workspace_id}


# ============================================================================
# Recording CRUD（按 ID）
# ============================================================================

@router.get("/{recording_id}", response_model=RecordingResponse)
async def get_recording(
    recording_id: int,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """获取录制记录详情"""
    details = recording_crud.get_recording_with_details(session, recording_id)
    if not details:
        raise HTTPException(status_code=404, detail="Recording not found")

    recording = details["recording"]

    # 权限检查：非管理员只能查看自己的录制
    if not current_user.is_superuser and recording.recorded_by != current_user.id:
        raise HTTPException(status_code=403, detail="You don't have access to this recording")

    return RecordingResponse(
        id=recording.id,
        task_id=recording.task_id,
        task_description=details["task_description"],
        directory_name=recording.directory_name,
        recorded_by=recording.recorded_by,
        recorded_by_username=details["recorded_by_username"],
        created_at=recording.created_at,
        updated_at=recording.updated_at
    )


@router.put("/{recording_id}", response_model=RecordingResponse)
async def update_recording(
    recording_id: int,
    request: RecordingUpdate,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """更新录制记录"""
    recording = recording_crud.get_recording_by_id(session, recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    # 权限检查：只有录制者本人或管理员可以更新
    if not current_user.is_superuser and recording.recorded_by != current_user.id:
        raise HTTPException(status_code=403, detail="You don't have permission to modify this recording")

    updated = recording_crud.update_recording(
        session, recording_id,
        directory_name=request.directory_name
    )

    task_desc = recording_crud.get_task_description(session, updated.task_id)
    username = recording_crud.get_username(session, updated.recorded_by)

    return RecordingResponse(
        id=updated.id,
        task_id=updated.task_id,
        task_description=task_desc,
        directory_name=updated.directory_name,
        recorded_by=updated.recorded_by,
        recorded_by_username=username,
        created_at=updated.created_at,
        updated_at=updated.updated_at
    )


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recording(
    recording_id: int,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """删除录制记录"""
    recording = recording_crud.get_recording_by_id(session, recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    # 权限检查：只有录制者本人或管理员可以删除
    if not current_user.is_superuser and recording.recorded_by != current_user.id:
        raise HTTPException(status_code=403, detail="You don't have permission to delete this recording")

    recording_crud.delete_recording(session, recording_id)
    return None
