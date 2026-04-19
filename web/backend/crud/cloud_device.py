"""
CRUD operations for CloudDevice model
"""
from typing import Optional, List, Tuple
from sqlmodel import Session, select, func
from datetime import datetime

from backend.models.cloud_device import CloudDevice


def create_cloud_device(
    session: Session,
    product_id: str,
    pod_id: str,
    created_by: int,
    alias: Optional[str] = None
) -> CloudDevice:
    """创建云设备"""
    device = CloudDevice(
        product_id=product_id,
        pod_id=pod_id,
        alias=alias,
        created_by=created_by,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def get_cloud_device_by_id(session: Session, device_id: int) -> Optional[CloudDevice]:
    """根据 ID 获取云设备"""
    return session.get(CloudDevice, device_id)


def get_cloud_device_by_product_pod(
    session: Session,
    product_id: str,
    pod_id: str
) -> Optional[CloudDevice]:
    """根据 product_id 和 pod_id 获取云设备"""
    statement = select(CloudDevice).where(
        CloudDevice.product_id == product_id,
        CloudDevice.pod_id == pod_id
    )
    return session.exec(statement).first()


def get_cloud_devices(
    session: Session,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
) -> Tuple[List[CloudDevice], int]:
    """获取云设备列表"""
    statement = select(CloudDevice)

    if is_active is not None:
        statement = statement.where(CloudDevice.is_active == is_active)

    if search:
        search_pattern = f"%{search}%"
        statement = statement.where(
            (CloudDevice.product_id.like(search_pattern)) |
            (CloudDevice.pod_id.like(search_pattern)) |
            (CloudDevice.alias.like(search_pattern))
        )

    # 获取总数
    count_stmt = select(func.count()).select_from(statement.subquery())
    total = session.exec(count_stmt).one()

    # 分页
    statement = statement.offset(skip).limit(limit).order_by(CloudDevice.created_at.desc())
    devices = list(session.exec(statement).all())

    return devices, total


def update_cloud_device(
    session: Session,
    device_id: int,
    alias: Optional[str] = None,
    is_active: Optional[bool] = None
) -> Optional[CloudDevice]:
    """更新云设备"""
    device = get_cloud_device_by_id(session, device_id)
    if not device:
        return None

    if alias is not None:
        device.alias = alias
    if is_active is not None:
        device.is_active = is_active
    device.updated_at = datetime.utcnow()

    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def delete_cloud_device(session: Session, device_id: int) -> bool:
    """删除云设备"""
    device = get_cloud_device_by_id(session, device_id)
    if not device:
        return False

    session.delete(device)
    session.commit()
    return True


def bulk_create_cloud_devices(
    session: Session,
    devices_data: List[dict],
    created_by: int
) -> Tuple[int, int, List[str]]:
    """批量创建云设备"""
    success = 0
    failed = 0
    errors = []

    for i, data in enumerate(devices_data):
        product_id = data.get('product_id', '').strip()
        pod_id = data.get('pod_id', '').strip()
        alias = data.get('alias')

        if not product_id or not pod_id:
            failed += 1
            errors.append(f"Device {i+1}: product_id and pod_id are required")
            continue

        # 检查是否已存在
        existing = get_cloud_device_by_product_pod(session, product_id, pod_id)
        if existing:
            failed += 1
            errors.append(f"Device {i+1}: ({product_id}, {pod_id}) already exists")
            continue

        try:
            device = CloudDevice(
                product_id=product_id,
                pod_id=pod_id,
                alias=alias.strip() if alias else None,
                created_by=created_by,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.add(device)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(f"Device {i+1}: {str(e)}")

    session.commit()
    return success, failed, errors


def batch_update_active_status(
    session: Session,
    device_ids: List[int],
    is_active: bool
) -> Tuple[int, int, List[str]]:
    """批量更新激活状态"""
    success = 0
    failed = 0
    errors = []

    for device_id in device_ids:
        device = get_cloud_device_by_id(session, device_id)
        if not device:
            failed += 1
            errors.append(f"Device {device_id}: Not found")
            continue

        device.is_active = is_active
        device.updated_at = datetime.utcnow()
        session.add(device)
        success += 1

    session.commit()
    return success, failed, errors


def batch_delete_cloud_devices(
    session: Session,
    device_ids: List[int]
) -> Tuple[int, int, List[str]]:
    """批量删除云设备"""
    success = 0
    failed = 0
    errors = []

    for device_id in device_ids:
        device = get_cloud_device_by_id(session, device_id)
        if not device:
            failed += 1
            errors.append(f"Device {device_id}: Not found")
            continue

        session.delete(device)
        success += 1

    session.commit()
    return success, failed, errors
