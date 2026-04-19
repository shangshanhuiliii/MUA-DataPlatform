"""
Batch model using SQLModel
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


DEFAULT_CLAIM_LIMIT_PER_USER = 10


class Batch(SQLModel, table=True):
    """批次表"""
    __tablename__ = "batches"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = Field(default=None)
    claim_limit_per_user: int = Field(default=DEFAULT_CLAIM_LIMIT_PER_USER, nullable=False)
    created_by: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
