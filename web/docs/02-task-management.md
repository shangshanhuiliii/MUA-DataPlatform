# 任务管理系统

## 数据库设计

### tasks 表

```python
class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    description: str = Field(index=True)  # 任务描述/操作指令
    status: str = Field(default="pending")  # pending/in_progress/completed
    batch_id: Optional[int] = Field(default=None, foreign_key="batches.id", index=True)
    created_by: int = Field(foreign_key="users.id")  # 创建者（管理员）
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### task_assignments 表（任务分配）

```python
class TaskAssignment(SQLModel, table=True):
    __tablename__ = "task_assignments"
    __table_args__ = (
        UniqueConstraint('task_id', 'user_id', name='unique_task_user'),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_by: int = Field(foreign_key="users.id")  # 分配者
```

### recordings 表（录制数据）

```python
class Recording(SQLModel, table=True):
    __tablename__ = "recordings"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", index=True)
    recorded_by: int = Field(foreign_key="users.id", index=True)  # 录制者
    directory_name: str = Field(unique=True)  # 录制目录名
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### 数据关系

```
User (1) ←→ (N) Task (created_by)
User (1) ←→ (N) TaskAssignment (user_id)
Task (1) ←→ (N) TaskAssignment (task_id)
Task (1) ←→ (N) Recording (task_id)
User (1) ←→ (N) Recording (recorded_by)
```

### Schema 定义

```python
# 任务创建请求
class TaskCreate(BaseModel):
    description: str  # 1-1000 字符

# 任务更新请求
class TaskUpdate(BaseModel):
    description: Optional[str] = None  # 1-1000 字符
    status: Optional[str] = None       # pending/in_progress/completed

# 任务响应
class TaskResponse(BaseModel):
    id: int
    description: str
    status: str
    created_by: int
    created_at: datetime
    updated_at: datetime
    assigned_users: List[UserBrief]  # 分配的用户列表
    recording_count: int             # 录制数量

# 任务列表响应（分页）
class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int
```

## 相关文件

```
backend/
├── models/
│   ├── task.py              # Task 模型
│   ├── task_assignment.py   # TaskAssignment 模型
│   └── recording.py         # Recording 模型
├── crud/
│   ├── task.py              # Task 和 TaskAssignment CRUD
│   └── recording.py         # Recording CRUD
├── routers/
│   ├── tasks.py             # 任务管理路由（含 Task Info API）
│   └── recordings.py        # 录制数据管理路由
├── schemas/
│   ├── task.py              # Task 请求/响应模型（含 TaskInfo schemas）
│   └── recording.py         # Recording 请求/响应模型
├── services/
│   ├── task_service.py      # Task Info 服务（读写 task-info.yaml）
│   └── task_record_service.py  # 任务录制服务
└── session_config.py        # Session 配置（含录制互斥锁）

static/js/
├── api/
│   └── client.js            # API 客户端（DroidBotAPI 类）
└── components/
    ├── task-manager.js      # 任务管理组件
    └── task-recorder.js     # 任务录制组件
```

## API 端点

### 任务管理 API（/api/tasks）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | /api/tasks | 管理员 | 创建任务 |
| GET | /api/tasks | 已认证 | 获取任务列表 |
| GET | /api/tasks/{task_id} | 已认证 | 获取任务详情 |
| PUT | /api/tasks/{task_id} | 管理员 | 更新任务 |
| DELETE | /api/tasks/{task_id} | 管理员 | 删除任务 |
| POST | /api/tasks/{task_id}/assignments | 管理员 | 分配任务给用户 |
| DELETE | /api/tasks/{task_id}/assignments/{user_id} | 管理员 | 取消分配 |
| POST | /api/tasks/batch | 管理员 | 批量上传任务 |
| DELETE | /api/tasks?ids=1,2,3 | 管理员 | 批量删除任务 |
| PATCH | /api/tasks/assignments | 管理员 | 批量分配任务 |

### Task Info API（基于 Session）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | /api/task-info | Session | 获取当前录制的 task-info.yaml 内容 |
| PUT | /api/task-info | Session | 更新当前录制的 task-info.yaml 内容 |

> 注：Task Info API 依赖 session 中的 `current_recording`，需先通过 `/api/recordings/current/{directory_name}` 设置当前录制。

### 录制数据 API

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | /api/recordings | 已认证 | 创建录制记录 |
| GET | /api/recordings | 已认证 | 获取录制列表 |
| GET | /api/recordings/{recording_id} | 已认证 | 获取录制详情 |
| PUT | /api/recordings/{recording_id} | 所有者/管理员 | 更新录制记录 |
| DELETE | /api/recordings/{recording_id} | 所有者/管理员 | 删除录制记录 |
| GET | /api/recordings/current | 已认证 | 获取当前选中的录制 |
| POST | /api/recordings/current/{directory_name} | 已认证 | 设置当前录制（带互斥锁） |
| DELETE | /api/recordings/current | 已认证 | 释放当前录制 |

## 权限控制

### 任务权限

```python
# 非管理员只能查看分配给自己的任务
if not current_user.is_superuser:
    if not task_crud.is_task_assigned_to_user(session, task_id, current_user.id):
        raise HTTPException(status_code=403, detail="You don't have access to this task")
```

### 录制权限

```python
# 非管理员只能操作自己的录制
if not current_user.is_superuser and recording.recorded_by != current_user.id:
    raise HTTPException(status_code=403, detail="You don't have permission")
```

## 前端 API 客户端

所有 API 调用集中在 `static/js/api/client.js` 的 `DroidBotAPI` 类中：

```javascript
// 任务管理（需要传 token）
api.createTask(token, description)
api.getTaskList(token, params)        // params: {status, page, page_size}
api.getTaskById(token, taskId)
api.updateTask(token, taskId, data)   // data: {description, status}
api.deleteTask(token, taskId)
api.assignTask(token, taskId, userIds)
api.unassignTask(token, taskId, userId)
api.bulkUploadTasks(token, tasks)     // tasks: string[]
api.batchDeleteTasks(token, taskIds)
api.batchAssignTasks(token, taskIds, userIds)

// Task Info（基于 session，无需 token）
api.getTaskInfo()                     // 获取当前录制的 task-info.yaml
api.updateTaskInfo(taskInfoYaml)      // 更新当前录制的 task-info.yaml
```

### 前端 API 与后端路由对应

| 前端方法 | HTTP 方法 | 后端路由 |
|---------|----------|---------|
| createTask | POST | /api/tasks |
| getTaskList | GET | /api/tasks |
| getTaskById | GET | /api/tasks/{task_id} |
| updateTask | PUT | /api/tasks/{task_id} |
| deleteTask | DELETE | /api/tasks/{task_id} |
| assignTask | POST | /api/tasks/{task_id}/assignments |
| unassignTask | DELETE | /api/tasks/{task_id}/assignments/{user_id} |
| bulkUploadTasks | POST | /api/tasks/batch |
| batchDeleteTasks | DELETE | /api/tasks?ids=1,2,3 |
| batchAssignTasks | PATCH | /api/tasks/assignments |

## 数据存储

| 数据类型 | 存储位置 | 说明 |
|---------|---------|------|
| 结构化数据 | MySQL | 用户、任务、分配关系、录制元数据 |
| 录制文件 | data/record/ | UTG 数据目录（截图、视频等） |
| 路径引用 | MySQL recording.directory_name | 指向 data/ 下的目录 |

## 批量上传任务

支持 TXT 文件批量导入，每行一个任务描述：

```txt
用美团小程序，帮我点一份【宫保鸡丁】和一碗【白米饭】送到家
用饿了么小程序，帮我在公司附近下单一份【水煮牛肉】
用美团小程序，帮我点一份【麻婆豆腐】送到"上海市黄浦区南京东路299号"
```
