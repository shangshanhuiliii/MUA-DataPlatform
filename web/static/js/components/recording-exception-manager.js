/**
 * Recording Exception Manager Component
 * Admin-only page for repairing missing or invalid recording metadata.
 */
class RecordingExceptionManager {
    constructor(containerId) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.items = [];
        this.users = [];
        this.currentUser = null;
        this.isVisible = false;
        this.searchKeyword = '';
        this.exceptionType = '';
        this.taskPreview = null;
        this.init();
    }

    init() {
        this.render();
    }

    getToken() {
        return localStorage.getItem('auth_token');
    }

    render() {
        this.container.innerHTML = `
            <div class="recording-exception-manager">
                <div class="panel panel-default">
                    <div class="panel-heading">
                        <h4>录制异常管理</h4>
                    </div>
                    <div class="panel-body">
                        <div class="row" style="margin-bottom: 15px;">
                            <div class="col-sm-5">
                                <button class="btn btn-default" onclick="window.app.recordingExceptionManager.refresh()">
                                    <span class="glyphicon glyphicon-refresh"></span> 刷新
                                </button>
                                <span id="recording-exception-count" class="text-muted" style="margin-left: 10px;"></span>
                            </div>
                            <div class="col-sm-7 text-right">
                                <div class="input-group" style="display: inline-flex; width: 300px; vertical-align: middle; margin-right: 8px;">
                                    <input type="text" id="recording-exception-search" class="form-control"
                                           placeholder="搜索目录、任务、录制人或异常类型">
                                    <span class="input-group-btn">
                                        <button class="btn btn-default" onclick="window.app.recordingExceptionManager.applyFilters()">
                                            <span class="glyphicon glyphicon-search"></span>
                                        </button>
                                    </span>
                                </div>
                                <select id="recording-exception-type-filter" class="form-control" style="display: inline-block; width: 180px;">
                                    <option value="">全部异常</option>
                                    <option value="missing_db_record">目录存在但 DB 缺失</option>
                                    <option value="invalid_relationship">任务/录制人关系异常</option>
                                </select>
                            </div>
                        </div>

                        <table class="table table-striped table-hover">
                            <thead>
                                <tr>
                                    <th style="width: 24%;">录制目录</th>
                                    <th style="width: 16%;">异常类型</th>
                                    <th style="width: 18%;">当前 DB 记录</th>
                                    <th style="width: 24%;">推断任务信息</th>
                                    <th style="width: 10%;">task-info</th>
                                    <th style="width: 8%;">操作</th>
                                </tr>
                            </thead>
                            <tbody id="recording-exception-table-body"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="modal fade" id="recording-exception-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title">修复录制异常</h4>
                        </div>
                        <div class="modal-body">
                            <form id="recording-exception-form">
                                <div class="form-group">
                                    <label>录制目录</label>
                                    <input type="text" class="form-control" id="recording-exception-directory" readonly>
                                </div>
                                <div class="form-group">
                                    <label>异常说明</label>
                                    <div class="well well-sm" id="recording-exception-issues" style="margin-bottom: 0;"></div>
                                </div>
                                <div class="form-group">
                                    <label>任务 ID</label>
                                    <div class="input-group">
                                        <input type="number" min="1" class="form-control" id="recording-exception-task-id" placeholder="请输入任务 ID">
                                        <span class="input-group-btn">
                                            <button type="button" class="btn btn-default" onclick="window.app.recordingExceptionManager.loadTaskPreview()">
                                                读取任务
                                            </button>
                                        </span>
                                    </div>
                                    <div id="recording-exception-task-preview" class="help-block" style="margin-bottom: 0;"></div>
                                </div>
                                <div class="form-group">
                                    <label>实际录制人</label>
                                    <select class="form-control" id="recording-exception-recorded-by">
                                        <option value="">请选择录制人</option>
                                    </select>
                                </div>
                                <p class="text-muted" style="margin-bottom: 0;">
                                    保存时如果录制人当前未分配到该任务，系统会自动补一条任务分配关系，避免异常持续出现。
                                </p>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.recordingExceptionManager.saveRepair()">保存修复</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        var searchInput = document.getElementById('recording-exception-search');
        if (searchInput) {
            searchInput.addEventListener('keydown', function(event) {
                if (event.key === 'Enter') {
                    window.app.recordingExceptionManager.applyFilters();
                }
            });
        }

        var typeFilter = document.getElementById('recording-exception-type-filter');
        if (typeFilter) {
            typeFilter.addEventListener('change', function() {
                window.app.recordingExceptionManager.applyFilters();
            });
        }
    }

    showNoPermission(message) {
        this.container.innerHTML = `
            <div class="recording-exception-manager">
                <div class="panel panel-default">
                    <div class="panel-heading"><h4>录制异常管理</h4></div>
                    <div class="panel-body text-center" style="padding: 50px;">
                        <span class="glyphicon glyphicon-lock" style="font-size: 48px; color: #ccc;"></span>
                        <h4 style="margin-top: 20px; color: #999;">${message}</h4>
                    </div>
                </div>
            </div>
        `;
    }

    async show() {
        this.isVisible = true;
        this.container.style.display = 'block';

        var token = this.getToken();
        if (!token) {
            this.showNoPermission('请登录管理员账号管理录制异常');
            return;
        }

        try {
            this.currentUser = await api.getCurrentUser(token);
            if (!this.currentUser.is_superuser) {
                this.showNoPermission('当前账号无权限管理录制异常');
                return;
            }
            this.render();
            await Promise.all([this.loadUsers(), this.loadExceptions()]);
        } catch (error) {
            this.showNoPermission('请登录管理员账号管理录制异常');
        }
    }

    hide() {
        this.isVisible = false;
        this.container.style.display = 'none';
    }

    async loadUsers() {
        var token = this.getToken();
        this.users = await api.getUsers(token);
        this.users.sort(function(a, b) {
            return (a.username || '').localeCompare(b.username || '', 'zh-CN');
        });
    }

    async loadExceptions() {
        var token = this.getToken();
        var data = await api.getRecordingExceptions(token);
        this.items = (data && data.items) || [];
        this.renderTable();
        this.updateCount();
    }

    renderTable() {
        var tbody = document.getElementById('recording-exception-table-body');
        if (!tbody) return;

        if (!this.items.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center text-muted" style="padding: 30px;">当前没有待处理的录制异常</td>
                </tr>
            `;
            return;
        }

        var self = this;
        tbody.innerHTML = this.items.map(function(item) {
            var currentRecord = item.recording_id
                ? ('<div><strong>#' + item.recording_id + '</strong></div>'
                    + '<div class="text-muted">任务: ' + self.escapeHtml(self.formatTaskLabel(item.task_id, item.task_description)) + '</div>'
                    + '<div class="text-muted">录制人: ' + self.escapeHtml(item.recorded_by_username || ('#' + item.recorded_by)) + '</div>')
                : '<span class="text-muted">DB 中暂无记录</span>';

            var inferredTask = self.formatTaskLabel(
                item.inferred_task_id || item.task_info_task_id,
                item.inferred_task_description || item.task_info_description
            );
            var taskInfoStatus = item.task_info_exists
                ? ('<span class="label label-success">存在</span><div class="text-muted" style="margin-top: 6px;">'
                    + self.escapeHtml(item.task_info_description || '无描述') + '</div>')
                : '<span class="label label-default">缺失</span>';

            return `
                <tr>
                    <td>
                        <div><strong>${self.escapeHtml(item.directory_name)}</strong></div>
                        <div class="text-muted">${self.escapeHtml(item.record_url)}</div>
                    </td>
                    <td>
                        ${self.formatExceptionType(item.exception_type)}
                        <div style="margin-top: 6px;">${self.formatIssues(item.issues)}</div>
                    </td>
                    <td>${currentRecord}</td>
                    <td>${self.escapeHtml(inferredTask)}</td>
                    <td>${taskInfoStatus}</td>
                    <td>${self.buildRepairActionHtml(item)}</td>
                </tr>
            `;
        }).join('');

        this.bindRepairButtons();
    }

    updateCount() {
        var countNode = document.getElementById('recording-exception-count');
        if (countNode) {
            countNode.textContent = '共 ' + this.items.length + ' 条异常';
        }
    }

    applyFilters() {
        var searchInput = document.getElementById('recording-exception-search');
        var typeFilter = document.getElementById('recording-exception-type-filter');
        this.searchKeyword = searchInput ? searchInput.value.trim() : '';
        this.exceptionType = typeFilter ? typeFilter.value : '';
        this.refresh();
    }

    async refresh() {
        try {
            var token = this.getToken();
            var params = {};
            if (this.searchKeyword) params.keyword = this.searchKeyword;
            if (this.exceptionType) params.exception_type = this.exceptionType;
            var data = await api.getRecordingExceptions(token, params);
            this.items = (data && data.items) || [];
            this.renderTable();
            this.updateCount();
        } catch (error) {
            alert('加载录制异常失败: ' + error.message);
        }
    }

    formatExceptionType(type) {
        if (type === 'missing_db_record') {
            return '<span class="label label-warning">目录存在但 DB 缺失</span>';
        }
        return '<span class="label label-danger">任务/录制人关系异常</span>';
    }

    formatIssues(issues) {
        var self = this;
        return (issues || []).map(function(issue) {
            return '<span class="label label-default" style="margin-right: 4px;">' + self.escapeHtml(self.getIssueLabel(issue)) + '</span>';
        }).join('');
    }

    getIssueLabel(issue) {
        var labels = {
            db_missing: 'recordings 缺失',
            task_missing: '任务不存在',
            user_missing: '录制人不存在',
            user_not_assigned: '录制人未分配到任务'
        };
        return labels[issue] || issue;
    }

    formatTaskLabel(taskId, description) {
        if (!taskId && !description) return '未识别';
        if (!taskId) return description || '未识别';
        return '#' + taskId + (description ? (' ' + description) : '');
    }

    buildRepairActionHtml(item) {
        return '<button class="btn btn-xs btn-primary recording-exception-repair-btn" '
            + 'data-directory-name="' + this.escapeAttribute(item.directory_name) + '">修复</button>';
    }

    bindRepairButtons() {
        var buttons = this.container.querySelectorAll('.recording-exception-repair-btn');
        var self = this;
        buttons.forEach(function(button) {
            button.addEventListener('click', function(event) {
                self.handleRepairButtonClick(event);
            });
        });
    }

    handleRepairButtonClick(event) {
        var button = event.currentTarget;
        if (!button) return;

        var directoryName = button.getAttribute('data-directory-name');
        if (!directoryName) return;

        this.openRepairModal(directoryName);
    }

    populateUserOptions(selectedUserId) {
        var select = document.getElementById('recording-exception-recorded-by');
        if (!select) return;

        var options = ['<option value="">请选择录制人</option>'];
        this.users.forEach(function(user) {
            var selected = String(user.id) === String(selectedUserId || '') ? 'selected' : '';
            var suffix = user.is_superuser ? ' (管理员)' : '';
            var activeSuffix = user.is_active ? '' : ' [已禁用]';
            options.push('<option value="' + user.id + '" ' + selected + '>' + user.username + suffix + activeSuffix + '</option>');
        });
        select.innerHTML = options.join('');
    }

    openRepairModal(directoryName) {
        var item = this.items.find(function(entry) {
            return entry.directory_name === directoryName;
        });
        if (!item) {
            alert('未找到对应异常项，请刷新后重试');
            return;
        }

        document.getElementById('recording-exception-directory').value = item.directory_name;
        document.getElementById('recording-exception-issues').innerHTML = this.formatIssues(item.issues) || '<span class="text-muted">无</span>';

        var initialTaskId = item.task_id || item.inferred_task_id || item.task_info_task_id || '';
        document.getElementById('recording-exception-task-id').value = initialTaskId;
        this.populateUserOptions(item.recorded_by || '');

        this.taskPreview = {
            id: initialTaskId || null,
            description: item.task_description || item.inferred_task_description || item.task_info_description || ''
        };
        this.renderTaskPreview();
        $('#recording-exception-modal').modal('show');
    }

    renderTaskPreview(errorMessage) {
        var preview = document.getElementById('recording-exception-task-preview');
        if (!preview) return;

        if (errorMessage) {
            preview.innerHTML = '<span class="text-danger">' + this.escapeHtml(errorMessage) + '</span>';
            return;
        }

        if (!this.taskPreview || !this.taskPreview.id) {
            preview.innerHTML = '<span class="text-muted">请输入任务 ID 并点击“读取任务”校验</span>';
            return;
        }

        preview.innerHTML = '<span class="text-success">任务已确认：</span>' + this.escapeHtml(
            this.formatTaskLabel(this.taskPreview.id, this.taskPreview.description)
        );
    }

    async loadTaskPreview() {
        var taskIdValue = document.getElementById('recording-exception-task-id').value.trim();
        if (!taskIdValue) {
            this.taskPreview = null;
            this.renderTaskPreview('请先输入任务 ID');
            return;
        }

        try {
            var token = this.getToken();
            var task = await api.getTaskById(token, parseInt(taskIdValue, 10));
            this.taskPreview = { id: task.id, description: task.description || '' };
            this.renderTaskPreview();
        } catch (error) {
            this.taskPreview = null;
            this.renderTaskPreview('任务不存在或当前无法访问');
        }
    }

    async saveRepair() {
        var directoryName = document.getElementById('recording-exception-directory').value.trim();
        var taskId = parseInt(document.getElementById('recording-exception-task-id').value, 10);
        var recordedBy = parseInt(document.getElementById('recording-exception-recorded-by').value, 10);

        if (!directoryName) {
            alert('缺少录制目录');
            return;
        }
        if (!Number.isInteger(taskId) || taskId <= 0) {
            alert('请输入有效的任务 ID');
            return;
        }
        if (!Number.isInteger(recordedBy) || recordedBy <= 0) {
            alert('请选择实际录制人');
            return;
        }

        try {
            var token = this.getToken();
            var result = await api.repairRecordingException(token, {
                directory_name: directoryName,
                task_id: taskId,
                recorded_by: recordedBy
            });
            $('#recording-exception-modal').modal('hide');
            alert(result.message || '修复成功');
            await this.refresh();
        } catch (error) {
            alert('修复失败: ' + error.message);
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

    escapeAttribute(str) {
        return this.escapeHtml(str).replace(/'/g, '&#39;');
    }
}
