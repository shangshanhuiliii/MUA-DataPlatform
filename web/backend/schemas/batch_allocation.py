"""
Schemas for batch allocation API
"""
from typing import List
from pydantic import BaseModel


class BatchAllocationRequest(BaseModel):
    """批次分配请求"""
    user_ids: List[int]


class BatchAllocationResponse(BaseModel):
    """批次分配响应"""
    batch_id: int
    allocations: List[dict]


class ClaimTaskRequest(BaseModel):
    """认领任务请求"""
    task_id: int


class AllocationStatsResponse(BaseModel):
    """领取限额统计响应"""
    claim_limit_per_user: int
    occupied: int
    available: int
