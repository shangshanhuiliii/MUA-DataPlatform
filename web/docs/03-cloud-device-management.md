# 云手机设备管理

云手机设备管理功能用于管理火山引擎云手机（ACEP）设备。系统通过 `ProductId` 和 `PodId` 唯一标识云手机实例，支持设备的增删改查、批量导入、激活/停用等操作，并集成了 ADB 连接管理以支持任务录制。

## 数据库设计

### SQLModel 模型

```python
# backend/models/cloud_device.py
class CloudDevice(SQLModel, table=True):
    __tablename__ = "cloud_devices"

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: str = Field(max_length=100, index=True)
    pod_id: str = Field(max_length=100, index=True)
    alias: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = Field(default=True, index=True)
    created_by: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### Schema 定义

```python
# 创建云设备请求
class CloudDeviceCreate(BaseModel):
    product_id: str   # 1-100 字符
    pod_id: str       # 1-100 字符
    alias: Optional[str] = None  # 最大 100 字符

# 更新云设备请求
class CloudDeviceUpdate(BaseModel):
    alias: Optional[str] = None
    is_active: Optional[bool] = None

# 云设备响应
class CloudDeviceResponse(BaseModel):
    id: int
    product_id: str
    pod_id: str
    alias: Optional[str]
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime

# 云设备列表响应
class CloudDeviceListResponse(BaseModel):
    items: List[CloudDeviceResponse]
    total: int
    page: int
    page_size: int
    locked_device_ids: List[int]  # 被锁定的设备 ID 列表
```

## 相关文件

```
backend/
├── models/cloud_device.py              # CloudDevice SQLModel 模型
├── schemas/cloud_device.py             # 请求/响应 Pydantic 模型
├── crud/cloud_device.py                # CRUD 操作
├── services/cloud_device_service.py    # 火山引擎 ADB 管理服务
└── routers/cloud_devices.py            # API 路由

static/js/
├── api/client.js                       # 云设备相关 API 方法
└── components/
    ├── cloud-device-manager.js         # 云设备管理前端组件
    └── task-recorder.js                # 任务录制组件（集成云设备）
```

## API 端点

### 设备管理 API（/api/cloud-devices）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | /api/cloud-devices | 已认证 | 获取云设备列表 |
| GET | /api/cloud-devices/{id} | 管理员 | 获取单个设备详情 |
| POST | /api/cloud-devices | 管理员 | 创建单个云设备 |
| PUT | /api/cloud-devices/{id} | 管理员 | 更新设备 |
| DELETE | /api/cloud-devices/{id} | 管理员 | 删除单个设备 |
| POST | /api/cloud-devices/batch | 管理员 | 批量创建设备 |
| PATCH | /api/cloud-devices/batch | 管理员 | 批量更新设备状态 |
| DELETE | /api/cloud-devices?ids=1,2,3 | 管理员 | 批量删除设备 |
| POST | /api/cloud-devices/{id}/connections | 已认证 | 连接云手机 |

### GET /api/cloud-devices 查询参数

| 参数 | 类型 | 说明 |
|------|------|------|
| is_active | bool | 筛选激活状态（普通用户强制为 true） |
| locked | bool | 筛选锁定状态 |
| search | string | 搜索（product_id/pod_id/alias） |
| page | int | 页码（默认 1） |
| page_size | int | 每页数量（默认 20，最大 100） |

### POST /api/cloud-devices/{id}/connections

连接云手机设备。

**请求体：**
```json
{
  "force_reconnect": false  // 是否强制重连
}
```

**响应：**
```json
{
  "success": true,
  "device_serial": "ip:port",
  "message": "Connected successfully",
  "adb_expire_time": "2024-01-01T12:00:00"
}
```

## 权限控制

- **设备列表 API**：所有已认证用户可访问（普通用户只能看到激活设备）
- **设备详情/增删改 API**：仅限管理员（`is_superuser=True`）
- **ADB 连接 API**：所有已认证用户可访问

## 批量上传格式

### CSV 格式

```csv
product_id,pod_id,alias
prod_001,pod_001,测试设备1
prod_001,pod_002,测试设备2
prod_002,pod_001,
```

### JSON 格式

```json
{
  "devices": [
    {"product_id": "prod_001", "pod_id": "pod_001", "alias": "测试设备1"},
    {"product_id": "prod_001", "pod_id": "pod_002", "alias": "测试设备2"}
  ]
}
```

## 前端功能

- 表格展示：ID、ProductId、PodId、别名、状态、创建时间、操作
- 分页、状态筛选、搜索
- 单个添加 / CSV 批量上传
- 编辑别名、激活/停用切换、删除
- 批量选择 + 批量操作

## ADB 连接管理

### CloudDeviceService 服务

`backend/services/cloud_device_service.py` 封装了火山引擎 SDK 调用，负责 ADB 生命周期管理。

**核心方法：**

| 方法 | 说明 |
|------|------|
| `get_pod_detail(product_id, pod_id)` | 获取 Pod 详情（AdbStatus, Adb, AdbExpireTime） |
| `enable_adb(product_id, pod_id)` | 开启 ADB |
| `disable_adb(product_id, pod_id)` | 关闭 ADB |
| `ensure_adb_connection(product_id, pod_id, force_reconnect)` | 确保 ADB 可用并返回连接地址和过期时间 |
| `adb_connect(adb_address)` | 执行 `adb connect` 命令 |
| `check_device_locked(product_id, pod_id)` | 检查设备是否被锁定 |

### ADB 连接流程

```
POST /api/cloud-devices/{id}/connections 调用时：
1. 调用火山引擎 API 获取 Pod 详情 (DetailPod)
2. 检查 AdbStatus 字段：
   - AdbStatus == 0（未开启）：调用 PodAdb 开启 ADB
   - AdbStatus == 1（已开启）：
     - force_reconnect=true：先关闭再重新开启
     - 距离过期时间 < 6小时：先关闭再重新开启
     - 距离过期时间 >= 6小时：直接使用现有地址
3. 获取 Adb 字段作为连接地址
4. 执行 `adb connect <adb_address>` 连接设备
5. 返回连接结果和 ADB 过期时间
```

### 设备锁定机制

云手机录制复用 `TaskRecordService` 中的设备锁定机制，防止多用户同时操作同一设备。

**工作流程：**
- WebSocket 连接时自动调用 `_try_lock_device` 锁定设备
- 断开连接时自动调用 `_release_device_lock` 释放锁定
- 设备列表 API 响应中包含 `locked_device_ids` 字段，前端据此显示锁定标记

**锁定状态检查：**
`CloudDeviceService.check_device_locked()` 方法通过查询云端 ADB 状态获取 ADB 地址，然后检查该地址是否在 `task_record_service.device_locks` 中。

### 火山引擎 API 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| Adb | string | ADB 连接地址，格式 `ip:port` |
| AdbStatus | int | 0=未开启，1=已开启 |
| AdbExpireTime | string | ADB 过期时间（ISO 8601） |
