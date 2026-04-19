"""
Batch schemas for API requests and responses
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from backend.models.batch import DEFAULT_CLAIM_LIMIT_PER_USER


class BatchCreate(BaseModel):
    """创建批次请求"""
    name: str
    description: Optional[str] = None


class BatchUpdate(BaseModel):
    """更新批次请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    claim_limit_per_user: Optional[int] = Field(default=None, ge=1)


class BatchStatistics(BaseModel):
    """批次统计信息"""
    total: int
    pending: int
    in_progress: int
    completed: int
    assigned_user_count: int
    assigned_usernames: List[str] = []
    allocated_usernames: List[str] = []


class BatchResponse(BaseModel):
    """批次响应"""
    id: int
    name: str
    description: Optional[str]
    claim_limit_per_user: int = Field(default=DEFAULT_CLAIM_LIMIT_PER_USER, ge=1)
    created_by: int
    created_at: datetime
    updated_at: datetime
    statistics: Optional[BatchStatistics] = None


class BatchListResponse(BaseModel):
    """批次列表响应"""
    batches: List[BatchResponse]
    total: int
    page: int
    page_size: int


class BatchAssignRequest(BaseModel):
    """批次分配请求"""
    user_ids: List[int]
