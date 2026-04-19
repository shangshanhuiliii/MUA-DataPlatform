/**
 * Task Manager Component
 * Handles task management for administrators
 */
class TaskManager {
    constructor(containerId) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.tasks = [];
        this.users = [];
        this.selectedTaskIds = new Set();
        this.currentPage = 1;
        this.pageSize = 20;
        this.totalPages = 1;
        this.statusFilter = '';
        this.searchKeyword = '';
        this.sortBy = 'created_at';
        this.sortOrder = 'desc';
        this.token = localStorage.getItem('auth_token');
        this.isVisible = false;
        this.batchMode = false;
        this.currentBatchId = null;
        this.currentBatch = null;
        this.currentUser = null;
        this.allocationStats = null;
        this.claimableTasks = []; // 可领取的任务列表
        this.selectedClaimTaskIds = new Set(); // 模态框中选中的任务ID
        this.userFilter = '';
        this.dateFrom = '';
        this.dateTo = '';
        this.filterUsers = null; // 用户列表缓存
        this.init();
    }

    init() {
        this.render();
    }

    render() {
        this.container.innerHTML = `
            <div class="task-manager">
                <div class="panel panel-default">
                    <div class="panel-heading">
                        <div id="batch-breadcrumb" style="display: none; align-items: center;">
                            <nav aria-label="breadcrumb">
                                <ol class="breadcrumb" style="margin: 0; background: none; padding: 0;">
                                    <li><a href="#" onclick="window.app.taskManager.exitBatchMode(); return false;">任务管理</a></li>
                                    <li class="active" id="batch-name-breadcrumb">批次</li>
                                </ol>
                            </nav>
                            <button class="btn btn-default" style="margin-left: 15px;" onclick="window.app.taskManager.exitBatchMode()">
                                <span class="glyphicon glyphicon-arrow-left"></span> 返回批次列表
                            </button>
                            <!-- 管理员按钮区 -->
                            <div id="admin-buttons-section" style="display: none; margin-left: 10px;">
                                <button class="btn btn-info" onclick="window.app.taskManager.editBatchInfo()">
                                    <span class="glyphicon glyphicon-edit"></span> 修改信息
                                </button>
                                <button class="btn btn-danger" onclick="window.app.taskManager.deleteBatch()">
                                    <span class="glyphicon glyphicon-trash"></span> 删除批次
                                </button>
                                <button class="btn btn-success" onclick="window.app.taskManager.showTaskAllocModal('add')">
                                    <span class="glyphicon glyphicon-plus"></span> 添加用户
                                </button>
                                <button class="btn btn-danger" onclick="window.app.taskManager.showTaskAllocModal('delete')">
                                    <span class="glyphicon glyphicon-minus"></span> 删除用户
                                </button>
                            </div>
                        </div>
                        <h4 id="task-manager-title">任务管理</h4>
                    </div>
                    <div class="panel-body">
                        <!-- 批次信息区 -->
                        <div id="batch-info-section" class="well" style="display: none; margin-bottom: 15px;">
                            <div style="display: flex; align-items: center; gap: 20px;;">
                                <h3 id="batch-title-display" class="task-batch-info-title" style="margin-top: 0; margin-bottom: 0;"></h3>
                                <button class="btn btn-success" onclick="window.app.taskManager.showClaimTaskModal()">
                                    <span class="glyphicon glyphicon-hand-up"></span> 领取任务
                                </button>
                            </div>
                            <div id="batch-desc-display" class="text-muted" style="margin-top: 6px;"></div>
                            <div style="margin-top: 10px;">
                                <span class="label label-default task-batch-info-stat">总数: <span id="batch-stat-total">0</span></span>
                                <span class="label label-warning task-batch-info-stat">待执行: <span id="batch-stat-pending">0</span></span>
                                <span class="label label-info task-batch-info-stat">进行中: <span id="batch-stat-in-progress">0</span></span>
                                <span class="label label-success task-batch-info-stat">已完成: <span id="batch-stat-completed">0</span></span>
                            </div>
                            <div class="text-muted" style="margin-top: 4px;">已分配用户: <span id="batch-stat-allocated">无</span></div>
                            <div class="text-muted" style="margin-top: 4px;">已参与录制用户: <span id="batch-stat-users">无</span></div>
                            <div style="margin-top: 8px;">
                                <span class="label label-primary task-batch-info-claim-limit" id="allocation-claim-limit-display" style="display: none;">
                                    领取限额: 当前占用<span id="batch-allocation-occupied">0</span>/上限<span id="batch-allocation-claim-limit">0</span>/可领取<span id="batch-allocation-available">0</span>
                                </span>
                            </div>
                        </div>
                        <div class="row" style="margin-bottom: 15px;">
                            <div class="col-sm-8">
                                <button class="btn btn-success" onclick="window.app.taskManager.showCreateTaskModal()">
                                    <span class="glyphicon glyphicon-plus"></span> 创建任务
                                </button>
                                <button class="btn btn-info" onclick="window.app.taskManager.showBatchUploadModal()">
                                    <span class="glyphicon glyphicon-upload"></span> 批量上传
                                </button>
                                <button class="btn btn-primary" id="batch-assign-btn" onclick="window.app.taskManager.showBatchAssignModal()" disabled>
                                    <span class="glyphicon glyphicon-user"></span> 批量分配
                                </button>
                                <button class="btn btn-danger" id="batch-delete-btn" onclick="window.app.taskManager.batchDelete()" disabled>
                                    <span class="glyphicon glyphicon-trash"></span> 批量删除
                                </button>
                                <button class="btn btn-warning" id="batch-move-btn" onclick="window.app.taskManager.showBatchMoveModal()" disabled>
                                    <span class="glyphicon glyphicon-move"></span> 移动到其他批次
                                </button>
                                <span id="selected-count" style="margin-left: 10px; color: #666;"></span>
                            </div>
                            <div class="col-sm-4 text-right">
                                <div class="input-group" style="display: inline-flex; width: auto; vertical-align: middle; margin-right: 8px;">
                                    <input type="text" id="task-search-input" class="form-control" style="width: 180px;" placeholder="搜索任务描述..." onkeydown="if(event.key==='Enter') window.app.taskManager.handleSearch()">
                                    <span class="input-group-btn">
                                        <button class="btn btn-default" onclick="window.app.taskManager.handleSearch()">
                                            <span class="glyphicon glyphicon-search"></span>
                                        </button>
                                    </span>
                                </div>
                                <div style="display: inline-block; position: relative;">
                                    <button class="btn btn-default" id="task-filter-btn" onclick="window.app.taskManager.toggleFilterPanel()">
                                        <span class="glyphicon glyphicon-filter"></span> 筛选
                                        <span class="badge" id="task-filter-badge" style="display:none; margin-left:4px;"></span>
                                    </button>
                                    <div id="task-filter-panel" style="display:none; position:absolute; right:0; top:100%; z-index:1050; background:#fff; border:1px solid #ddd; border-radius:4px; padding:12px; min-width:280px; box-shadow:0 2px 8px rgba(0,0,0,0.15); margin-top:4px;">
                                        <div class="form-group" style="margin-bottom:8px;">
                                            <label style="font-size:12px;">状态</label>
                                            <select id="task-filter-status" class="form-control input-sm">
                                                <option value="">全部</option>
                                                <option value="pending">待执行</option>
                                                <option value="in_progress">进行中</option>
                                                <option value="completed">已完成</option>
                                            </select>
                                        </div>
                                        <div class="form-group" id="task-filter-user-group" style="margin-bottom:8px; display:none;">
                                            <label style="font-size:12px;">分配用户</label>
                                            <select id="task-filter-user" class="form-control input-sm">
                                                <option value="">全部</option>
                                            </select>
                                        </div>
                                        <div class="form-group" style="margin-bottom:8px;">
                                            <label style="font-size:12px;">创建时间（起）</label>
                                            <input type="date" id="task-filter-date-from" class="form-control input-sm">
                                        </div>
                                        <div class="form-group" style="margin-bottom:8px;">
                                            <label style="font-size:12px;">创建时间（止）</label>
                                            <input type="date" id="task-filter-date-to" class="form-control input-sm">
                                        </div>
                                        <div style="display:flex; gap:6px; justify-content:flex-end;">
                                            <button class="btn btn-default btn-sm" onclick="window.app.taskManager.clearFilters()">重置</button>
                                            <button class="btn btn-primary btn-sm" onclick="window.app.taskManager.applyFilters()">应用</button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <table class="table table-striped table-hover" id="tasks-table">
                            <thead>
                                <tr>
                                    <th style="width: 40px;"><input type="checkbox" id="select-all-tasks" onchange="window.app.taskManager.toggleSelectAll(this.checked)"></th>
                                    <th style="cursor: pointer;" data-sort-field="id">
                                        ID <span class="sort-indicator" data-field="id"></span>
                                    </th>
                                    <th style="cursor: pointer;" data-sort-field="description">
                                        描述 <span class="sort-indicator" data-field="description"></span>
                                    </th>
                                    <th style="cursor: pointer;" data-sort-field="status">
                                        状态 <span class="sort-indicator" data-field="status"></span>
                                    </th>
                                    <th style="cursor: pointer;" data-sort-field="assigned_count">
                                        分配用户 <span class="sort-indicator" data-field="assigned_count"></span>
                                    </th>
                                    <th style="cursor: pointer;" data-sort-field="recording_count">
                                        录制数 <span class="sort-indicator" data-field="recording_count"></span>
                                    </th>
                                    <th style="cursor: pointer;" data-sort-field="created_at">
                                        创建时间 <span class="sort-indicator" data-field="created_at"></span>
                                    </th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody id="tasks-table-body"></tbody>
                        </table>
                        <div id="tasks-pagination" class="text-center"></div>
                    </div>
                </div>
            </div>

            <!-- Create/Edit Task Modal -->
            <div class="modal fade" id="task-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title" id="task-modal-title">创建任务</h4>
                        </div>
                        <div class="modal-body">
                            <form id="task-form">
                                <input type="hidden" id="task-id">
                                <div class="form-group">
                                    <label>任务描述 *</label>
                                    <textarea class="form-control" id="task-description" rows="3" required></textarea>
                                </div>
                                <div class="form-group" id="task-status-group" style="display: none;">
                                    <label>状态</label>
                                    <select class="form-control" id="task-status">
                                        <option value="pending">待执行</option>
                                        <option value="in_progress">进行中</option>
                                        <option value="completed">已完成</option>
                                    </select>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.taskManager.saveTask()">保存</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Batch Upload Modal -->
            <div class="modal fade" id="batch-upload-modal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title">批量上传任务</h4>
                        </div>
                        <div class="modal-body">
                            <div class="form-group">
                                <label>选择 TXT 文件（每行一个任务）</label>
                                <input type="file" class="form-control" id="batch-file" accept=".txt" onchange="window.app.taskManager.handleFileSelect(event)">
                            </div>
                            <div class="form-group">
                                <label>预览（前10条）</label>
                                <div id="batch-preview" style="max-height: 200px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; background: #f9f9f9;"></div>
                            </div>
                            <div id="batch-count"></div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.taskManager.uploadBatch()">上传</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Assign Task Modal (single) -->
            <div class="modal fade" id="assign-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title">分配任务</h4>
                        </div>
                        <div class="modal-body">
                            <input type="hidden" id="assign-task-id">
                            <p id="assign-task-desc"></p>
                            <hr>
                            <div id="assign-users-list"></div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.taskManager.saveAssignment()">保存</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Batch Assign Modal -->
            <div class="modal fade" id="batch-assign-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title">批量分配任务</h4>
                        </div>
                        <div class="modal-body">
                            <p id="batch-assign-info"></p>
                            <hr>
                            <div id="batch-assign-users-list"></div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.taskManager.saveBatchAssignment()">分配</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Batch Move Modal -->
            <div class="modal fade" id="batch-move-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title">移动任务到其他批次</h4>
                        </div>
                        <div class="modal-body">
                            <p id="batch-move-info"></p>
                            <hr>
                            <div class="form-group">
                                <label>选择目标批次</label>
                                <select class="form-control" id="target-batch-select">
                                    <!-- 动态加载批次选项 -->
                                </select>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-warning" onclick="window.app.taskManager.saveBatchMove()">
                                确认移动
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="modal fade" id="task-batch-modal" tabindex="-1"> <!-- 修改 ID -->
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title" id="task-batch-modal-title">编辑批次</h4> <!-- 修改标题 ID -->
                        </div>
                        <div class="modal-body">
                            <form id="task-batch-form"> <!-- 修改表单 ID -->
                                <input type="hidden" id="task-batch-id"> <!-- 修改批次ID输入框 -->
                                <div class="form-group">
                                    <label for="task-batch-name">批次名称 *</label>
                                    <input type="text" class="form-control" id="task-batch-name" required> <!-- 修改名称输入框 -->
                                </div>
                                <div class="form-group">
                                    <label for="task-batch-description">批次描述</label>
                                    <textarea class="form-control" id="task-batch-description" rows="3"></textarea> <!-- 修改描述输入框 -->
                                </div>
                                <hr>
                                <div class="form-group">
                                    <label>每人单次最多可认领任务数：</label>
                                    <input type="number" id="task-batch-modal-claim-limit" min="1" class="form-control" placeholder="例如: 20（默认 10）">
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.taskManager.saveBatchInfo()">保存</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Allocate Users Modal (batch detail) -->
            <div class="modal fade" id="task-alloc-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title">分配用户</h4>
                        </div>
                        <div class="modal-body">
                            <div id="task-alloc-add-panel" style="display:none; border:1px solid #5cb85c; padding:8px; border-radius:4px; background:#f9fff9;">
                                <div id="task-alloc-add-list" style="max-height:300px; overflow-y:auto;"></div>
                                <div style="margin-top:6px; text-align:right;">
                                    <button type="button" class="btn btn-xs btn-success" onclick="window.app.taskManager.confirmTaskAllocAdd()">确定添加</button>
                                </div>
                            </div>
                            <div id="task-alloc-delete-panel" style="display:none; border:1px solid #d9534f; padding:8px; border-radius:4px; background:#fff9f9;">
                                <div id="task-alloc-delete-list" style="max-height:300px; overflow-y:auto;"></div>
                                <div style="margin-top:6px; text-align:right;">
                                    <button type="button" class="btn btn-xs btn-danger" style="margin-right:4px;" onclick="window.app.taskManager.deleteAllTaskAllocUsers()">全部删除</button>
                                    <button type="button" class="btn btn-xs btn-danger" onclick="window.app.taskManager.confirmTaskAllocDelete()">确定删除</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Claim Task Modal -->
            <div class="modal fade" id="claim-task-modal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title" id="claim-task-modal-title">领取任务（最多可领取 0 个）</h4>
                        </div>
                        <div class="modal-body">
                            <div id="claim-tasks-list" style="max-height: 400px; overflow-y: auto; border: 1px solid #ddd; padding: 10px;">
                                <!-- 动态加载未认领任务 -->
                            </div>
                            <div style="margin-top: 10px; color: #666;">
                                已选择 <span id="claim-selected-count">0</span> 个任务（最多可领取 <span id="claim-max-available">0</span> 个）
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.taskManager.confirmClaimTasks()">确认领取</button>
                        </div>
                    </div>
                </div>
            </div>            
        `;
        this.bindSortEvents();
        this.updateSortIndicators();
    }

    async loadTasks() {
        try {
            const params = { page: this.currentPage, page_size: this.pageSize };
            if (this.statusFilter) params.status = this.statusFilter;
            if (this.searchKeyword) params.keyword = this.searchKeyword;
            if (this.sortBy) params.sort_by = this.sortBy;
            if (this.sortOrder) params.sort_order = this.sortOrder;
            if (this.batchMode && this.currentBatchId) params.batch_id = this.currentBatchId;
            if (this.userFilter) params.assigned_user = this.userFilter;
            if (this.dateFrom) params.date_from = this.dateFrom;
            if (this.dateTo) params.date_to = this.dateTo;

            const data = await api.getTaskList(this.token, params);
            this.tasks = data.tasks || [];
            this.totalPages = Math.ceil(data.total / this.pageSize);
            this.selectedTaskIds.clear();
            this.renderTasksTable();
            this.renderPagination();
            this.updateBatchButtons();
            this.updateSortIndicators();
        } catch (error) {
            alert('加载任务列表失败: ' + error.message);
        }
    }

    renderTasksTable() {
        const tbody = document.getElementById('tasks-table-body');
        const statusLabels = {
            'pending': '<span class="label label-warning">待执行</span>',
            'in_progress': '<span class="label label-info">进行中</span>',
            'completed': '<span class="label label-success">已完成</span>'
        };

        tbody.innerHTML = this.tasks.map(task => `
            <tr>
                <td><input type="checkbox" class="task-checkbox" value="${task.id}" onchange="window.app.taskManager.toggleTaskSelection(${task.id}, this.checked)" ${this.selectedTaskIds.has(task.id) ? 'checked' : ''}></td>
                <td>${task.id}</td>
                <td title="${task.description}">${task.description.length > 50 ? task.description.substring(0, 50) + '...' : task.description}</td>
                <td>${statusLabels[task.status] || task.status}</td>
                <td>${task.assigned_users.map(u => u.username).join(', ') || '-'}</td>
                <td>${task.recording_count}</td>
                <td>${new Date(task.created_at).toLocaleString()}</td>
                <td>
                    <button class="btn btn-xs btn-info" onclick="window.app.taskManager.showEditTaskModal(${task.id})">
                        <span class="glyphicon glyphicon-edit"></span>
                    </button>
                    <button class="btn btn-xs btn-primary" onclick="window.app.taskManager.showAssignModal(${task.id})">
                        <span class="glyphicon glyphicon-user"></span>
                    </button>
                    <button class="btn btn-xs btn-danger" onclick="window.app.taskManager.deleteTask(${task.id})">
                        <span class="glyphicon glyphicon-trash"></span>
                    </button>
                </td>
            </tr>
        `).join('');

        // Update select-all checkbox state
        const selectAllCheckbox = document.getElementById('select-all-tasks');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = this.tasks.length > 0 && this.tasks.every(t => this.selectedTaskIds.has(t.id));
        }
    }

    toggleTaskSelection(taskId, checked) {
        if (checked) {
            this.selectedTaskIds.add(taskId);
        } else {
            this.selectedTaskIds.delete(taskId);
        }
        this.updateBatchButtons();
    }

    toggleSelectAll(checked) {
        this.tasks.forEach(task => {
            if (checked) {
                this.selectedTaskIds.add(task.id);
            } else {
                this.selectedTaskIds.delete(task.id);
            }
        });
        this.renderTasksTable();
        this.updateBatchButtons();
    }

    getCheckedTaskIdsFromDOM() {
        const checkboxes = document.querySelectorAll('#tasks-table-body .task-checkbox:checked');
        const ids = Array.from(checkboxes).map(cb => parseInt(cb.value));

        const newSet = new Set(ids);
        if (newSet.size !== this.selectedTaskIds.size || ids.some(id => !this.selectedTaskIds.has(id))) {
            this.selectedTaskIds = newSet;
            this.updateBatchButtons();
        }

        return ids;
    }

    updateBatchButtons() {
        const count = this.selectedTaskIds.size;
        const batchAssignBtn = document.getElementById('batch-assign-btn');
        const batchDeleteBtn = document.getElementById('batch-delete-btn');
        const batchMoveBtn = document.getElementById('batch-move-btn');
        const selectedCount = document.getElementById('selected-count');

        if (batchAssignBtn) batchAssignBtn.disabled = count === 0;
        if (batchDeleteBtn) batchDeleteBtn.disabled = count === 0;
        if (batchMoveBtn) batchMoveBtn.disabled = count === 0;
        if (selectedCount) selectedCount.textContent = count > 0 ? `已选择 ${count} 项` : '';
    }

    buildPageList(totalPages, currentPage) {
        const pages = [];
        const maxButtons = 5;
        let start = Math.max(1, currentPage - 2);
        let end = Math.min(totalPages, start + maxButtons - 1);
        if (end - start < maxButtons - 1) start = Math.max(1, end - maxButtons + 1);

        if (start > 1) {
            pages.push(1);
            if (start > 2) pages.push('...');
        }
        for (let p = start; p <= end; p++) {
            pages.push(p);
        }
        if (end < totalPages) {
            if (end < totalPages - 1) pages.push('...');
            pages.push(totalPages);
        }
        return pages;
    }

    renderPagination() {
        const container = document.getElementById('tasks-pagination');
        if (this.totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        // 构建智能页码列表
        const pages = this.buildPageList(this.totalPages, this.currentPage);

        let html = '<ul class="pagination" style="margin: 0;">';
        html += `<li class="${this.currentPage === 1 ? 'disabled' : ''}"><a href="#" onclick="window.app.taskManager.goToPage(${this.currentPage - 1}); return false;">&laquo;</a></li>`;

        for (const p of pages) {
            if (p === '...') {
                html += `<li class="disabled"><a href="#">...</a></li>`;
            } else {
                html += `<li class="${this.currentPage === p ? 'active' : ''}"><a href="#" onclick="window.app.taskManager.goToPage(${p}); return false;">${p}</a></li>`;
            }
        }

        html += `<li class="${this.currentPage === this.totalPages ? 'disabled' : ''}"><a href="#" onclick="window.app.taskManager.goToPage(${this.currentPage + 1}); return false;">&raquo;</a></li>`;
        html += '</ul>';

        // 页面跳转控件
        html += `<div style="display: inline-flex; align-items: center; margin-left: 12px; gap: 4px;">
            <span class="text-muted" style="white-space: nowrap;">共 ${this.totalPages} 页，跳转到</span>
            <input type="number" id="task-page-jump-input" class="form-control input-sm" style="width: 60px; display: inline-block;"
                min="1" max="${this.totalPages}" placeholder="页码"
                onkeydown="if(event.key==='Enter') window.app.taskManager.jumpToPage()">
            <button class="btn btn-sm btn-default" onclick="window.app.taskManager.jumpToPage()">跳转</button>
        </div>`;

        container.innerHTML = `<div style="display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 4px;">${html}</div>`;
    }

    jumpToPage() {
        const input = document.getElementById('task-page-jump-input');
        if (!input) return;
        const page = parseInt(input.value, 10);
        if (isNaN(page) || page < 1 || page > this.totalPages) {
            alert(`请输入 1 到 ${this.totalPages} 之间的页码`);
            return;
        }
        input.value = '';
        this.goToPage(page);
    }

    goToPage(page) {
        if (page < 1 || page > this.totalPages) return;
        this.currentPage = page;
        this.loadTasks();
    }

    toggleFilterPanel() {
        const panel = document.getElementById('task-filter-panel');
        if (!panel) return;
        const isVisible = panel.style.display !== 'none';
        if (isVisible) {
            panel.style.display = 'none';
            return;
        }
        panel.style.display = 'block';

        // 应用缓存的筛选值到DOM
        this.applyFiltersToDom({
            statusFilter: this.statusFilter,
            userFilter: this.userFilter,
            dateFrom: this.dateFrom,
            dateTo: this.dateTo
        });

        // 管理员首次打开时加载用户列表
        if (this.currentUser && this.currentUser.is_superuser && !this.filterUsers) {
            this.loadFilterUsers();
        }
        // 管理员显示用户筛选
        const userGroup = document.getElementById('task-filter-user-group');
        if (userGroup) {
            userGroup.style.display = (this.currentUser && this.currentUser.is_superuser) ? 'block' : 'none';
        }
        // 点击外部关闭
        setTimeout(() => {
            const closeHandler = (e) => {
                if (!panel.contains(e.target) && e.target.id !== 'task-filter-btn' && !e.target.closest('#task-filter-btn')) {
                    panel.style.display = 'none';
                    document.removeEventListener('click', closeHandler);
                }
            };
            document.addEventListener('click', closeHandler);
        }, 0);
    }

    async loadFilterUsers() {
        try {
            this.filterUsers = await api.getUsers(this.token);
            const select = document.getElementById('task-filter-user');
            if (!select) return;
            select.innerHTML = '<option value="">全部</option>' +
                this.filterUsers.map(u => `<option value="${u.id}">${this.escapeHtml(u.username)}</option>`).join('');
            // 加载完成后应用缓存的用户筛选值
            if (this.userFilter) {
                select.value = this.userFilter;
            }
        } catch (e) {
            this.filterUsers = [];
        }
    }

    getBatchFilterCacheKey() {
        if (!this.batchMode || !this.currentBatchId) return null;
        const token = localStorage.getItem('auth_token');
        if (token) {
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                const userId = payload.sub || payload.user_id || '';
                return `batch-${this.currentBatchId}-filters-user-${userId}`;
            } catch (e) {
                return `batch-${this.currentBatchId}-filters`;
            }
        }
        return `batch-${this.currentBatchId}-filters`;
    }

    loadBatchFilters() {
        try {
            const key = this.getBatchFilterCacheKey();
            if (!key) return null;
            const cached = sessionStorage.getItem(key);
            return cached ? JSON.parse(cached) : null;
        } catch (e) {
            return null;
        }
    }

    saveBatchFilters() {
        try {
            const key = this.getBatchFilterCacheKey();
            if (!key) return;
            const filters = {
                statusFilter: this.statusFilter,
                userFilter: this.userFilter,
                dateFrom: this.dateFrom,
                dateTo: this.dateTo
            };
            sessionStorage.setItem(key, JSON.stringify(filters));
        } catch (e) {}
    }

    applyFiltersToDom(filters) {
        if (!filters) return;
        const statusEl = document.getElementById('task-filter-status');
        const userEl = document.getElementById('task-filter-user');
        const dateFromEl = document.getElementById('task-filter-date-from');
        const dateToEl = document.getElementById('task-filter-date-to');
        if (statusEl) statusEl.value = filters.statusFilter || '';
        if (userEl) userEl.value = filters.userFilter || '';
        if (dateFromEl) dateFromEl.value = filters.dateFrom || '';
        if (dateToEl) dateToEl.value = filters.dateTo || '';
    }

    applyFilters() {
        const statusEl = document.getElementById('task-filter-status');
        const userEl = document.getElementById('task-filter-user');
        const dateFromEl = document.getElementById('task-filter-date-from');
        const dateToEl = document.getElementById('task-filter-date-to');
        this.statusFilter = statusEl ? statusEl.value : '';
        this.userFilter = userEl ? userEl.value : '';
        this.dateFrom = dateFromEl ? dateFromEl.value : '';
        this.dateTo = dateToEl ? dateToEl.value : '';
        this.currentPage = 1;
        this.saveBatchFilters();
        this.updateFilterBadge();
        document.getElementById('task-filter-panel').style.display = 'none';
        this.loadTasks();
    }

    clearFilters() {
        this.statusFilter = '';
        this.userFilter = '';
        this.dateFrom = '';
        this.dateTo = '';
        const els = ['task-filter-status','task-filter-user','task-filter-date-from','task-filter-date-to'];
        els.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
        this.currentPage = 1;
        try {
            const key = this.getBatchFilterCacheKey();
            if (key) sessionStorage.removeItem(key);
        } catch (e) {}
        this.updateFilterBadge();
        document.getElementById('task-filter-panel').style.display = 'none';
        this.loadTasks();
    }

    updateFilterBadge() {
        const count = [this.statusFilter, this.userFilter, this.dateFrom, this.dateTo].filter(v => v).length;
        const badge = document.getElementById('task-filter-badge');
        if (badge) {
            badge.style.display = count > 0 ? 'inline' : 'none';
            badge.textContent = count;
        }
    }

    escapeHtml(str) {
        if (str === undefined || str === null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    handleSearch() {
        const input = document.getElementById('task-search-input');
        this.searchKeyword = input ? input.value.trim() : '';
        this.currentPage = 1;
        this.loadTasks();
    }

    bindSortEvents() {
        const table = document.getElementById('tasks-table');
        if (!table) return;

        if (!this.sortHeaderListener) {
            this.sortHeaderListener = (event) => {
                let target = event.target;
                let header = null;

                if (target && typeof target.closest === 'function') {
                    header = target.closest('th[data-sort-field]');
                }

                if (!header) {
                    while (target) {
                        const matcher = target.matches || target.msMatchesSelector || target.webkitMatchesSelector;
                        if (matcher && matcher.call(target, 'th[data-sort-field]')) {
                            header = target;
                            break;
                        }
                        target = target.parentElement;
                    }
                }

                if (!header) return;
                const field = header.getAttribute('data-sort-field');
                this.onSortHeaderClick(field);
            };
        }

        table.addEventListener('click', this.sortHeaderListener);
    }

    updateSortIndicators() {
        const indicators = document.querySelectorAll('#tasks-table .sort-indicator');
        indicators.forEach(indicator => {
            const field = indicator.getAttribute('data-field');
            if (field === this.sortBy) {
                indicator.textContent = this.sortOrder === 'asc' ? '▲' : '▼';
            } else {
                indicator.textContent = '';
            }
        });
    }

    onSortHeaderClick(field) {
        if (!field) return;
        if (this.sortBy === field) {
            this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
        } else {
            const defaultOrderMap = {
                id: 'desc',
                description: 'asc',
                status: 'asc',
                assigned_count: 'desc',
                recording_count: 'desc',
                created_at: 'desc'
            };
            this.sortBy = field;
            this.sortOrder = defaultOrderMap[field] || 'desc';
        }
        this.currentPage = 1;
        this.updateSortIndicators();
        this.loadTasks();
    }

    showCreateTaskModal() {
        document.getElementById('task-modal-title').textContent = '创建任务';
        document.getElementById('task-id').value = '';
        document.getElementById('task-description').value = '';
        document.getElementById('task-status-group').style.display = 'none';
        $('#task-modal').modal('show');
    }

    showEditTaskModal(taskId) {
        const task = this.tasks.find(t => t.id === taskId);
        if (!task) return;

        document.getElementById('task-modal-title').textContent = '编辑任务';
        document.getElementById('task-id').value = task.id;
        document.getElementById('task-description').value = task.description;
        document.getElementById('task-status').value = task.status;
        document.getElementById('task-status-group').style.display = 'block';
        $('#task-modal').modal('show');
    }

    async saveTask() {
        const taskId = document.getElementById('task-id').value;
        const description = document.getElementById('task-description').value;

        try {
            if (taskId) {
                const status = document.getElementById('task-status').value;
                await api.updateTask(this.token, taskId, { description, status });
            } else {
                const taskData = { description };
                if (this.batchMode && this.currentBatchId) {
                    taskData.batch_id = this.currentBatchId;
                }
                await api.createTask(this.token, taskData); 
            }
            $('#task-modal').modal('hide');
            await this.loadTasks();
        } catch (error) {
            alert('保存任务失败: ' + error.message);
        }
    }

    async deleteTask(taskId) {
        if (!confirm('确定要删除这个任务吗？')) return;

        try {
            await api.deleteTask(this.token, taskId);
            await this.loadTasks();
        } catch (error) {
            alert('删除任务失败: ' + error.message);
        }
    }

    // Batch Upload
    showBatchUploadModal() {
        this.batchTasks = [];
        document.getElementById('batch-file').value = '';
        document.getElementById('batch-preview').innerHTML = '';
        document.getElementById('batch-count').textContent = '';
        $('#batch-upload-modal').modal('show');
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            this.batchTasks = e.target.result.split('\n').map(line => line.trim()).filter(line => line.length > 0);
            this.renderBatchPreview();
        };
        reader.readAsText(file);
    }

    renderBatchPreview() {
        const preview = document.getElementById('batch-preview');
        const tasks = this.batchTasks.slice(0, 10);
        preview.innerHTML = tasks.map((t, i) => `<div>${i + 1}. ${t}</div>`).join('');
        if (this.batchTasks.length > 10) {
            preview.innerHTML += `<div>... 还有 ${this.batchTasks.length - 10} 条</div>`;
        }
        document.getElementById('batch-count').textContent = `共 ${this.batchTasks.length} 条任务`;
    }

    async uploadBatch() {
        if (!this.batchTasks || this.batchTasks.length === 0) {
            alert('请先选择文件');
            return;
        }

        try {
            const uploadData = { tasks: this.batchTasks };
            if (this.batchMode && this.currentBatchId) {
                uploadData.batch_id = this.currentBatchId;
            }
            const result = await api.bulkUploadTasks(this.token, uploadData);
            alert(`上传完成！成功: ${result.success}, 失败: ${result.failed}`);
            $('#batch-upload-modal').modal('hide');
            await this.loadTasks();
        } catch (error) {
            alert('批量上传失败: ' + error.message);
        }
    }

    // Assignment
    async showAssignModal(taskId) {
        const task = this.tasks.find(t => t.id === taskId);
        if (!task) return;

        document.getElementById('assign-task-id').value = taskId;
        document.getElementById('assign-task-desc').textContent = task.description;

        try {
            this.users = await api.getUsers(this.token);
            const assignedIds = task.assigned_users.map(u => u.id);

            const html = this.users.map(user => `
                <div class="checkbox">
                    <label>
                        <input type="checkbox" class="assign-user-checkbox" value="${user.id}" ${assignedIds.includes(user.id) ? 'checked' : ''}>
                        ${user.username} ${assignedIds.includes(user.id) ? '(已分配)' : ''}
                    </label>
                </div>
            `).join('');

            document.getElementById('assign-users-list').innerHTML = html;
            $('#assign-modal').modal('show');
        } catch (error) {
            alert('加载用户列表失败: ' + error.message);
        }
    }

    async saveAssignment() {
        const taskId = document.getElementById('assign-task-id').value;
        const checkboxes = document.querySelectorAll('.assign-user-checkbox:checked');
        const userIds = Array.from(checkboxes).map(cb => parseInt(cb.value));

        try {
            await api.assignTask(this.token, taskId, userIds);
            $('#assign-modal').modal('hide');
            await this.loadTasks();
        } catch (error) {
            alert('分配任务失败: ' + error.message);
        }
    }

    // Batch Operations
    async batchDelete() {
        const taskIds = this.getCheckedTaskIdsFromDOM();
        const count = taskIds.length;
        if (count === 0) return;

        if (!confirm(`确定要删除选中的 ${count} 个任务吗？`)) return;

        try {
            const result = await api.batchDeleteTasks(this.token, taskIds);
            alert(`删除完成！成功: ${result.success}, 失败: ${result.failed}${result.errors.length > 0 ? '\n' + result.errors.join('\n') : ''}`);
            await this.loadTasks();
        } catch (error) {
            alert('批量删除失败: ' + error.message);
        }
    }

    async showBatchAssignModal() {
        const taskIds = this.getCheckedTaskIdsFromDOM();
        const count = taskIds.length;
        if (count === 0) {
            alert('请选择当前页的任务后再进行批量分配');
            return;
        }

        document.getElementById('batch-assign-info').textContent = `将为选中的 ${count} 个任务分配用户`;

        try {
            this.users = await api.getUsers(this.token);
            const html = this.users.map(user => `
                <div class="checkbox">
                    <label>
                        <input type="checkbox" class="batch-assign-user-checkbox" value="${user.id}">
                        ${user.username}
                    </label>
                </div>
            `).join('');

            document.getElementById('batch-assign-users-list').innerHTML = html;
            $('#batch-assign-modal').modal('show');
        } catch (error) {
            alert('加载用户列表失败: ' + error.message);
        }
    }

    async saveBatchAssignment() {
        const checkboxes = document.querySelectorAll('.batch-assign-user-checkbox:checked');
        const userIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
        const taskIds = this.getCheckedTaskIdsFromDOM();

        if (taskIds.length === 0) {
            alert('当前无可分配的任务，请重新选择');
            $('#batch-assign-modal').modal('hide');
            return;
        }

        // 空列表表示取消所有分配
        if (userIds.length === 0) {
            if (!confirm('未选择任何用户，将取消选中任务的所有分配。确定继续？')) {
                return;
            }
        }

        try {
            const result = await api.batchAssignTasks(this.token, taskIds, userIds);
            alert(`分配完成！成功: ${result.success}, 失败: ${result.failed}${result.errors.length > 0 ? '\n' + result.errors.join('\n') : ''}`);
            $('#batch-assign-modal').modal('hide');
            await this.loadTasks();
        } catch (error) {
            alert('批量分配失败: ' + error.message);
        }
    }

    show() {
        this.isVisible = true;
        this.token = localStorage.getItem('auth_token');
        this.currentUser = null; // 清除缓存，确保重新获取用户信息
        this.container.style.display = 'block';

        // 如果不在批次模式，默认显示批次管理视图
        if (!this.batchMode && window.app.batchManager) {
            this.container.style.display = 'none';
            window.app.batchManager.show();
        } else if (!this.batchMode && this.token) {
            // 如果批次管理器未初始化且不在批次模式，显示原任务列表
            this.loadTasks();
        } else if (this.batchMode && this.token) {
            // 批次模式下也刷新数据，确保切换账号后显示正确的任务
            this.loadBatchInfo();
            this.loadAllocationStats();
            this.loadTasks();
        }
    }

    async showBatchDetail(batchId) {
        // 重置搜索状态
        this.searchKeyword = '';
        this.currentPage = 1;
        const searchInput = document.getElementById('task-search-input');
        if (searchInput) searchInput.value = '';

        this.token = localStorage.getItem('auth_token');

        // 加载当前用户信息
        if (!this.currentUser) {
            try {
                this.currentUser = await api.getCurrentUser(this.token);
            } catch (e) { /* ignore */ }
        }

        this.batchMode = true;
        this.currentBatchId = batchId;

        // 加载该批次的缓存筛选条件
        const cachedFilters = this.loadBatchFilters();
        if (cachedFilters) {
            this.statusFilter = cachedFilters.statusFilter || '';
            this.userFilter = cachedFilters.userFilter || '';
            this.dateFrom = cachedFilters.dateFrom || '';
            this.dateTo = cachedFilters.dateTo || '';
        } else {
            this.statusFilter = '';
            this.userFilter = '';
            this.dateFrom = '';
            this.dateTo = '';
        }
        this.filterUsers = null;
        this.updateFilterBadge();

        document.getElementById('batch-info-section').style.display = 'block';
        document.getElementById('batch-breadcrumb').style.display = 'flex';
        document.getElementById('task-manager-title').style.display = 'none';
        document.getElementById('batch-move-btn').style.display = 'inline-block';
        await this.loadBatchInfo();
        await this.loadAllocationStats();
        await this.loadTasks();
    }

    exitBatchMode() {
        this.batchMode = false;
        this.currentBatchId = null;
        this.currentBatch = null;
        this.statusFilter = '';
        this.userFilter = '';
        this.dateFrom = '';
        this.dateTo = '';
        this.filterUsers = null;
        document.getElementById('batch-info-section').style.display = 'none';
        document.getElementById('batch-breadcrumb').style.display = 'none';
        document.getElementById('task-manager-title').style.display = 'block';
        document.getElementById('batch-move-btn').style.display = 'none';
        this.hide();
        window.app.batchManager.show();
    }

    async loadBatchInfo() {
        if (!this.currentBatchId) return;
        if (!this.currentUser) {
            try {
                this.currentUser = await api.getCurrentUser(this.token);
            } catch (e) { /* ignore */ }
        }
        try {
            this.currentBatch = await api.getBatch(this.token, this.currentBatchId);
        } catch (e) {
            return;
        }
        const description = this.currentBatch.description || '无描述';
        document.getElementById('batch-title-display').textContent = `批次：${this.currentBatch.name}`;
        document.getElementById('batch-desc-display').textContent = `批次描述：${description}`;
        document.getElementById('batch-name-breadcrumb').textContent = `批次：${this.currentBatch.name}`;
        document.getElementById('batch-stat-total').textContent = this.currentBatch.statistics.total;
        document.getElementById('batch-stat-pending').textContent = this.currentBatch.statistics.pending;
        document.getElementById('batch-stat-in-progress').textContent = this.currentBatch.statistics.in_progress;
        document.getElementById('batch-stat-completed').textContent = this.currentBatch.statistics.completed;
        const usernames = this.currentBatch.statistics.assigned_usernames;
        document.getElementById('batch-stat-users').textContent = usernames && usernames.length > 0 ? usernames.join(', ') : '无';
        const allocNames = this.currentBatch.statistics.allocated_usernames;
        document.getElementById('batch-stat-allocated').textContent = allocNames && allocNames.length > 0 ? allocNames.join(', ') : '无';

        // 根据用户权限显示/隐藏管理员按钮
        const adminButtonsSection = document.getElementById('admin-buttons-section');
        if (adminButtonsSection && this.currentUser && this.currentUser.is_superuser) {
            adminButtonsSection.style.display = 'block';
        } else if (adminButtonsSection) {
            adminButtonsSection.style.display = 'none';
        }
    }

    async saveBatchInfo() {
        const batchId = document.getElementById('task-batch-id').value;
        const name = document.getElementById('task-batch-name').value.trim();
        const description = document.getElementById('task-batch-description').value.trim();
        const claimLimitInput = parseInt(document.getElementById('task-batch-modal-claim-limit').value, 10);
        const claimLimitPerUser = Number.isInteger(claimLimitInput) && claimLimitInput > 0 ? claimLimitInput : 10;

        if (!name) {
            alert('批次名称不能为空');
            return;
        }
        if (!batchId) {
            alert('批次ID不存在，请刷新页面重试');
            return;
        }

        try {
            await api.updateBatch(this.token, batchId, {
                name: name,
                description: description,
                claim_limit_per_user: claimLimitPerUser
            });
            $('#task-batch-modal').modal('hide');
            alert('批次信息已更新');
            await this.loadBatchInfo();
            await this.loadAllocationStats();
            await this.loadTasks();
        } catch (error) {
            alert(`更新失败: ${error.message}`);
        }
    }

    async deleteBatch() {
        if (!confirm('确定要删除此批次吗？批次内的所有任务也将被删除，此操作不可恢复！')) return;
        try {
            await api.deleteBatch(this.token, this.currentBatchId);
            alert('批次已删除');
            this.exitBatchMode();
        } catch (error) {
            alert('删除失败');
        }
    }

    editBatchInfo() {
        document.getElementById('task-batch-id').value = this.currentBatchId;
        document.getElementById('task-batch-name').value = this.currentBatch.name;
        document.getElementById('task-batch-description').value = this.currentBatch.description || '';
        document.getElementById('task-batch-modal-claim-limit').value = this.currentBatch?.claim_limit_per_user != null
            ? this.currentBatch.claim_limit_per_user
            : 10;
        $('#task-batch-modal').modal('show');
    }

    async showBatchMoveModal() {
        // 1. 获取当前选中的任务 ID
        const taskIds = this.getCheckedTaskIdsFromDOM();
        const count = taskIds.length;
        if (count === 0) {
            alert('请选择当前页的任务后再进行批量移动');
            return;
        }

        // 2. 显示提示信息
        document.getElementById('batch-move-info').textContent = 
            `将把选中的 ${count} 个任务移动到其他批次`;

        try {
            // 3. 调用 API 获取批次列表（修正：解析返回的对象）
            const batchData = await api.getBatches(this.token);
            const batches = batchData.batches || [];
            
            // 4. 渲染批次下拉选项（排除当前批次）
            const select = document.getElementById('target-batch-select');
            select.innerHTML = batches
                .filter(b => b.id !== this.currentBatchId) // 排除当前批次
                .map(b => `<option value="${b.id}">${b.name}</option>`)
                .join('');

            // 5. 显示模态框
            $('#batch-move-modal').modal('show');
        } catch (error) {
            alert('加载批次列表失败: ' + error.message);
        }
    }

    async saveBatchMove() {
        // 1. 获取选中的任务 ID 和目标批次 ID
        const taskIds = this.getCheckedTaskIdsFromDOM();
        const targetBatchId = parseInt(document.getElementById('target-batch-select').value);
        const count = taskIds.length;

        if (taskIds.length === 0) {
            alert('当前无可移动的任务，请重新选择');
            $('#batch-move-modal').modal('hide');
            return;
        }
        if (!targetBatchId) {
            alert('请选择目标批次');
            return;
        }

        // 2. 二次确认
        if (!confirm(`确定要将选中的 ${count} 个任务移动到目标批次吗？`)) {
            return;
        }

        try {
            // 3. 调用后端批量移动接口
            const result = await api.batchMoveTasks(this.token, taskIds, targetBatchId);
            alert(`移动完成！成功: ${result.success}, 失败: ${result.failed}${result.errors.length > 0 ? '\n' + result.errors.join('\n') : ''}`);
            
            // 4. 关闭模态框并刷新数据
            $('#batch-move-modal').modal('hide');
            await this.loadTasks();
            await this.loadBatchInfo(); // 刷新批次统计信息
        } catch (error) {
            alert('批量移动任务失败: ' + error.message);
        }
    }

    // ========== Allocate Users Modal (batch detail) ==========

    async showTaskAllocModal(mode = 'add') {
        if (!this.currentBatchId) return;
        this._taskAlloc = { allUsers: [], assignedIds: new Set(), addPage: 1, deletePage: 1 };
        document.getElementById('task-alloc-add-panel').style.display = 'none';
        document.getElementById('task-alloc-delete-panel').style.display = 'none';
        document.querySelector('#task-alloc-modal .modal-title').textContent =
            mode === 'delete' ? '删除用户' : '添加用户';
        $('#task-alloc-modal').modal('show');

        try {
            const [usersData, allocData] = await Promise.all([
                api.getUsers(this.token),
                api.getBatchAllocations(this.token, this.currentBatchId)
            ]);
            this._taskAlloc.allUsers = usersData;
            if (allocData && allocData.allocations) {
                for (const a of allocData.allocations) {
                    this._taskAlloc.assignedIds.add(a.user_id);
                }
            }
        } catch (error) {
            console.error('Failed to load users:', error);
        }
        if (mode === 'delete') {
            this.showTaskAllocDeletePanel();
        } else {
            this.showTaskAllocAddPanel();
        }
    }

    showTaskAllocAddPanel() {
        document.getElementById('task-alloc-delete-panel').style.display = 'none';
        this._taskAlloc.addPage = 1;
        this._taskAllocRenderAddPage();
        document.getElementById('task-alloc-add-panel').style.display = 'block';
    }

    _taskAllocRenderAddPage() {
        const PAGE_SIZE = 10;
        const unassigned = this._taskAlloc.allUsers.filter(u => !this._taskAlloc.assignedIds.has(u.id));
        const el = document.getElementById('task-alloc-add-list');
        if (!unassigned.length) {
            el.innerHTML = '<span class="text-muted">所有用户已分配</span>';
            return;
        }
        const totalPages = Math.ceil(unassigned.length / PAGE_SIZE);
        if (this._taskAlloc.addPage > totalPages) this._taskAlloc.addPage = totalPages;
        const page = this._taskAlloc.addPage;
        const start = (page - 1) * PAGE_SIZE;
        const pageUsers = unassigned.slice(start, start + PAGE_SIZE);

        let html = `<table class="table table-condensed table-bordered" style="margin-bottom:4px; font-size:12px;">
            <thead><tr>
                <th style="width:28px;"><input type="checkbox" onclick="window.app.taskManager.selectAllTaskAllocAdd(this)"></th>
                <th style="width:36px;">ID</th>
                <th>用户名</th>
                <th>邮箱</th>
                <th>全名</th>
            </tr></thead><tbody>`;
        for (const u of pageUsers) {
            html += `<tr>
                <td><input type="checkbox" value="${u.id}"></td>
                <td>${u.id}</td>
                <td>${this.escapeHtml(u.username)}</td>
                <td>${this.escapeHtml(u.email || '')}</td>
                <td>${this.escapeHtml(u.full_name || '')}</td>
            </tr>`;
        }
        html += `</tbody></table>`;
        html += `<div style="display:flex; align-items:center; justify-content:space-between; margin-top:4px;">
            <span style="font-size:12px; color:#666;">第 ${page}/${totalPages} 页，共 ${unassigned.length} 人</span>
            <div>
                <button class="btn btn-xs btn-default" ${page <= 1 ? 'disabled' : ''} onclick="window.app.taskManager.taskAllocAddPrev()">«</button>
                <button class="btn btn-xs btn-default" ${page >= totalPages ? 'disabled' : ''} onclick="window.app.taskManager.taskAllocAddNext()">»</button>
            </div>
        </div>`;
        el.innerHTML = html;
    }

    taskAllocAddPrev() {
        if (this._taskAlloc.addPage > 1) { this._taskAlloc.addPage--; this._taskAllocRenderAddPage(); }
    }

    taskAllocAddNext() {
        this._taskAlloc.addPage++;
        this._taskAllocRenderAddPage();
    }

    selectAllTaskAllocAdd(cb) {
        const checked = cb ? cb.checked : true;
        document.querySelectorAll('#task-alloc-add-list input[type=checkbox]').forEach(c => c.checked = checked);
    }

    hideTaskAllocAddPanel() {
        document.getElementById('task-alloc-add-panel').style.display = 'none';
    }

    async confirmTaskAllocAdd() {
        const checked = document.querySelectorAll('#task-alloc-add-list tbody input:checked');
        if (!checked.length) { alert('请选择要添加的用户'); return; }
        if (!confirm(`确定添加选中的 ${checked.length} 位用户吗？`)) return;
        checked.forEach(cb => this._taskAlloc.assignedIds.add(parseInt(cb.value)));
        await this.saveTaskAlloc();
    }

    showTaskAllocDeletePanel() {
        document.getElementById('task-alloc-add-panel').style.display = 'none';
        this._taskAlloc.deletePage = 1;
        this._taskAllocRenderDeletePage();
        document.getElementById('task-alloc-delete-panel').style.display = 'block';
    }

    _taskAllocRenderDeletePage() {
        const PAGE_SIZE = 10;
        const assigned = this._taskAlloc.allUsers.filter(u => this._taskAlloc.assignedIds.has(u.id));
        const el = document.getElementById('task-alloc-delete-list');
        if (!assigned.length) {
            el.innerHTML = '<span class="text-muted">暂无已分配用户</span>';
            return;
        }
        const totalPages = Math.ceil(assigned.length / PAGE_SIZE);
        if (this._taskAlloc.deletePage > totalPages) this._taskAlloc.deletePage = totalPages;
        const page = this._taskAlloc.deletePage;
        const start = (page - 1) * PAGE_SIZE;
        const pageUsers = assigned.slice(start, start + PAGE_SIZE);

        let html = `<table class="table table-condensed table-bordered" style="margin-bottom:4px; font-size:12px;">
            <thead><tr>
                <th style="width:28px;"><input type="checkbox" onclick="window.app.taskManager.selectAllTaskAllocDelete(this)"></th>
                <th style="width:36px;">ID</th>
                <th>用户名</th>
                <th>邮箱</th>
                <th>全名</th>
            </tr></thead><tbody>`;
        for (const u of pageUsers) {
            html += `<tr>
                <td><input type="checkbox" value="${u.id}"></td>
                <td>${u.id}</td>
                <td>${this.escapeHtml(u.username)}</td>
                <td>${this.escapeHtml(u.email || '')}</td>
                <td>${this.escapeHtml(u.full_name || '')}</td>
            </tr>`;
        }
        html += `</tbody></table>`;
        html += `<div style="display:flex; align-items:center; justify-content:space-between; margin-top:4px;">
            <span style="font-size:12px; color:#666;">第 ${page}/${totalPages} 页，共 ${assigned.length} 人</span>
            <div>
                <button class="btn btn-xs btn-default" ${page <= 1 ? 'disabled' : ''} onclick="window.app.taskManager.taskAllocDeletePrev()">«</button>
                <button class="btn btn-xs btn-default" ${page >= totalPages ? 'disabled' : ''} onclick="window.app.taskManager.taskAllocDeleteNext()">»</button>
            </div>
        </div>`;
        el.innerHTML = html;
    }

    taskAllocDeletePrev() {
        if (this._taskAlloc.deletePage > 1) { this._taskAlloc.deletePage--; this._taskAllocRenderDeletePage(); }
    }

    taskAllocDeleteNext() {
        this._taskAlloc.deletePage++;
        this._taskAllocRenderDeletePage();
    }

    selectAllTaskAllocDelete(cb) {
        const checked = cb ? cb.checked : true;
        document.querySelectorAll('#task-alloc-delete-list input[type=checkbox]').forEach(c => c.checked = checked);
    }

    hideTaskAllocDeletePanel() {
        document.getElementById('task-alloc-delete-panel').style.display = 'none';
    }

    async confirmTaskAllocDelete() {
        const checked = document.querySelectorAll('#task-alloc-delete-list tbody input:checked');
        if (!checked.length) { alert('请选择要删除的用户'); return; }
        if (!confirm(`确定删除选中的 ${checked.length} 位用户吗？`)) return;
        checked.forEach(cb => this._taskAlloc.assignedIds.delete(parseInt(cb.value)));
        await this.saveTaskAlloc();
    }

    async deleteAllTaskAllocUsers() {
        if (!confirm('确定删除所有已分配用户吗？')) return;
        this._taskAlloc.assignedIds.clear();
        await this.saveTaskAlloc();
    }

    async saveTaskAlloc() {
        const userIds = Array.from(this._taskAlloc.assignedIds);

        try {
            await api.saveBatchAllocations(this.token, this.currentBatchId, userIds);
            $('#task-alloc-modal').modal('hide');
            await this.loadBatchInfo();
            await this.loadAllocationStats();
            await this.loadTasks();
            alert('用户分配已保存');
        } catch (error) {
            console.error('Failed to save allocation:', error);
            alert('保存分配失败: ' + error.message);
        }
    }

    async loadAllocationStats() {
        if (!this.currentBatchId) return;

        try {
            this.allocationStats = await api.getMyBatchAllocation(this.token, this.currentBatchId);
            document.getElementById('batch-allocation-claim-limit').textContent = this.allocationStats.claim_limit_per_user;
            document.getElementById('batch-allocation-occupied').textContent = this.allocationStats.occupied;
            document.getElementById('batch-allocation-available').textContent = this.allocationStats.available;
            document.getElementById('allocation-claim-limit-display').style.display = 'inline';
        } catch (error) {
            this.allocationStats = null;
            document.getElementById('allocation-claim-limit-display').style.display = 'none';
        }
    }

    async refreshAfterClaim() {
        await this.loadAllocationStats();
        await this.loadTasks();
    }

    async showClaimTaskModal() {
        if (!this.currentBatchId) {
            alert('请先进入批次详情页');
            return;
        }
        if (!this.allocationStats || this.allocationStats.available <= 0) {
            alert('已达到领取限额，暂无可领取任务');
            return;
        }

        const available = this.allocationStats?.available || 0;
        try {
            const data = await api.getClaimableTasks(this.token, this.currentBatchId, available);
            this.claimableTasks = data.tasks || [];

            // 渲染任务列表（默认全选）
            const listHtml = this.claimableTasks.map(task => `
                <div class="checkbox">
                    <label>
                        <input type="checkbox" class="claim-task-checkbox" value="${task.id}" checked>
                        ${task.id} - ${task.description.length > 80 ? task.description.substring(0, 80) + '...' : task.description}
                    </label>
                </div>
            `).join('');
            document.getElementById('claim-tasks-list').innerHTML = listHtml || '<p style="text-align: center; color: #666;">暂无可领取的任务</p>';
            document.getElementById('claim-selected-count').textContent = this.claimableTasks.length;
            document.getElementById('claim-task-modal-title').textContent = `领取任务（最多可领取 ${available} 个）`;
            document.getElementById('claim-max-available').textContent = available;
            this.selectedClaimTaskIds.clear(); // 重置选择
            $('#claim-task-modal').modal('show');

            const self = this;
            document.querySelectorAll('.claim-task-checkbox').forEach(cb => {
                cb.addEventListener('change', () => {
                    const count = document.querySelectorAll('.claim-task-checkbox:checked').length;
                    document.getElementById('claim-selected-count').textContent = count;
                });
            });            
        } catch (error) {
            alert('加载可领取任务失败: ' + error.message);
        }
    }

    async confirmClaimTasks() {
        const checkboxes = document.querySelectorAll('.claim-task-checkbox:checked');
        const selectedTaskIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
        const maxAvailable = this.allocationStats.available;

        if (selectedTaskIds.length === 0) {
            alert('请至少选择一个任务');
            return;
        }
        if (selectedTaskIds.length > maxAvailable) {
            alert(`最多可领取 ${maxAvailable} 个任务，请调整选择`);
            return;
        }

        try {
            // 批量认领任务（调用后端接口）
            for (const taskId of selectedTaskIds) {
                await api.claimTask(this.token, this.currentBatchId, taskId);
            }
            alert(`成功领取 ${selectedTaskIds.length} 个任务`);
            $('#claim-task-modal').modal('hide');
            // 刷新数据
            await this.refreshAfterClaim();
        } catch (error) {
            alert('领取任务失败: ' + error.message);
        }
    }



    hide() {
        this.isVisible = false;
        this.container.style.display = 'none';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
