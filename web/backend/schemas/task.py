"""
Task management schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ============================================================================
# Task Info API (existing)
# ============================================================================

class TaskInfoResponse(BaseModel):
    """Task Info API 响应模型"""
    recording: str = Field(..., description="录制目录名称")
    task_info: str = Field(..., description="任务信息 YAML 内容")


class UpdateTaskInfoRequest(BaseModel):
    """更新 Task Info 请求模型"""
    task_info_yaml: str = Field(..., description="任务信息 YAML 内容")


# ============================================================================
# Task Management API (new)
# ============================================================================

class TaskCreate(BaseModel):
    """创建任务请求"""
    description: str = Field(..., min_length=1, max_length=1000)
    batch_id: Optional[int] = None


class TaskUpdate(BaseModel):
    """更新任务请求"""
    description: Optional[str] = Field(None, min_length=1, max_length=1000)
    status: Optional[str] = Field(None, pattern="^(pending|in_progress|completed)$")
    batch_id: Optional[int] = None


class UserBrief(BaseModel):
    """用户简要信息"""
    id: int
    username: str


class TaskResponse(BaseModel):
    """任务响应"""
    id: int
    description: str
    status: str
    batch_id: Optional[int] = None
    created_by: int
    created_at: datetime
    updated_at: datetime
    assigned_users: List[UserBrief] = []
    recording_count: int = 0


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int


class TaskAssignRequest(BaseModel):
    """任务分配请求"""
    user_ids: List[int] = Field(..., min_length=1)


class TaskAssignResponse(BaseModel):
    """任务分配响应"""
    task_id: int
    assigned_users: List[int]
    message: str


class BulkUploadRequest(BaseModel):
    """批量上传任务请求"""
    tasks: List[str] = Field(..., min_length=1)
    batch_id: Optional[int] = None


class BulkUploadResponse(BaseModel):
    """批量上传任务响应"""
    success: int
    failed: int
    errors: List[str] = []


class BatchDeleteRequest(BaseModel):
    """批量删除任务请求"""
    task_ids: List[int] = Field(..., min_length=1)


class BatchDeleteResponse(BaseModel):
    """批量删除任务响应"""
    success: int
    failed: int
    errors: List[str] = []


class BatchAssignRequest(BaseModel):
    """批量分配任务请求"""
    task_ids: List[int] = Field(..., min_length=1)
    user_ids: List[int] = Field(default=[])  # 空列表表示取消所有分配


class BatchAssignResponse(BaseModel):
    """批量分配任务响应"""
    success: int
    failed: int
    errors: List[str] = []


class BatchMoveRequest(BaseModel):
    """批量移动任务请求"""
    task_ids: List[int] = Field(..., min_length=1)
    target_batch_id: Optional[int] = None  # None 表示移动到独立任务

