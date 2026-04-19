"""
Task model using SQLModel
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class Task(SQLModel, table=True):
    """任务表"""
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    description: str = Field(index=True)
    status: str = Field(default="pending")  # pending/in_progress/completed
    batch_id: Optional[int] = Field(default=None, foreign_key="batches.id", index=True)
    created_by: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
