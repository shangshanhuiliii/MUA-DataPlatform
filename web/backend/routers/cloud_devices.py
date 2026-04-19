"""
Cloud device management API routes
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlmodel import Session

from backend.database import get_session
from backend.models.user import User
from backend.auth.dependencies import get_current_superuser, get_current_active_user
from backend.schemas.cloud_device import (
    CloudDeviceCreate, CloudDeviceUpdate, CloudDeviceResponse,
    CloudDeviceListResponse, CloudDeviceBulkUpload,
    CloudDeviceBatchIds, CloudDeviceBatchStatusUpdate, CloudDeviceBatchResponse,
    CloudDeviceConnectRequest, CloudDeviceConnectResponse
)
from backend.crud import cloud_device as cloud_device_crud

router = APIRouter(prefix="/api/cloud-devices", tags=["Cloud Devices"])


@router.get("", response_model=CloudDeviceListResponse)
async def get_cloud_devices(
    is_active: bool = Query(None),
    locked: bool = Query(None, description="Filter by lock status"),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """获取云设备列表（普通用户只能获取激活的设备）"""
    from backend.services.cloud_device_service import cloud_device_service

    skip = (page - 1) * page_size

    # 普通用户只能查看激活的设备
    if not current_user.is_superuser:
        is_active = True

    devices, total = cloud_device_crud.get_cloud_devices(
        session,
        is_active=is_active,
        search=search,
        skip=skip,
        limit=page_size
    )

    # 检查每个设备的锁定状态
    locked_device_ids = []
    for device in devices:
        is_locked = await cloud_device_service.check_device_locked(
            device.product_id, device.pod_id
        )
        if is_locked:
            locked_device_ids.append(device.id)

    # 根据 locked 参数过滤
    if locked is not None:
        if locked:
            devices = [d for d in devices if d.id in locked_device_ids]
        else:
            devices = [d for d in devices if d.id not in locked_device_ids]
        total = len(devices)

    return CloudDeviceListResponse(
        items=[CloudDeviceResponse.model_validate(d, from_attributes=True) for d in devices],
        total=total,
        page=page,
        page_size=page_size,
        locked_device_ids=locked_device_ids
    )


@router.get("/{device_id}", response_model=CloudDeviceResponse)
async def get_cloud_device(
    device_id: int,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """获取云设备详情（仅管理员）"""
    device = cloud_device_crud.get_cloud_device_by_id(session, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Cloud device not found")
    return CloudDeviceResponse.model_validate(device, from_attributes=True)


@router.post("", response_model=CloudDeviceResponse, status_code=201)
async def create_cloud_device(
    request: CloudDeviceCreate,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """创建云设备（仅管理员）"""
    # 检查是否已存在
    existing = cloud_device_crud.get_cloud_device_by_product_pod(
        session, request.product_id, request.pod_id
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Device with product_id={request.product_id} and pod_id={request.pod_id} already exists"
        )

    device = cloud_device_crud.create_cloud_device(
        session,
        product_id=request.product_id,
        pod_id=request.pod_id,
        alias=request.alias,
        created_by=current_user.id
    )
    return CloudDeviceResponse.model_validate(device, from_attributes=True)


@router.put("/{device_id}", response_model=CloudDeviceResponse)
async def update_cloud_device(
    device_id: int,
    request: CloudDeviceUpdate,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """更新云设备（仅管理员）"""
    device = cloud_device_crud.update_cloud_device(
        session, device_id,
        alias=request.alias,
        is_active=request.is_active
    )
    if not device:
        raise HTTPException(status_code=404, detail="Cloud device not found")
    return CloudDeviceResponse.model_validate(device, from_attributes=True)


@router.delete("/{device_id}", status_code=204)
async def delete_cloud_device(
    device_id: int,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """删除云设备（仅管理员）"""
    if not cloud_device_crud.delete_cloud_device(session, device_id):
        raise HTTPException(status_code=404, detail="Cloud device not found")
    return None


@router.post("/batch", response_model=CloudDeviceBatchResponse, status_code=201)
async def batch_create_cloud_devices(
    request: CloudDeviceBulkUpload,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """批量创建云设备（仅管理员）"""
    devices_data = [d.model_dump() for d in request.devices]
    success, failed, errors = cloud_device_crud.bulk_create_cloud_devices(
        session, devices_data, current_user.id
    )
    return CloudDeviceBatchResponse(success=success, failed=failed, errors=errors)


@router.patch("/batch", response_model=CloudDeviceBatchResponse)
async def batch_update_cloud_devices(
    request: CloudDeviceBatchStatusUpdate,
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """批量更新云设备状态（仅管理员）"""
    success, failed, errors = cloud_device_crud.batch_update_active_status(
        session, request.device_ids, is_active=request.is_active
    )
    return CloudDeviceBatchResponse(success=success, failed=failed, errors=errors)


@router.delete("", response_model=CloudDeviceBatchResponse)
async def batch_delete_cloud_devices(
    ids: str = Query(..., description="逗号分隔的设备ID列表，如: 1,2,3"),
    current_user: User = Depends(get_current_superuser),
    session: Session = Depends(get_session)
):
    """批量删除云设备（仅管理员）"""
    # 解析 ID 列表
    try:
        device_ids = [int(id.strip()) for id in ids.split(",") if id.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device IDs format")

    if not device_ids:
        raise HTTPException(status_code=400, detail="No device IDs provided")

    success, failed, errors = cloud_device_crud.batch_delete_cloud_devices(
        session, device_ids
    )
    return CloudDeviceBatchResponse(success=success, failed=failed, errors=errors)


@router.post("/{device_id}/connections", response_model=CloudDeviceConnectResponse)
async def connect_cloud_device(
    device_id: int,
    request: CloudDeviceConnectRequest = CloudDeviceConnectRequest(),
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session)
):
    """
    连接云手机设备（所有登录用户可用）
    1. 根据 device_id 获取 product_id 和 pod_id
    2. 确保 ADB 可用（检查状态、过期时间，必要时重新开启）
    3. 执行 adb connect
    4. 返回连接结果和设备 serial
    """
    from backend.services.cloud_device_service import cloud_device_service

    # 获取云设备信息
    device = cloud_device_crud.get_cloud_device_by_id(session, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Cloud device not found")

    if not device.is_active:
        raise HTTPException(status_code=400, detail="Cloud device is not active")

    try:
        # 确保 ADB 连接可用
        adb_address, adb_expire_time = await cloud_device_service.ensure_adb_connection(
            device.product_id,
            device.pod_id,
            force_reconnect=request.force_reconnect
        )

        # 执行 adb connect
        await cloud_device_service.adb_connect(adb_address)

        return CloudDeviceConnectResponse(
            success=True,
            device_serial=adb_address,
            message="Connected successfully",
            adb_expire_time=adb_expire_time
        )

    except Exception as e:
        return CloudDeviceConnectResponse(
            success=False,
            device_serial="",
            message=str(e),
            adb_expire_time=None
        )
