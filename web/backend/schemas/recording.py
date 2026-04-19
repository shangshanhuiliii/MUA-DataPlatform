"""
Recording management schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class RecordingCreate(BaseModel):
    """创建录制记录请求"""
    task_id: int
    directory_name: str = Field(..., min_length=1)


class RecordingUpdate(BaseModel):
    """更新录制记录请求"""
    directory_name: Optional[str] = Field(None, min_length=1)


class RecordingResponse(BaseModel):
    """录制记录响应"""
    id: int
    task_id: int
    task_description: str
    directory_name: str
    recorded_by: int
    recorded_by_username: str
    created_at: datetime
    updated_at: datetime


class RecordingListResponse(BaseModel):
    """录制记录列表响应"""
    recordings: List[RecordingResponse]
    total: int
    page: int
    page_size: int


class CurrentRecordingResponse(BaseModel):
    """当前录制响应"""
    current: Optional[str] = Field(None, description="当前选中的录制目录名称")
    recording: Optional[RecordingResponse] = Field(None, description="录制详情（如果存在于数据库）")


class RecordingExceptionItem(BaseModel):
    """录制异常项"""
    directory_name: str
    record_url: str
    exception_type: str = Field(pattern="^(missing_db_record|invalid_relationship)$")
    issues: List[str] = Field(default_factory=list)
    recording_id: Optional[int] = None
    task_id: Optional[int] = None
    task_description: Optional[str] = None
    recorded_by: Optional[int] = None
    recorded_by_username: Optional[str] = None
    inferred_task_id: Optional[int] = None
    inferred_task_description: Optional[str] = None
    task_info_exists: bool = False
    task_info_task_id: Optional[int] = None
    task_info_description: Optional[str] = None


class RecordingExceptionListResponse(BaseModel):
    """录制异常列表响应"""
    items: List[RecordingExceptionItem]
    total: int


class RepairRecordingExceptionRequest(BaseModel):
    """录制异常修复请求"""
    directory_name: str = Field(..., min_length=1)
    task_id: int
    recorded_by: int


class RepairRecordingExceptionResponse(BaseModel):
    """录制异常修复响应"""
    action: str = Field(pattern="^(created|updated)$")
    assignment_created: bool = False
    message: str
    recording: RecordingResponse
