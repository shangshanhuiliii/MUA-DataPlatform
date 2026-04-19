"""
Cloud device management schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class CloudDeviceCreate(BaseModel):
    """创建云设备请求"""
    product_id: str = Field(..., min_length=1, max_length=100)
    pod_id: str = Field(..., min_length=1, max_length=100)
    alias: Optional[str] = Field(None, max_length=100)


class CloudDeviceUpdate(BaseModel):
    """更新云设备请求"""
    alias: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class CloudDeviceResponse(BaseModel):
    """云设备响应"""
    id: int
    product_id: str
    pod_id: str
    alias: Optional[str]
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime


class CloudDeviceListResponse(BaseModel):
    """云设备列表响应"""
    items: List[CloudDeviceResponse]
    total: int
    page: int
    page_size: int
    locked_device_ids: List[int] = []


class CloudDeviceBulkUpload(BaseModel):
    """批量上传云设备请求"""
    devices: List[CloudDeviceCreate] = Field(..., min_length=1)


class CloudDeviceBatchIds(BaseModel):
    """批量操作请求"""
    device_ids: List[int] = Field(..., min_length=1)


class CloudDeviceBatchStatusUpdate(BaseModel):
    """批量更新状态请求"""
    device_ids: List[int] = Field(..., min_length=1)
    is_active: bool


class CloudDeviceBatchResponse(BaseModel):
    """批量操作响应"""
    success: int
    failed: int
    errors: List[str] = []


class CloudDeviceConnectRequest(BaseModel):
    """连接云设备请求"""
    force_reconnect: bool = False


class CloudDeviceConnectResponse(BaseModel):
    """连接云设备响应"""
    success: bool
    device_serial: str = ""
    message: str
    adb_expire_time: Optional[datetime] = None
