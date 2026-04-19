from pydantic import BaseModel, Field
from typing import Optional

class Device(BaseModel):
    """设备模型"""
    serial: str = Field(..., description="设备序列号")
    model: Optional[str] = Field(None, description="设备型号")
    brand: Optional[str] = Field(None, description="设备品牌")
    version: Optional[str] = Field(None, description="Android版本")
    api_level: Optional[int] = Field(None, description="API级别")
    status: str = Field("unknown", description="设备状态")
