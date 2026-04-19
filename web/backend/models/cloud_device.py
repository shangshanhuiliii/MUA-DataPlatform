"""
CloudDevice model for managing cloud phone devices (Volcengine ACEP)
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, UniqueConstraint


class CloudDevice(SQLModel, table=True):
    """云手机设备表"""
    __tablename__ = "cloud_devices"
    __table_args__ = (
        UniqueConstraint('product_id', 'pod_id', name='unique_product_pod'),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: str = Field(max_length=100, index=True)
    pod_id: str = Field(max_length=100, index=True)
    alias: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = Field(default=True, index=True)
    created_by: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
