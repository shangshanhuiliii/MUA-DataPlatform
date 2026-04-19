# 前端开发规范

## 前端请求规范：统一使用 api/client.js

### 规范说明

所有前端对后端的 HTTP 请求，**必须**通过 `static/js/api/client.js` 中的 `DroidBotAPI` 类方法发起。

**禁止**在 UI 组件中直接使用 `fetch()` 调用后端接口。

```javascript
// ❌ 错误：在组件中直接 fetch
const response = await fetch('/api/batches/1', {
    headers: { 'Authorization': `Bearer ${token}` }
});

// ✅ 正确：通过 api 实例调用
const batch = await api.getBatch(token, 1);
```

### 原因

- **统一错误处理**：`DroidBotAPI.request()` 自动解析后端错误信息，抛出含 `status` 和 `message` 的 Error 对象，组件只需 try/catch 即可
- **避免重复代码**：请求头、baseURL、JSON 解析等样板代码集中在一处
- **便于维护**：接口路径变更时只需修改 `client.js`，不需要在多个组件中查找替换

### 新增接口的操作步骤

1. 在 `client.js` 对应模块的注释区块中添加新方法，遵循现有命名和参数风格
2. 在组件中通过全局 `api` 实例调用（`api.methodName(token, ...)`）

```javascript
// client.js 中添加新方法示例
async getMyNewResource(token, resourceId) {
    return this.request(`/my-resource/${resourceId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
}
```

### 错误处理模式

`request()` 在 `!response.ok` 时抛出 Error，组件中统一用 try/catch 处理：

```javascript
try {
    const data = await api.getSomething(token, id);
    // 处理成功结果
} catch (error) {
    // error.message 包含后端返回的 detail 或 HTTP 状态描述
    // error.status 包含 HTTP 状态码
    alert('操作失败: ' + error.message);
}
```

---

## DroidBotAPI 方法列表

全局实例：`const api = new DroidBotAPI()`（定义在 `client.js` 末尾）

### UTG / 录制编辑

| 方法 | 说明 |
|------|------|
| `getUTG()` | 获取 UTG 图数据 |
| `updateEvent(edgeId, oldEventStr, eventType, eventStr, newFromState, newToState)` | 更新事件 |
| `deleteEvent(edgeId, eventStr)` | 删除事件 |
| `deleteNode(nodeId)` | 删除节点 |
| `getBranchStates(nodeId)` | 获取分支状态 |
| `batchDeleteNodes(nodeIds)` | 批量删除节点 |
| `createEvent(fromState, toState, eventType, eventStr)` | 创建事件 |
| `getTaskInfo()` | 获取任务信息 |
| `updateTaskInfo(taskInfoYaml)` | 更新任务信息 |
| `setFirstState(nodeId)` | 设置起始状态 |
| `setLastState(nodeId)` | 设置终止状态 |
| `setNodeLabels(nodeId, labels, labelMeta)` | 设置节点标签 |
| `getDeletedNodes()` | 获取已删除节点 |
| `batchRestoreNodes(stateList)` | 批量恢复节点 |

### 用户认证

| 方法 | 说明 |
|------|------|
| `login(username, password)` | 登录，返回 token |
| `getCurrentUser(token)` | 获取当前用户信息 |
| `getUsers(token)` | 获取用户列表 |
| `createUser(token, userData)` | 创建用户 |
| `updateUser(token, userId, userData)` | 更新用户 |
| `deleteUser(token, userId)` | 删除用户 |

### 任务管理

| 方法 | 说明 |
|------|------|
| `createTask(token, taskData)` | 创建任务（taskData 含 description、batch_id） |
| `getTaskList(token, params)` | 获取任务列表（支持 batch_id、status 等过滤） |
| `getTaskById(token, taskId)` | 获取单个任务 |
| `updateTask(token, taskId, data)` | 更新任务 |
| `deleteTask(token, taskId)` | 删除任务 |
| `assignTask(token, taskId, userIds)` | 分配任务给用户 |
| `unassignTask(token, taskId, userId)` | 取消任务分配 |
| `bulkUploadTasks(token, uploadData)` | 批量上传任务（uploadData 含 tasks、batch_id） |
| `batchDeleteTasks(token, taskIds)` | 批量删除任务 |
| `batchAssignTasks(token, taskIds, userIds)` | 批量分配任务 |

### 录制数据

| 方法 | 说明 |
|------|------|
| `createRecording(token, taskId, directoryName)` | 创建录制记录 |
| `getRecordings(token, params)` | 获取录制列表 |
| `getRecordingById(token, recordingId)` | 获取单条录制 |
| `updateRecording(token, recordingId, data)` | 更新录制 |
| `deleteRecording(token, recordingId)` | 删除录制 |
| `getCurrentRecording()` | 获取当前录制 |
| `setCurrentRecording(directoryName)` | 设置当前录制 |
| `releaseCurrentRecording()` | 释放当前录制 |

### 批次管理

| 方法 | 说明 |
|------|------|
| `getBatches(token, params)` | 获取批次列表（支持 page、page_size、sort_by、sort_order） |
| `getBatch(token, batchId)` | 获取批次详情 |
| `createBatch(token, data)` | 创建批次 |
| `updateBatch(token, batchId, data)` | 更新批次（含 claim_limit_per_user） |
| `deleteBatch(token, batchId)` | 删除批次 |
| `getBatchAllocations(token, batchId)` | 获取批次用户分配情况（管理员） |
| `saveBatchAllocations(token, batchId, userIds)` | 设置批次用户分配 |
| `getMyBatchAllocation(token, batchId)` | 获取当前用户的认领限额统计 |
| `getClaimableTasks(token, batchId, pageSize)` | 获取可认领的任务列表 |
| `claimTask(token, batchId, taskId)` | 认领任务 |
| `batchMoveTasks(token, taskIds, targetBatchId)` | 批量移动任务到其他批次 |

### 云手机管理

| 方法 | 说明 |
|------|------|
| `getCloudDevices(token, params)` | 获取云手机列表 |
| `getCloudDevice(token, deviceId)` | 获取单个云手机 |
| `createCloudDevice(token, data)` | 创建云手机 |
| `updateCloudDevice(token, deviceId, data)` | 更新云手机 |
| `deleteCloudDevice(token, deviceId)` | 删除云手机 |
| `bulkUploadCloudDevices(token, devices)` | 批量上传云手机 |
| `batchUpdateCloudDeviceStatus(token, deviceIds, isActive)` | 批量更新云手机状态 |
| `batchDeleteCloudDevices(token, deviceIds)` | 批量删除云手机 |
| `connectCloudDevice(token, deviceId, forceReconnect)` | 连接云手机 |
