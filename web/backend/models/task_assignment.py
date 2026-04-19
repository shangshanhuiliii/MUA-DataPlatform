"""
TaskAssignment model using SQLModel
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint


class TaskAssignment(SQLModel, table=True):
    """任务分配表 - 实现任务与用户的多对多关系"""
    __tablename__ = "task_assignments"
    __table_args__ = (
        UniqueConstraint('task_id', 'user_id', name='unique_task_user'),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_by: int = Field(foreign_key="users.id")
