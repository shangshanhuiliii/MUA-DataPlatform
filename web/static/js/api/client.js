class DroidBotAPI {
    constructor(baseURL = '') {
        this.baseURL = baseURL;
        this.authExpiryHandled = false;
    }

    async request(endpoint, options = {}) {
        try {
            const requestOptions = await this.prepareRequestOptions(options);
            const response = await fetch(`${this.baseURL}/api${endpoint}`, requestOptions);
            if (!response.ok) {
                let errorMessage = `HTTP error! status: ${response.status}`;
                let errorCode = null;
                let errorData = null;
                try {
                    errorData = await response.json();
                    errorMessage = errorData.detail || errorMessage;
                    errorCode = errorData.code || null;
                } catch (e) {
                    errorMessage = response.statusText || errorMessage;
                }

                if (response.status === 401 && errorCode === 'AUTH_EXPIRED' && !options.suppressAuthExpiredHandling) {
                    this.handleAuthExpired();
                } else if (
                    errorCode === 'WORKSPACE_EXPIRED' &&
                    !options.suppressWorkspaceExpiredHandling &&
                    window.app &&
                    typeof window.app.handleWorkspaceExpired === 'function'
                ) {
                    window.app.handleWorkspaceExpired(errorData);
                }

                const error = new Error(errorMessage);
                error.response = response;
                error.status = response.status;
                error.code = errorCode;
                error.data = errorData;
                throw error;
            }
            if (response.status === 204) {
                return null;
            }
            return await response.json();
        } catch (error) {
            console.error(`API request failed: ${endpoint}`, error);
            throw error;
        }
    }

    async prepareRequestOptions(options = {}) {
        const {
            headers: optionHeaders = {},
            workspace = true,
            auth = true,
            skipAuthRefresh = false,
            suppressAuthExpiredHandling: _suppressAuthExpiredHandling,
            suppressWorkspaceExpiredHandling: _suppressWorkspaceExpiredHandling,
            ...fetchOptions
        } = options;
        const requestOptions = {
            credentials: 'same-origin',
            ...fetchOptions
        };
        const headers = { ...optionHeaders };

        const hasExplicitAuthorization = Object.prototype.hasOwnProperty.call(headers, 'Authorization');
        const explicitToken = hasExplicitAuthorization ? this.extractBearerToken(headers.Authorization) : null;
        const implicitToken = !hasExplicitAuthorization && auth !== false ? localStorage.getItem('auth_token') : null;
        const authToken = explicitToken || implicitToken;

        if (authToken) {
            const finalToken = skipAuthRefresh ? authToken : await this.ensureFreshToken(authToken);
            headers.Authorization = `Bearer ${finalToken}`;
        }

        if (workspace !== false) {
            const workspaceId = this.getWorkspaceId();
            if (workspaceId && !headers['X-Workspace-Id']) {
                headers['X-Workspace-Id'] = workspaceId;
            }
        }

        if (!headers['X-Client-Shortcode']) {
            const clientShortcode = this.getClientShortcode();
            if (clientShortcode) {
                headers['X-Client-Shortcode'] = clientShortcode;
            }
        }

        requestOptions.headers = headers;
        return requestOptions;
    }

    extractBearerToken(authorizationHeader) {
        if (!authorizationHeader || typeof authorizationHeader !== 'string') {
            return null;
        }
        return authorizationHeader.replace(/^Bearer\s+/i, '').trim() || null;
    }

    getWorkspaceId() {
        return sessionStorage.getItem('workspace_id');
    }

    setWorkspaceId(workspaceId) {
        if (workspaceId) {
            sessionStorage.setItem('workspace_id', workspaceId);
        } else {
            sessionStorage.removeItem('workspace_id');
        }
    }

    getClientShortcode() {
        const storageKey = 'client_shortcode';
        try {
            const existing = localStorage.getItem(storageKey);
            if (existing && /^[A-Z0-9]{4,12}$/.test(existing)) {
                return existing;
            }

            const shortcode = this.generateClientShortcode();
            localStorage.setItem(storageKey, shortcode);
            return shortcode;
        } catch (error) {
            console.warn('Failed to access client shortcode storage', error);
            return null;
        }
    }

    generateClientShortcode() {
        const seed = `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`.toUpperCase();
        const normalized = seed.replace(/[^A-Z0-9]/g, '');
        return (normalized.slice(0, 4) || 'CLNT').padEnd(4, 'X');
    }

    isRecordingLockConflict(error) {
        return !!(error && error.code === 'RECORDING_LOCK_CONFLICT');
    }

    formatRecordingLockConflict(error) {
        if (!this.isRecordingLockConflict(error)) {
            return error && error.message ? error.message : '当前数据被其他工作区占用';
        }

        const data = error && error.data ? error.data : {};
        const username = data.holder_username;
        const rawView = data.holder_view;
        const holderView = rawView ? this.formatRecordingLockView(rawView) : null;
        const visibleIp = data.holder_ip_full || data.holder_ip_masked || null;
        const clientShortcode = data.holder_client_shortcode || null;
        const browserInfo = this.formatRecordingLockAgent(
            data.holder_browser_name,
            data.holder_browser_version
        );
        const osInfo = this.formatRecordingLockAgent(
            data.holder_os_name,
            data.holder_os_version
        );
        const userAgent = data.holder_user_agent || null;
        const expiresAt = this.formatRecordingLockTime(data.expires_at);
        const sentences = [];

        if (!username && !holderView && !visibleIp && !clientShortcode) {
            sentences.push('当前数据处于占用状态，但占用者用户名、页面和终端信息均缺失');
        } else if (username && holderView) {
            sentences.push(`当前数据正被 ${username} 在${holderView}使用`);
        } else if (username) {
            sentences.push(`当前数据正被 ${username} 使用`);
        } else if (holderView) {
            sentences.push(`当前数据正在${holderView}被占用`);
        } else {
            sentences.push('当前数据处于占用状态');
        }

        if (visibleIp || clientShortcode) {
            const terminalParts = [];
            if (visibleIp) {
                terminalParts.push(visibleIp);
            }
            if (clientShortcode) {
                terminalParts.push(clientShortcode);
            }
            sentences.push(`终端：${terminalParts.join(' / ')}`);
        }

        if (browserInfo) {
            sentences.push(`浏览器：${browserInfo}`);
        }

        if (osInfo) {
            sentences.push(`系统：${osInfo}`);
        }

        if (userAgent) {
            sentences.push(`User-Agent：${userAgent}`);
        }

        this.pushRecordingLockMissingReason(
            sentences,
            '占用者用户名缺失',
            username,
            data.holder_username_reason,
        );
        this.pushRecordingLockMissingReason(
            sentences,
            '占用页面缺失',
            rawView,
            data.holder_view_reason,
        );
        this.pushRecordingLockMissingReason(
            sentences,
            '终端短码缺失',
            clientShortcode,
            data.holder_client_shortcode_reason,
        );

        if (visibleIp && data.holder_ip_reason === 'ip_hidden_by_policy') {
            sentences.push(`IP 完整信息不可见：${this.formatRecordingLockReason(data.holder_ip_reason)}`);
        } else {
            this.pushRecordingLockMissingReason(
                sentences,
                'IP 信息缺失',
                visibleIp,
                data.holder_ip_reason,
            );
        }

        this.pushRecordingLockMissingReason(
            sentences,
            'User-Agent 缺失',
            userAgent,
            data.holder_user_agent_reason,
        );

        if (data.diagnostic_reason_summary) {
            sentences.push(`原因：${this.formatRecordingLockReason(data.diagnostic_reason_summary)}`);
        } else if (data.lock_diagnostic_message) {
            sentences.push(data.lock_diagnostic_message.replace(/[。]+$/u, ''));
        }

        if (expiresAt) {
            sentences.push(`预计于 ${expiresAt} 释放`);
        }

        if (data.lock_diagnostic_level === 'suspicious') {
            sentences.push('这条锁状态可疑，可能需要进一步排查是否为 bug');
        }

        if (!sentences.length) {
            return error && error.message ? error.message : '当前数据被其他工作区占用';
        }
        return `${sentences.join('。')}。`;
    }

    formatRecordingLockAgent(name, version) {
        if (!name) {
            return '';
        }
        if (!version) {
            return name;
        }
        return `${name} ${version}`;
    }

    formatRecordingLockView(rawView) {
        const viewNameMap = {
            'data-editor': '数据编辑',
            'task-recorder': '任务录制',
        };
        return viewNameMap[rawView] || '其他页面';
    }

    pushRecordingLockMissingReason(sentences, label, value, reasonCode) {
        if (value || !reasonCode) {
            return;
        }
        sentences.push(`${label}：${this.formatRecordingLockReason(reasonCode)}`);
    }

    formatRecordingLockReason(reasonCode) {
        const reasonMap = {
            anonymous_workspace: '该工作区以匿名方式创建，没有绑定登录用户',
            workspace_username_not_captured: '创建工作区时未采集用户名，可能为旧版本会话或链路遗漏',
            view_not_reported: '当前会话未上报所在页面',
            view_lost_on_renewal: '续租时未携带页面信息',
            client_shortcode_not_sent: '前端未上传终端短码，可能为旧前端版本或本地存储异常',
            client_shortcode_not_persisted: '本地终端短码生成或持久化失败',
            client_ip_unavailable: '服务端未获取到客户端地址',
            proxy_header_missing: '代理链路未透传来源地址',
            ip_hidden_by_policy: '当前角色无权查看完整 IP',
            user_agent_unavailable: '服务端未收到 User-Agent',
            user_agent_not_captured: '会话元数据采集链路未记录 User-Agent',
            legacy_client_or_incomplete_session_metadata: '会话元数据未完整采集，可能为旧版本会话遗留',
            role_limited_visibility: '当前角色的可见范围受限',
            state_capture_gap: '会话状态采集存在缺口',
        };
        return reasonMap[reasonCode] || reasonCode || '未知原因';
    }

    formatRecordingLockTime(timestamp) {
        if (typeof timestamp !== 'number' || !Number.isFinite(timestamp)) {
            return '';
        }

        const date = new Date(timestamp * 1000);
        if (Number.isNaN(date.getTime())) {
            return '';
        }

        const pad = function(value) {
            return String(value).padStart(2, '0');
        };

        return [
            date.getFullYear(),
            pad(date.getMonth() + 1),
            pad(date.getDate()),
        ].join('-') + ' ' + [
            pad(date.getHours()),
            pad(date.getMinutes()),
            pad(date.getSeconds()),
        ].join(':');
    }

    decodeJwtPayload(token) {
        try {
            const parts = token.split('.');
            if (parts.length < 2) return null;
            const normalized = parts[1].replace(/-/g, '+').replace(/_/g, '/');
            const payload = decodeURIComponent(
                atob(normalized)
                    .split('')
                    .map(function(ch) {
                        return '%' + ('00' + ch.charCodeAt(0).toString(16)).slice(-2);
                    })
                    .join('')
            );
            return JSON.parse(payload);
        } catch (error) {
            console.warn('Failed to decode JWT payload', error);
            return null;
        }
    }

    tokenExpiresSoon(token, thresholdSeconds = 300) {
        const payload = this.decodeJwtPayload(token);
        if (!payload || !payload.exp) {
            return true;
        }
        const nowSeconds = Math.floor(Date.now() / 1000);
        return payload.exp - nowSeconds <= thresholdSeconds;
    }

    handleAuthExpired() {
        if (this.authExpiryHandled) {
            return;
        }
        this.authExpiryHandled = true;
        localStorage.removeItem('auth_token');
        if (window.app && typeof window.app.handleAuthExpired === 'function') {
            window.app.handleAuthExpired();
        } else {
            window.location.href = '/';
        }
        setTimeout(() => {
            this.authExpiryHandled = false;
        }, 1000);
    }

    async ensureFreshToken(token = null) {
        const currentToken = token || localStorage.getItem('auth_token');
        if (!currentToken) {
            throw new Error('Authentication required');
        }
        if (!this.tokenExpiresSoon(currentToken)) {
            return currentToken;
        }

        const refreshed = await this.refreshToken();
        if (!refreshed || !refreshed.access_token) {
            this.handleAuthExpired();
            throw new Error('Authentication expired');
        }
        localStorage.setItem('auth_token', refreshed.access_token);
        return refreshed.access_token;
    }

    async getUTG() {
        return this.request('/utg');
    }

    async updateEvent(edgeId, oldEventStr, eventType, eventStr, newFromState = null, newToState = null) {
        const body = {
            old_event_str: oldEventStr,
            event_type: eventType,
            event_str: eventStr
        };

        // 如果提供了新状态，则包含在请求中
        if (newFromState !== null) {
            body.new_from_state = newFromState;
        }
        if (newToState !== null) {
            body.new_to_state = newToState;
        }

        return this.request(`/events/${edgeId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(body)
        });
    }

    async deleteEvent(edgeId, eventStr) {
        return this.request(`/edges/${edgeId}/events`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                event_str: eventStr
            })
        });
    }

    async deleteNode(nodeId) {
        return this.request(`/nodes/${nodeId}`, {
            method: 'DELETE'
        });
    }

    async getBranchStates(nodeId) {
        return this.request(`/nodes/${nodeId}/branch`);
    }

    async batchDeleteNodes(nodeIds) {
        return this.request('/nodes/batch-delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                node_ids: nodeIds
            })
        });
    }

    async createEvent(fromState, toState, eventType, eventStr) {
        return this.request('/events', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                from: fromState,
                to: toState,
                event_type: eventType,
                event_str: eventStr
            })
        });
    }

    // Task Info API methods
    /**
     * 获取当前 recording 的 task-info
     * 使用 workspace 中的 current_recording，无需传递参数
     * @returns {Promise<{recording: string, task_info: string}>}
     */
    async getTaskInfo() {
        return this.request('/task-info');
    }

    /**
     * 更新当前 recording 的 task-info
     * 使用 workspace 中的 current_recording，无需传递参数
     * @param {string} taskInfoYaml - YAML 格式的 task-info 内容
     * @returns {Promise<{recording: string, task_info: string}>}
     */
    async updateTaskInfo(taskInfoYaml) {
        return this.request('/task-info', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                task_info_yaml: taskInfoYaml
            })
        });
    }

    /**
     * 设置 UTG 的 first_state 属性
     * @param {string} nodeId - 节点ID
     * @returns {Promise<{message: string, node_id: string}>}
     */
    async setFirstState(nodeId) {
        return this.request(`/utg/first-state`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                node_id: nodeId
            })
        });
    }

    /**
     * 设置 UTG 的 last_state 属性
     * @param {string} nodeId - 节点ID
     * @returns {Promise<{message: string, node_id: string}>}
     */
    async setLastState(nodeId) {
        return this.request(`/utg/last-state`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                node_id: nodeId
            })
        });
    }

    /**
     * 设置节点的自定义标签列表
     * @param {string} nodeId - 节点ID
     * @param {Array<string>} labels - 标签列表
     * @param {Object|null} labelMeta - 标签元数据（可选）
     * @returns {Promise<{message: string, node_id: string, labels: Array<string>}>}
     */
    async setNodeLabels(nodeId, labels, labelMeta = null) {
        return this.request(`/nodes/${nodeId}/labels`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                labels: labels,
                label_meta: labelMeta
            })
        });
    }

    /**
     * 获取被删除的节点列表
     * @returns @returns {Promise<Array<{state_str: string, image: string}>>}
     */
    async getDeletedNodes(){
        return this.request(`/nodes/deleted_nodes`, {
            method: 'GET'
        });
    }

    /**
     * 批量恢复删除节点
     * @param {Array<string>} stateList - 要恢复的节点 state_str 列表
     * @returns {Promise<{restored: Array<string>, failed: Array<{state_str: string, reason: string}>, message: string}>}
     */
    async batchRestoreNodes(stateList) {
        return this.request(`/nodes/batch_restore`, {
            method: 'POST',
            body: JSON.stringify({ state_list: stateList }),
            headers: {
                'Content-Type': 'application/json'
            }
        });
    }

    // User Authentication API methods
    async login(username, password) {
        return this.request('/auth/login', {
            method: 'POST',
            auth: false,
            workspace: false,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username, password })
        });
    }

    async refreshToken(options = {}) {
        return this.request('/auth/refresh', {
            method: 'POST',
            auth: false,
            workspace: false,
            skipAuthRefresh: true,
            ...options
        });
    }

    async logout(token = null) {
        const headers = {};
        if (token) {
            headers.Authorization = `Bearer ${token}`;
        }
        return this.request('/auth/logout', {
            method: 'POST',
            auth: false,
            skipAuthRefresh: true,
            suppressAuthExpiredHandling: true,
            headers
        });
    }

    async getCurrentUser(token) {
        return this.request('/auth/me', {
            workspace: false,
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
    }

    async getUsers(token) {
        return this.request('/users', {
            workspace: false,
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
    }

    async createUser(token, userData) {
        return this.request('/users', {
            method: 'POST',
            workspace: false,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(userData)
        });
    }

    async updateUser(token, userId, userData) {
        return this.request(`/users/${userId}`, {
            method: 'PUT',
            workspace: false,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(userData)
        });
    }

    async deleteUser(token, userId) {
        return this.request(`/users/${userId}`, {
            method: 'DELETE',
            workspace: false,
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
    }

    // ============ Task Management API ============

    async createTask(token, taskData) { // 接收对象参数（包含 description + batch_id）
        return this.request('/tasks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(taskData) // 直接传对象
        });
    }

    async getTaskList(token, params = {}) {
        const queryParams = new URLSearchParams();
        if (params.status) queryParams.append('status', params.status);
        if (params.batch_id !== undefined) queryParams.append('batch_id', params.batch_id);
        if (params.keyword) queryParams.append('keyword', params.keyword);
        if (params.assigned_user) queryParams.append('assigned_user', params.assigned_user);
        if (params.date_from) queryParams.append('date_from', params.date_from);
        if (params.date_to) queryParams.append('date_to', params.date_to);
        if (params.page) queryParams.append('page', params.page);
        if (params.page_size) queryParams.append('page_size', params.page_size);
        if (params.sort_by) queryParams.append('sort_by', params.sort_by);
        if (params.sort_order) queryParams.append('sort_order', params.sort_order);

        const url = queryParams.toString() ? `/tasks?${queryParams}` : '/tasks';
        return this.request(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async getTaskById(token, taskId) {
        return this.request(`/tasks/${taskId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async updateTask(token, taskId, data) {
        return this.request(`/tasks/${taskId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(data)
        });
    }

    async deleteTask(token, taskId) {
        return this.request(`/tasks/${taskId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async assignTask(token, taskId, userIds) {
        return this.request(`/tasks/${taskId}/assignments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ user_ids: userIds })
        });
    }

    async unassignTask(token, taskId, userId) {
        return this.request(`/tasks/${taskId}/assignments/${userId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async bulkUploadTasks(token, uploadData) { // 接收对象参数（包含 tasks + batch_id）
        return this.request('/tasks/batch', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(uploadData) // 直接传对象
        });
    }

    async batchDeleteTasks(token, taskIds) {
        const idsParam = taskIds.join(',');
        return this.request(`/tasks?ids=${idsParam}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
    }

    async batchAssignTasks(token, taskIds, userIds) {
        return this.request('/tasks/assignments', {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ task_ids: taskIds, user_ids: userIds })
        });
    }

    // ============ Recording Management API ============

    async getRecordings(token, params = {}) {
        const queryParams = new URLSearchParams();
        if (params.task_id) queryParams.append('task_id', params.task_id);
        if (params.keyword) queryParams.append('keyword', params.keyword);
        if (params.batch_id !== undefined && params.batch_id !== null) queryParams.append('batch_id', params.batch_id);
        if (params.recorded_by) queryParams.append('recorded_by', params.recorded_by);
        if (params.date_from) queryParams.append('date_from', params.date_from);
        if (params.date_to) queryParams.append('date_to', params.date_to);
        if (params.page) queryParams.append('page', params.page);
        if (params.page_size) queryParams.append('page_size', params.page_size);
        if (params.sort_by) queryParams.append('sort_by', params.sort_by);
        if (params.sort_order) queryParams.append('sort_order', params.sort_order);

        const url = queryParams.toString() ? `/recordings?${queryParams}` : '/recordings';
        return this.request(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async getRecordingById(token, recordingId) {
        return this.request(`/recordings/${recordingId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async getRecordingExceptions(token, params = {}) {
        const queryParams = new URLSearchParams();
        if (params.keyword) queryParams.append('keyword', params.keyword);
        if (params.exception_type) queryParams.append('exception_type', params.exception_type);

        const url = queryParams.toString() ? `/recordings/exceptions?${queryParams}` : '/recordings/exceptions';
        return this.request(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async repairRecordingException(token, data) {
        return this.request('/recordings/exceptions/repair', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(data)
        });
    }

    async updateRecording(token, recordingId, data) {
        return this.request(`/recordings/${recordingId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(data)
        });
    }

    async deleteRecording(token, recordingId) {
        return this.request(`/recordings/${recordingId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    // ============ Workspace + Current Recording API ============

    async bootstrapWorkspace(workspaceId = null, currentView = null) {
        const payload = {};
        if (workspaceId) payload.workspace_id = workspaceId;
        if (currentView) payload.current_view = currentView;
        const token = localStorage.getItem('auth_token');
        const baseOptions = {
            method: 'POST',
            auth: false,
            workspace: false,
            skipAuthRefresh: true,
            suppressAuthExpiredHandling: true,
            suppressWorkspaceExpiredHandling: true,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        };
        const sendBootstrap = async (accessToken = null, requestedWorkspaceId = workspaceId) => this.request('/workspaces/bootstrap', {
            ...baseOptions,
            body: JSON.stringify({
                ...(requestedWorkspaceId ? { workspace_id: requestedWorkspaceId } : {}),
                ...(currentView ? { current_view: currentView } : {})
            }),
            headers: {
                ...baseOptions.headers,
                ...(accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {})
            }
        });

        let result = null;
        try {
            result = await sendBootstrap(token, workspaceId);
        } catch (error) {
            if (token && error && error.code === 'AUTH_EXPIRED') {
                let refreshed = null;
                try {
                    refreshed = await this.refreshToken({
                        suppressAuthExpiredHandling: true
                    });
                } catch (refreshError) {
                    this.handleAuthExpired();
                    throw refreshError;
                }
                if (!refreshed || !refreshed.access_token) {
                    this.handleAuthExpired();
                    throw error;
                }
                localStorage.setItem('auth_token', refreshed.access_token);
                try {
                    result = await sendBootstrap(refreshed.access_token, workspaceId);
                } catch (retryError) {
                    if (retryError && retryError.code === 'AUTH_EXPIRED') {
                        this.handleAuthExpired();
                        throw retryError;
                    }
                    if (workspaceId && retryError && retryError.code === 'WORKSPACE_EXPIRED') {
                        this.setWorkspaceId(null);
                        result = await sendBootstrap(refreshed.access_token, null);
                    } else {
                        throw retryError;
                    }
                }
            } else if (workspaceId && error && error.code === 'WORKSPACE_EXPIRED') {
                this.setWorkspaceId(null);
                result = await sendBootstrap(token, null);
            } else {
                throw error;
            }
        }

        if (result && result.workspace_id) {
            this.setWorkspaceId(result.workspace_id);
        }
        return result;
    }

    async reportWorkspaceActivity(currentView = null) {
        const workspaceId = this.getWorkspaceId();
        if (!workspaceId) {
            return null;
        }
        return this.request(`/workspaces/${encodeURIComponent(workspaceId)}/activity`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ current_view: currentView })
        });
    }

    async releaseWorkspace() {
        const workspaceId = this.getWorkspaceId();
        if (!workspaceId) {
            return null;
        }
        const result = await this.request(`/workspaces/${encodeURIComponent(workspaceId)}`, {
            method: 'DELETE'
        });
        this.setWorkspaceId(null);
        return result;
    }

    async getCurrentRecording() {
        return this.request('/recordings/current');
    }

    async setCurrentRecording(directoryName) {
        return this.request(`/recordings/current/${encodeURIComponent(directoryName)}`, {
            method: 'POST'
        });
    }

    async releaseCurrentRecording() {
        return this.request('/recordings/current', {
            method: 'DELETE'
        });
    }

    
    // ============ Batch Management API ============

    async getBatches(token, params = {}) {
        const queryParams = new URLSearchParams();
        if (params.page) queryParams.append('page', params.page);
        if (params.page_size) queryParams.append('page_size', params.page_size);
        if (params.sort_by) queryParams.append('sort_by', params.sort_by);
        if (params.sort_order) queryParams.append('sort_order', params.sort_order);
        const url = queryParams.toString() ? `/batches?${queryParams}` : '/batches';
        return this.request(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async getBatch(token, batchId) {
        return this.request(`/batches/${batchId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async createBatch(token, data) {
        return this.request('/batches', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(data)
        });
    }

    async updateBatch(token, batchId, data) {
        return this.request(`/batches/${batchId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(data)
        });
    }

    async deleteBatch(token, batchId) {
        return this.request(`/batches/${batchId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async getBatchAllocations(token, batchId) {
        return this.request(`/batches/${batchId}/allocations`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async saveBatchAllocations(token, batchId, userIds) {
        return this.request(`/batches/${batchId}/allocations`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ user_ids: userIds })
        });
    }

    async getMyBatchAllocation(token, batchId) {
        return this.request(`/batches/${batchId}/my-allocation`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async getClaimableTasks(token, batchId, pageSize) {
        return this.request(`/batches/${batchId}/claimable-tasks?page=1&page_size=${pageSize}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async claimTask(token, batchId, taskId) {
        return this.request(`/batches/${batchId}/claim-task`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ task_id: taskId })
        });
    }

    async batchMoveTasks(token, taskIds, targetBatchId) {
        return this.request('/tasks/batch-move', {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                task_ids: taskIds,
                target_batch_id: targetBatchId
            })
        });
    }


    // ============ Cloud Device Management API ============

    async getCloudDevices(token, params = {}) {
        const queryParams = new URLSearchParams();
        if (params.is_active !== undefined) queryParams.append('is_active', params.is_active);
        if (params.search) queryParams.append('search', params.search);
        if (params.page) queryParams.append('page', params.page);
        if (params.page_size) queryParams.append('page_size', params.page_size);

        const url = queryParams.toString() ? `/cloud-devices?${queryParams}` : '/cloud-devices';
        return this.request(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async getCloudDevice(token, deviceId) {
        return this.request(`/cloud-devices/${deviceId}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async createCloudDevice(token, data) {
        return this.request('/cloud-devices', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(data)
        });
    }

    async updateCloudDevice(token, deviceId, data) {
        return this.request(`/cloud-devices/${deviceId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(data)
        });
    }

    async deleteCloudDevice(token, deviceId) {
        return this.request(`/cloud-devices/${deviceId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
    }

    async bulkUploadCloudDevices(token, devices) {
        return this.request('/cloud-devices/batch', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ devices })
        });
    }

    async batchUpdateCloudDeviceStatus(token, deviceIds, isActive) {
        return this.request('/cloud-devices/batch', {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ device_ids: deviceIds, is_active: isActive })
        });
    }

    async batchDeleteCloudDevices(token, deviceIds) {
        const idsParam = deviceIds.join(',');
        return this.request(`/cloud-devices?ids=${idsParam}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
    }

    // 连接云手机设备
    async connectCloudDevice(token, deviceId, forceReconnect = false) {
        return this.request(`/cloud-devices/${deviceId}/connections`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ force_reconnect: forceReconnect })
        });
    }
}

const api = new DroidBotAPI();
