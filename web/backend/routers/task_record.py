"""
TaskRecord 路由器 - 基于 Thread+Queue 架构
提供设备屏幕流和录制会话管理的 WebSocket API
使用 TaskRecordService 作为底层服务实现
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# 现在统一使用 TaskRecordService
from ..services.task_record_service import task_record_service as stream_service

router = APIRouter(prefix="/api", tags=["task-record"])
logger = logging.getLogger(__name__)

logger.info("Using TaskRecordService (Thread+Queue) for task recording and device streaming")


@router.websocket("/task-record/{device_serial}")
async def websocket_device_stream(websocket: WebSocket, device_serial: str):
    """
    设备屏幕流和录制管理 WebSocket 端点
    基于 TaskRecordService 的 Thread+Queue 架构
    """
    logger.info(f"WebSocket connection request for device: {device_serial}")

    try:
        # TaskRecordService 提供设备流连接管理
        await stream_service.connect_device_stream(device_serial, websocket)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for device: {device_serial}")
    except Exception as e:
        logger.error(f"WebSocket error for device {device_serial}: {e}")