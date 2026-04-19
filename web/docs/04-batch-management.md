# 批次管理系统

批次管理功能用于将任务按批次进行组织和管理。管理员可以创建批次、向批次中添加任务、为用户分配批次访问权限，并设置每用户的认领上限；普通用户则可以在限额范围内认领任务。

## 数据库设计

### batches 表

```python
# backend/models/batch.py
DEFAULT_CLAIM_LIMIT_PER_USER = 10

class Batch(SQLModel, table=True):
    __tablename__ = "batches"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = Field(default=None)
    claim_limit_per_user: int = Field(default=DEFAULT_CLAIM_LIMIT_PER_USER, nullable=False)
    created_by: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

`claim_limit_per_user`：批次级别的每用户认领上限，所有被分配到该批次的用户名下待录制的任务数受该上限限制。

### batch_allocations 表（批次用户分配）

```python
# backend/models/batch_allocation.py
class BatchAllocation(SQLModel, table=True):
    __tablename__ = "batch_allocations"
    __table_args__ = (
        UniqueConstraint('batch_id', 'user_id', name='unique_batch_user_allocation'),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="batches.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    allocated_by: int = Field(foreign_key="users.id")
    allocated_at: datetime = Field(default_factory=datetime.utcnow)
```

记录哪些用户被分配到了某个批次。认领上限统一从 `batches.claim_limit_per_user` 读取，不再在分配记录中单独存储。

### tasks 表（新增 batch_id 字段）

```python
# backend/models/task.py（修改）
class Task(SQLModel, table=True):
    # ... 原有字段 ...
    batch_id: Optional[int] = Field(default=None, foreign_key="batches.id", index=True)
```

### 数据关系

```
Batch (1) ←→ (N) Task            (tasks.batch_id)
Batch (1) ←→ (N) BatchAllocation (batch_allocations.batch_id)
User  (1) ←→ (N) BatchAllocation (batch_allocations.user_id)
Task  (1) ←→ (N) TaskAssignment  (task_assignments.task_id)   ← 用户认领记录
User  (1) ←→ (N) TaskAssignment  (task_assignments.user_id)
```

### Schema 定义

```python
# 批次创建请求
class BatchCreate(BaseModel):
    name: str
    description: Optional[str] = None

# 批次更新请求
class BatchUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    claim_limit_per_user: Optional[int] = Field(default=None, ge=1)

# 批次统计信息
class BatchStatistics(BaseModel):
    total: int                           # 任务总数
    pending: int                         # 待执行
    in_progress: int                     # 进行中
    completed: int                       # 已完成
    assigned_user_count: int             # 已认领任务的用户数
    assigned_usernames: List[str] = []   # 已认领任务的用户名列表
    allocated_usernames: List[str] = []  # 已分配到批次的用户名列表

# 批次响应
class BatchResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    claim_limit_per_user: int            # 每用户认领上限
    created_by: int
    created_at: datetime
    updated_at: datetime
    statistics: Optional[BatchStatistics] = None

# 批次列表响应（分页）
class BatchListResponse(BaseModel):
    batches: List[BatchResponse]
    total: int
    page: int
    page_size: int

# 批次用户分配请求
class BatchAllocationRequest(BaseModel):
    user_ids: List[int]

# 用户认领限额统计响应
class AllocationStatsResponse(BaseModel):
    claim_limit_per_user: int  # 批次认领上限
    occupied: int              # 已占用（已认领且未完成的任务数）
    available: int             # 剩余可认领数

# 认领任务请求
class ClaimTaskRequest(BaseModel):
    task_id: int

# 批量移动任务请求
class BatchMoveRequest(BaseModel):
    task_ids: List[int]
    target_batch_id: Optional[int] = None  # None 表示移动到独立任务
```

## 相关文件

```
backend/
├── models/
│   ├── batch.py                # Batch SQLModel 模型
│   └── batch_allocation.py     # BatchAllocation SQLModel 模型
├── schemas/
│   ├── batch.py                # 批次请求/响应 Pydantic 模型
│   └── batch_allocation.py     # 分配请求/响应模型
├── crud/
│   ├── batch.py                # 批次 CRUD 操作
│   └── batch_allocation.py     # 分配 CRUD 操作（含认领逻辑）
└── routers/
    ├── batches.py              # 批次管理路由（/api/batches）
    └── batch_allocations.py    # 分配路由（/api/batches/{id}/allocations 等）

static/js/
├── api/
│   └── client.js               # 批次相关 API 方法（见"前端 API 客户端"章节）
└── components/
    ├── batch-manager.js        # 批次管理前端组件（卡片看板）
    └── task-manager.js         # 任务管理组件（批次模式 + 认领弹窗）

alembic/versions/
├── 2b4cf6fc0424_create_batch_table.py               # 创建 batches、batch_allocations 表 + tasks.batch_id
├── bbb4058d5529_seed_legacy_migration_batch.py       # 创建"历史迁移批次"并回填历史无批次任务
└── c3d4e5f6a7b8_add_claim_limit_per_user_to_batches.py  # 迁移配额字段到批次级别
```

## API 端点

### 批次管理 API（/api/batches）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | /api/batches | 管理员 | 创建批次 |
| GET | /api/batches | 已认证 | 获取批次列表（分页） |
| GET | /api/batches/{batch_id} | 已认证 | 获取批次详情 |
| PUT | /api/batches/{batch_id} | 管理员 | 更新批次 |
| DELETE | /api/batches/{batch_id} | 管理员 | 删除批次（级联删除任务） |

#### POST /api/batches

创建批次（仅管理员）。

**请求体：**
```json
{
  "name": "string",
  "description": "string"
}
```

**响应：** `201 Created` - BatchResponse（含 statistics）

#### GET /api/batches

获取批次列表（分页），每个批次包含统计信息。

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| sort_by | string | 排序字段（默认 `created_at`） |
| sort_order | string | 排序方向 `asc`/`desc`（默认 `desc`） |
| page | int | 页码（默认 1） |
| page_size | int | 每页数量（默认 20，最大 100） |

**响应示例：**
```json
{
  "batches": [
    {
      "id": 1,
      "name": "第一批次",
      "description": "测试批次",
      "claim_limit_per_user": 10,
      "created_by": 1,
      "created_at": "2026-03-07T16:00:00",
      "updated_at": "2026-03-07T16:00:00",
      "statistics": {
        "total": 100,
        "pending": 60,
        "in_progress": 30,
        "completed": 10,
        "assigned_user_count": 3,
        "assigned_usernames": ["user1", "user2"],
        "allocated_usernames": ["user1", "user2", "user3"]
      }
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

#### PUT /api/batches/{batch_id}

更新批次（仅管理员）。

**请求体：**
```json
{
  "name": "string",
  "description": "string",
  "claim_limit_per_user": 10
}
```

所有字段均为可选，仅传入需要修改的字段。

#### DELETE /api/batches/{batch_id}

删除批次（仅管理员）。**级联删除**批次下的所有数据：

1. 删除批次分配记录（batch_allocations）
2. 删除任务分配记录（task_assignments，通过任务关联）
3. 删除批次下的所有任务（tasks）
4. 删除批次本身（batches）

### 批次分配 API（/api/batches/{id}/allocations）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | /api/batches/{batch_id}/allocations | 管理员 | 设置批次用户分配 |
| GET | /api/batches/{batch_id}/allocations | 管理员 | 查看批次分配情况 |
| GET | /api/batches/{batch_id}/my-allocation | 已认证 | 获取我的认领限额统计 |
| POST | /api/batches/{batch_id}/claim-task | 已认证 | 认领任务 |
| GET | /api/batches/{batch_id}/claimable-tasks | 已认证 | 获取可认领的任务列表 |

#### POST /api/batches/{batch_id}/allocations

设置批次的用户分配（仅管理员）。传入完整的用户列表，不在列表中的用户将被移除分配记录。

**请求体：**
```json
{
  "user_ids": [1, 2, 3]
}
```

**响应：**
```json
{
  "success": 3,
  "failed": 0,
  "errors": []
}
```

#### GET /api/batches/{batch_id}/allocations

查看批次分配情况（仅管理员）。

**响应：**
```json
{
  "batch_id": 1,
  "allocations": [
    {
      "user_id": 1,
      "username": "user1",
      "occupied": 3,
      "available": 7,
      "allocated_at": "2026-03-07T16:00:00"
    }
  ]
}
```

`occupied` 和 `available` 基于批次的 `claim_limit_per_user` 计算。

#### GET /api/batches/{batch_id}/my-allocation

获取当前用户在该批次的认领限额统计。用户未被分配到该批次时返回 `404`。

**响应：**
```json
{
  "claim_limit_per_user": 10,
  "occupied": 3,
  "available": 7
}
```

- `claim_limit_per_user`：批次认领上限
- `occupied`：已认领且未完成的任务数
- `available`：剩余可认领数（`claim_limit_per_user - occupied`）

#### POST /api/batches/{batch_id}/claim-task

认领任务（带并发控制）。使用数据库行锁（`SELECT ... FOR UPDATE`）防止多用户同时认领同一任务。

**请求体：**
```json
{
  "task_id": 42
}
```

**认领流程：**
1. 验证用户有该批次的分配记录（BatchAllocation）
2. 计算当前占用数（未完成任务数）
3. 检查是否已达到 `claim_limit_per_user`
4. 使用 `FOR UPDATE` 锁定目标任务，验证任务为 `pending` 状态
5. 检查任务尚未被认领（无 TaskAssignment 记录）
6. 创建 TaskAssignment 记录

**错误：**
- `400 Bad Request` - 已达到认领限额 / 任务不可用 / 任务已被认领 / 无分配记录

#### GET /api/batches/{batch_id}/claimable-tasks

获取批次中可认领的任务（`pending` 状态且无 TaskAssignment 记录）。

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| page | int | 页码（默认 1） |
| page_size | int | 每页数量（默认 50，最大 5000） |

**响应：**
```json
{
  "tasks": [
    {
      "id": 1,
      "description": "任务描述",
      "status": "pending",
      "created_at": "2026-03-07T16:00:00"
    }
  ],
  "total": 50,
  "page": 1,
  "page_size": 50
}
```

### 任务批次集成

在原有任务 API 中新增了批次相关功能：

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | /api/tasks?batch_id=1 | 已认证 | 按批次筛选任务 |
| POST | /api/tasks | 管理员 | 创建任务时可指定 batch_id |
| POST | /api/tasks/batch | 管理员 | 批量上传任务时可指定 batch_id |
| PATCH | /api/tasks/batch-move | 管理员 | 批量移动任务到其他批次 |

#### PATCH /api/tasks/batch-move

批量移动任务到其他批次（仅管理员）。

**请求体：**
```json
{
  "task_ids": [1, 2, 3],
  "target_batch_id": 2
}
```

`target_batch_id` 为 `null` 时，将任务移出批次（`batch_id` 置为 `null`）。

## 权限控制

### 管理员 (is_superuser=True)

- 创建、编辑、删除批次
- 设置批次的每用户认领上限（`claim_limit_per_user`）
- 为批次分配用户（管理 BatchAllocation 记录）
- 查看批次分配情况
- 批量移动任务到不同批次

### 普通用户 (is_superuser=False)

- 查看批次列表和详情
- 查看自己在批次中的认领限额统计
- 通过"领取任务"弹窗批量认领任务（需有分配记录）
- 查看批次中可认领的任务

## 前端功能

### 批次看板（batch-manager.js）

- **卡片布局**：每个批次以卡片形式展示，包含名称、描述、统计信息（总数/待执行/进行中/已完成）、已分配用户列表
- **分页**：支持翻页浏览
- **操作**：创建批次、编辑批次（含认领上限）、删除批次、查看批次内任务、管理用户分配

### 批次内任务视图（task-manager.js）

点击批次卡片的"查看任务"按钮后，任务管理组件进入**批次模式**：

- 显示批次面包屑导航（可返回批次列表）
- 筛选显示当前批次下的任务
- 支持在批次内创建任务（自动关联 batch_id）
- 支持批量上传任务到当前批次
- **领取任务**：点击"领取任务"按钮，弹窗展示可认领的任务列表（默认全选），用户确认后批量认领

## 前端 API 客户端

所有批次相关请求通过 `static/js/api/client.js` 中的 `DroidBotAPI` 全局实例 `api` 发起：

```javascript
// 批次 CRUD
api.getBatches(token, {page, page_size, sort_by, sort_order})
api.getBatch(token, batchId)
api.createBatch(token, {name, description})
api.updateBatch(token, batchId, {name, description, claim_limit_per_user})
api.deleteBatch(token, batchId)

// 用户分配
api.getBatchAllocations(token, batchId)
api.saveBatchAllocations(token, batchId, userIds)
api.getMyBatchAllocation(token, batchId)

// 任务认领
api.getClaimableTasks(token, batchId, pageSize)
api.claimTask(token, batchId, taskId)

// 任务批次集成
api.batchMoveTasks(token, taskIds, targetBatchId)
api.createTask(token, {description, batch_id})
api.getTaskList(token, {batch_id, ...})
api.bulkUploadTasks(token, {tasks, batch_id})
```

## 数据库迁移

### 迁移 1：`2b4cf6fc0424_create_batch_table`

- 创建 `batches` 表（id, name, description, created_by, created_at, updated_at）
- 创建 `batch_allocations` 表（id, batch_id, user_id, quota, allocated_by, allocated_at）
- 在 `tasks` 表添加 `batch_id` 列（可为空的外键）
- 创建索引和唯一约束

### 迁移 2：`bbb4058d5529_seed_legacy_migration_batch`

- 创建系统批次：`历史迁移批次`
- 使用默认管理员作为该批次的创建者
- 将所有 `tasks.batch_id IS NULL` 的历史任务回填到该批次
- 该批次仅用于承接历史任务，后续由管理员逐步迁移到实际业务批次

### 迁移 3：`c3d4e5f6a7b8_add_claim_limit_per_user_to_batches`

- 在 `batches` 表添加 `claim_limit_per_user` 列（默认值 10）
- 将 `batch_allocations.quota` 的最大值迁移为批次级别的认领上限
- 删除 `batch_allocations.quota` 列（认领上限统一由批次管理）

### 执行迁移

```bash
cd web/
alembic upgrade head
```
