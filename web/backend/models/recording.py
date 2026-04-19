"""
Recording model using SQLModel
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class Recording(SQLModel, table=True):
    """录制数据表"""
    __tablename__ = "recordings"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", index=True)
    recorded_by: int = Field(foreign_key="users.id", index=True)
    directory_name: str = Field(unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
