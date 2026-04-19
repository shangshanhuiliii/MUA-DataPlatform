/**
 * User Manager Component
 * Handles user authentication and management
 */
class UserManager {
    constructor(containerId) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.currentUser = null;
        this.users = [];
        this.token = localStorage.getItem('auth_token');
        this.isVisible = false;

        this.init();
    }

    init() {
        this.render();
        if (this.token) {
            this.loadCurrentUser();
        }
    }

    render() {
        this.container.innerHTML = `
            <div class="user-manager">
                <div id="login-section" style="display: none;">
                    <div class="panel panel-default">
                        <div class="panel-heading"><h4>用户登录</h4></div>
                        <div class="panel-body">
                            <form id="login-form" class="form-horizontal">
                                <div class="form-group">
                                    <label class="col-sm-2 control-label">用户名</label>
                                    <div class="col-sm-10">
                                        <input type="text" class="form-control" id="login-username" required>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="col-sm-2 control-label">密码</label>
                                    <div class="col-sm-10">
                                        <input type="password" class="form-control" id="login-password" required>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <div class="col-sm-offset-2 col-sm-10">
                                        <button type="submit" class="btn btn-primary">登录</button>
                                    </div>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>

                <div id="user-management-section" style="display: none;">
                    <div class="panel panel-default">
                        <div class="panel-heading">
                            <h4>用户管理</h4>
                            <div class="pull-right" style="margin-top: -25px;">
                                <span id="current-user-info"></span>
                                <button class="btn btn-sm btn-danger" onclick="window.app.userManager.logout()">退出登录</button>
                            </div>
                        </div>
                        <div class="panel-body">
                            <button id="create-user-btn" class="btn btn-success" onclick="window.app.userManager.showCreateUserModal()">
                                <span class="glyphicon glyphicon-plus"></span> 创建用户
                            </button>
                            <hr>
                            <table class="table table-striped table-hover">
                                <thead>
                                    <tr>
                                        <th>ID</th>
                                        <th>用户名</th>
                                        <th>邮箱</th>
                                        <th>全名</th>
                                        <th>状态</th>
                                        <th>管理员</th>
                                        <th>创建时间</th>
                                        <th>操作</th>
                                    </tr>
                                </thead>
                                <tbody id="users-table-body"></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Create/Edit User Modal -->
            <div class="modal fade" id="user-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title" id="user-modal-title">创建用户</h4>
                        </div>
                        <div class="modal-body">
                            <form id="user-form" class="form-horizontal">
                                <input type="hidden" id="user-id">
                                <div class="form-group">
                                    <label class="col-sm-3 control-label">用户名 *</label>
                                    <div class="col-sm-9">
                                        <input type="text" class="form-control" id="user-username" required>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="col-sm-3 control-label">邮箱 *</label>
                                    <div class="col-sm-9">
                                        <input type="email" class="form-control" id="user-email" required>
                                    </div>
                                </div>
                                <div class="form-group" id="password-group">
                                    <label class="col-sm-3 control-label">密码</label>
                                    <div class="col-sm-9">
                                        <input type="password" class="form-control" id="user-password" minlength="8">
                                        <p class="help-block" id="password-help">创建/修改时填写，编辑时选填（留空则不修改）</p>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="col-sm-3 control-label">全名</label>
                                    <div class="col-sm-9">
                                        <input type="text" class="form-control" id="user-fullname">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <div class="col-sm-offset-3 col-sm-9">
                                        <div class="checkbox">
                                            <label>
                                                <input type="checkbox" id="user-active"> 激活状态
                                            </label>
                                        </div>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <div class="col-sm-offset-3 col-sm-9">
                                        <div class="checkbox">
                                            <label>
                                                <input type="checkbox" id="user-superuser"> 管理员权限
                                            </label>
                                        </div>
                                    </div>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.userManager.saveUser()">保存</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Setup event listeners
        document.getElementById('login-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.login();
        });

        // Show appropriate section
        if (this.token) {
            document.getElementById('user-management-section').style.display = 'block';
        } else {
            document.getElementById('login-section').style.display = 'block';
        }
    }

    async login() {
        const username = document.getElementById('login-username').value;
        const password = document.getElementById('login-password').value;

        try {
            const restoreView = this.resolvePostLoginView();
            const data = await api.login(username, password);
            if (window.app && typeof window.app.resetWorkspaceScopedState === 'function') {
                window.app.resetWorkspaceScopedState();
            }
            this.token = data.access_token;
            localStorage.setItem('auth_token', this.token);
            const bootstrapResult = await api.bootstrapWorkspace(
                api.getWorkspaceId(),
                restoreView
            );
            if (window.app && typeof window.app.applyBootstrapWorkspaceState === 'function') {
                window.app.applyBootstrapWorkspaceState(bootstrapResult);
            }

            await this.loadCurrentUser();
            this.render();
            this.loadUsers();
            await this.navigateAfterLogin(restoreView);
            if (
                restoreView === 'task-recorder' &&
                window.app &&
                typeof window.app.restoreTaskRecorderWorkspaceView === 'function'
            ) {
                await window.app.restoreTaskRecorderWorkspaceView(bootstrapResult);
            }
        } catch (error) {
            alert('登录失败: ' + error.message);
        }
    }

    async logout() {
        try {
            await api.logout(this.token);
        } catch (error) {
            console.warn('Logout request failed', error);
        } finally {
            if (window.app && typeof window.app.resetWorkspaceScopedState === 'function') {
                window.app.resetWorkspaceScopedState({ disconnectTaskRecorder: true });
            }
            if (window.app) {
                window.app.suspendedWorkspaceView = null;
            }
            this.token = null;
            this.currentUser = null;
            localStorage.removeItem('auth_token');
            api.setWorkspaceId(null);
            this.render();
            if (window.showUserManager) {
                await window.showUserManager();
            }
        }
    }

    async loadCurrentUser() {
        try {
            this.currentUser = await api.getCurrentUser(this.token);
            const userInfo = document.getElementById('current-user-info');
            if (userInfo) {
                userInfo.textContent = `当前用户: ${this.currentUser.username} ${this.currentUser.is_superuser ? '(管理员)' : ''}  `;
            }

            // Disable create button for non-admin users
            const createBtn = document.getElementById('create-user-btn');
            if (createBtn) {
                createBtn.disabled = !this.currentUser.is_superuser;
            }
        } catch (error) {
            console.error('Failed to load current user:', error);
            await this.logout();
        }
    }

    async loadUsers() {
        try {
            this.users = await api.getUsers(this.token);
            this.renderUsersTable();
        } catch (error) {
            alert('加载用户列表失败: ' + error.message);
        }
    }

    renderUsersTable() {
        const tbody = document.getElementById('users-table-body');
        tbody.innerHTML = this.users.map(user => `
            <tr>
                <td>${user.id}</td>
                <td>${user.username}</td>
                <td>${user.email}</td>
                <td>${user.full_name || '-'}</td>
                <td>${user.is_active ? '<span class="label label-success">激活</span>' : '<span class="label label-default">禁用</span>'}</td>
                <td>${user.is_superuser ? '<span class="label label-danger">是</span>' : '否'}</td>
                <td>${new Date(user.created_at).toLocaleString()}</td>
                <td>
                    <button class="btn btn-xs btn-info" onclick="window.app.userManager.showEditUserModal(${user.id})">
                        <span class="glyphicon glyphicon-edit"></span> 编辑
                    </button>
                    ${user.id !== this.currentUser.id ? `
                        <button class="btn btn-xs btn-danger" onclick="window.app.userManager.deleteUser(${user.id})">
                            <span class="glyphicon glyphicon-trash"></span> 删除
                        </button>
                    ` : ''}
                </td>
            </tr>
        `).join('');
    }

    showCreateUserModal() {
        document.getElementById('user-modal-title').textContent = '创建用户';
        document.getElementById('user-id').value = '';
        document.getElementById('user-username').value = '';
        document.getElementById('user-username').disabled = false;  // 启用用户名字段
        document.getElementById('user-email').value = '';
        document.getElementById('user-password').value = '';
        document.getElementById('user-fullname').value = '';
        document.getElementById('user-active').checked = true;
        document.getElementById('user-superuser').checked = false;
        document.getElementById('password-group').style.display = 'block';
        document.getElementById('user-password').required = true;
        $('#user-modal').modal('show');
    }

    showEditUserModal(userId) {
        const user = this.users.find(u => u.id === userId);
        if (!user) return;

        document.getElementById('user-modal-title').textContent = '编辑用户';
        document.getElementById('user-id').value = user.id;
        document.getElementById('user-username').value = user.username;
        document.getElementById('user-username').disabled = true;
        document.getElementById('user-email').value = user.email;
        document.getElementById('user-password').value = '';
        document.getElementById('user-fullname').value = user.full_name || '';
        document.getElementById('user-active').checked = user.is_active;
        document.getElementById('user-superuser').checked = user.is_superuser;
        document.getElementById('password-group').style.display = 'block';
        document.getElementById('user-password').required = false;
        $('#user-modal').modal('show');
    }

    async saveUser() {
        const userId = document.getElementById('user-id').value;
        const username = document.getElementById('user-username').value;
        const email = document.getElementById('user-email').value;
        const password = document.getElementById('user-password').value;
        const fullName = document.getElementById('user-fullname').value;
        const isActive = document.getElementById('user-active').checked;
        const isSuperuser = document.getElementById('user-superuser').checked;

        try {
            if (userId) {
                // Update user
                const updateData = {
                    email,
                    full_name: fullName || null,
                    is_active: isActive,
                    is_superuser: isSuperuser
                };

                // 只有填写了密码才包含在更新数据中
                if (password) {
                    updateData.password = password;
                }

                await api.updateUser(this.token, userId, updateData);
            } else {
                // Create user
                await api.createUser(this.token, {
                    username,
                    email,
                    password,
                    full_name: fullName || null,
                    is_superuser: isSuperuser
                });
            }

            $('#user-modal').modal('hide');
            await this.loadUsers();
        } catch (error) {
            alert('保存用户失败: ' + error.message);
        }
    }

    async deleteUser(userId) {
        if (!confirm('确定要删除这个用户吗？')) return;

        try {
            await api.deleteUser(this.token, userId);
            await this.loadUsers();
        } catch (error) {
            alert('删除用户失败: ' + error.message);
        }
    }

    show() {
        this.isVisible = true;
        this.container.style.display = 'block';
        if (this.token && this.currentUser) {
            this.loadUsers();
        }
    }

    hide() {
        this.isVisible = false;
        this.container.style.display = 'none';
    }

    resolvePostLoginView() {
        if (window.app && window.app.suspendedWorkspaceView) {
            return window.app.suspendedWorkspaceView;
        }
        if (window.app && window.app.currentView && window.app.currentView !== 'user-manager') {
            return window.app.currentView;
        }
        return 'task-recorder';
    }

    async navigateAfterLogin(restoreView) {
        const targetView = restoreView || 'task-recorder';
        if (window.app) {
            window.app.suspendedWorkspaceView = null;
        }

        if (targetView === 'data-editor' && window.showDataEditor) {
            await window.showDataEditor();
            return;
        }
        if (targetView === 'task-manager' && window.showTaskManager) {
            await window.showTaskManager();
            return;
        }
        if (targetView === 'cloud-device-manager' && window.showCloudDeviceManager) {
            await window.showCloudDeviceManager();
            return;
        }
        if (targetView === 'recording-exception-manager' && window.showRecordingExceptionManager) {
            await window.showRecordingExceptionManager();
            return;
        }

        if (window.showTaskRecorder) {
            await window.showTaskRecorder();
        }
    }
}
