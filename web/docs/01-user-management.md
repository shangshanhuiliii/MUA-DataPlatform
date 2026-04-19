# 用户管理系统

## 数据库设计

### User 模型

```python
# backend/models/user.py
class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, max_length=50, index=True)
    email: str = Field(unique=True, max_length=100, index=True)
    password_hash: str = Field(max_length=255)
    full_name: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = Field(default=True, index=True)
    is_superuser: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
```

### Schema 定义

```python
# 用户创建请求
class UserCreate(SQLModel):
    username: str       # 3-50 字符，唯一
    email: str          # 最大 100 字符，唯一
    password: str       # 8-100 字符
    full_name: Optional[str] = None
    is_superuser: bool = False

# 用户更新请求
class UserUpdate(SQLModel):
    email: Optional[str] = None
    password: Optional[str] = None    # 8-100 字符
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None

# 用户响应（不包含密码）
class UserResponse(SQLModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime]
```

## 相关文件

```
backend/
├── models/
│   └── user.py              # User SQLModel 模型及 Schema（UserCreate, UserUpdate, UserResponse）
├── schemas/
│   └── auth.py              # 认证相关 schema（Token, TokenData, LoginRequest）
├── database/
│   └── connection.py        # 数据库连接配置
├── crud/
│   └── user.py              # 用户 CRUD 操作
├── auth/
│   ├── __init__.py          # 导出认证函数
│   ├── security.py          # 密码加密、JWT 生成
│   └── dependencies.py      # 认证依赖（get_current_user 等）
└── routers/
    ├── auth.py              # 认证路由（/api/auth）
    └── users.py             # 用户管理路由（/api/users）

static/js/components/
└── user-manager.js          # 用户管理前端组件
```

## API 端点

### 认证 API（/api/auth）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/register | 用户注册 |
| POST | /api/auth/login | 用户登录（JSON 格式） |
| POST | /api/auth/token | OAuth2 兼容端点（表单格式，用于 Swagger UI） |
| GET | /api/auth/me | 获取当前用户信息 |

#### POST /api/auth/register

用户注册，创建新账户。

**请求体：**
```json
{
  "username": "string",    // 3-50 字符，唯一
  "email": "string",       // 唯一
  "password": "string",    // 至少 8 字符
  "full_name": "string"    // 可选
}
```

**响应：** `201 Created` - UserResponse

#### POST /api/auth/login

用户登录，返回 JWT Token。

**请求体：**
```json
{
  "username": "string",
  "password": "string"
}
```

**响应：**
```json
{
  "access_token": "string",
  "token_type": "bearer"
}
```

**错误：**
- `401 Unauthorized` - 用户名或密码错误
- `400 Bad Request` - 用户已被禁用（is_active=false）

### 用户管理 API（/api/users）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | /api/users | 已认证 | 获取用户列表 |
| GET | /api/users/{user_id} | 已认证 | 获取用户详情 |
| POST | /api/users | 管理员 | 创建新用户 |
| PUT | /api/users/{user_id} | 已认证 | 更新用户信息 |
| DELETE | /api/users/{user_id} | 管理员 | 删除用户 |

#### GET /api/users

获取用户列表。

**查询参数：**
- `skip`: 跳过的记录数（默认 0）
- `limit`: 返回的最大记录数（默认 100，最大 1000）
- `is_active`: 筛选激活状态（可选）

**权限：**
- 管理员：返回所有用户
- 普通用户：只返回自己的信息

#### POST /api/users

创建新用户（仅管理员）。

**请求体：** UserCreate

**错误：**
- `400 Bad Request` - 用户名或邮箱已存在

#### PUT /api/users/{user_id}

更新用户信息。

**请求体：** UserUpdate（所有字段可选）

**权限：**
- 普通用户：只能更新自己，不能修改 is_superuser
- 管理员：可以更新任何用户

#### DELETE /api/users/{user_id}

删除用户（仅管理员）。

**限制：**
- 不能删除自己
- 不能删除有关联数据的用户（任务分配、录制记录）

**错误：**
- `400 Bad Request` - 尝试删除自己
- `409 Conflict` - 存在关联数据，返回详细信息

## 权限模型

### 普通用户 (is_superuser=False)

- 查看和编辑自己的信息
- 不能修改自己的 is_superuser 状态
- 查看分配给自己的任务
- 录制分配给自己的任务

### 管理员 (is_superuser=True)

- 管理所有用户（创建、编辑、删除）
- 管理所有任务（创建、编辑、删除）
- 分配任务给用户
- 查看所有录制数据
- 管理云手机设备

## 安全措施

### 密码安全

- 使用 bcrypt 哈希（passlib 库）
- 密码最少 8 字符，最多 100 字符
- bcrypt 限制：最多处理 72 字节

### JWT 认证

| 配置项 | 环境变量 | 默认值 |
|--------|----------|--------|
| 签名密钥 | SECRET_KEY | - |
| 算法 | ALGORITHM | HS256 |
| 过期时间 | ACCESS_TOKEN_EXPIRE_MINUTES | 30 |

**使用方式：**
```
Authorization: Bearer <token>
```

### 其他安全措施

- **SQL 注入防护**：SQLModel ORM 自动参数化查询
- **权限控制**：基于 is_superuser 的 RBAC
- **用户状态检查**：登录时验证 is_active 状态，禁用用户无法登录
- **关联数据保护**：删除用户前检查任务分配和录制记录
