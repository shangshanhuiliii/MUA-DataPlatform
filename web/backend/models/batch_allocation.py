"""
BatchAllocation model using SQLModel
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint


class BatchAllocation(SQLModel, table=True):
    """批次分配表 - 批次级别的用户关联"""
    __tablename__ = "batch_allocations"
    __table_args__ = (
        UniqueConstraint('batch_id', 'user_id', name='unique_batch_user_allocation'),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batches.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    allocated_by: int = Field(foreign_key="users.id")
    allocated_at: datetime = Field(default_factory=datetime.utcnow)
