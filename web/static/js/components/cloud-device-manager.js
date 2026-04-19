/**
 * Cloud Device Manager Component
 * Manages cloud phone devices (Volcengine ACEP)
 */
class CloudDeviceManager {
    constructor(containerId) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.devices = [];
        this.selectedIds = new Set();
        this.currentPage = 1;
        this.pageSize = 20;
        this.total = 0;
        this.filterActive = null;
        this.searchQuery = '';
        this.isVisible = false;

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
            <div class="cloud-device-manager">
                <div class="panel panel-default">
                    <div class="panel-heading">
                        <h4>云手机设备管理</h4>
                    </div>
                    <div class="panel-body">
                        <!-- Toolbar -->
                        <div class="row" style="margin-bottom: 15px;">
                            <div class="col-sm-6">
                                <button class="btn btn-success" onclick="window.app.cloudDeviceManager.showCreateModal()">
                                    <span class="glyphicon glyphicon-plus"></span> 添加设备
                                </button>
                                <button class="btn btn-info" onclick="window.app.cloudDeviceManager.showBulkUploadModal()">
                                    <span class="glyphicon glyphicon-upload"></span> 批量上传
                                </button>
                                <div class="btn-group">
                                    <button class="btn btn-default dropdown-toggle" data-toggle="dropdown" id="batch-actions-btn" disabled>
                                        批量操作 <span class="caret"></span>
                                    </button>
                                    <ul class="dropdown-menu">
                                        <li><a href="#" onclick="window.app.cloudDeviceManager.batchActivate(); return false;">激活选中</a></li>
                                        <li><a href="#" onclick="window.app.cloudDeviceManager.batchDeactivate(); return false;">停用选中</a></li>
                                        <li class="divider"></li>
                                        <li><a href="#" onclick="window.app.cloudDeviceManager.batchDelete(); return false;">删除选中</a></li>
                                    </ul>
                                </div>
                            </div>
                            <div class="col-sm-6">
                                <div class="input-group">
                                    <input type="text" class="form-control" id="cloud-device-search"
                                           placeholder="搜索Product ID / Pod ID / 别名">
                                    <span class="input-group-btn">
                                        <button class="btn btn-default" onclick="window.app.cloudDeviceManager.search()">
                                            <span class="glyphicon glyphicon-search"></span>
                                        </button>
                                    </span>
                                </div>
                            </div>
                        </div>

                        <!-- Filter -->
                        <div class="row" style="margin-bottom: 15px;">
                            <div class="col-sm-12">
                                <div class="btn-group" data-toggle="buttons">
                                    <label class="btn btn-default active" onclick="window.app.cloudDeviceManager.setFilter(null)">
                                        <input type="radio" name="filter" checked> 全部
                                    </label>
                                    <label class="btn btn-default" onclick="window.app.cloudDeviceManager.setFilter(true)">
                                        <input type="radio" name="filter"> 已激活
                                    </label>
                                    <label class="btn btn-default" onclick="window.app.cloudDeviceManager.setFilter(false)">
                                        <input type="radio" name="filter"> 未激活
                                    </label>
                                </div>
                                <span id="cloud-device-count" class="text-muted" style="margin-left: 15px;"></span>
                            </div>
                        </div>

                        <!-- Table -->
                        <table class="table table-striped table-hover">
                            <thead>
                                <tr>
                                    <th style="width: 30px;">
                                        <input type="checkbox" id="select-all-devices"
                                               onchange="window.app.cloudDeviceManager.toggleSelectAll(this.checked)">
                                    </th>
                                    <th>ID</th>
                                    <th>Product ID</th>
                                    <th>Pod ID</th>
                                    <th>别名</th>
                                    <th>状态</th>
                                    <th>创建时间</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody id="cloud-devices-table-body"></tbody>
                        </table>

                        <!-- Pagination -->
                        <div class="text-center" id="cloud-device-pagination"></div>
                    </div>
                </div>
            </div>

            <!-- Create/Edit Modal -->
            <div class="modal fade" id="cloud-device-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title" id="cloud-device-modal-title">添加云设备</h4>
                        </div>
                        <div class="modal-body">
                            <form id="cloud-device-form" class="form-horizontal">
                                <input type="hidden" id="cloud-device-id">
                                <div class="form-group">
                                    <label class="col-sm-3 control-label">Product ID *</label>
                                    <div class="col-sm-9">
                                        <input type="text" class="form-control" id="cloud-device-product-id" required>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="col-sm-3 control-label">Pod ID *</label>
                                    <div class="col-sm-9">
                                        <input type="text" class="form-control" id="cloud-device-pod-id" required>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="col-sm-3 control-label">别名</label>
                                    <div class="col-sm-9">
                                        <input type="text" class="form-control" id="cloud-device-alias">
                                    </div>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.cloudDeviceManager.saveDevice()">保存</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Bulk Upload Modal -->
            <div class="modal fade" id="bulk-upload-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title">批量上传云设备</h4>
                        </div>
                        <div class="modal-body">
                            <div class="form-group">
                                <label>上传 CSV 文件</label>
                                <input type="file" class="form-control" id="csv-file-input" accept=".csv">
                                <p class="help-block">CSV 格式: product_id,pod_id,alias (第一行为表头)</p>
                            </div>
                            <hr>
                            <div class="form-group">
                                <label>或直接粘贴数据</label>
                                <textarea class="form-control" id="bulk-upload-text" rows="6"
                                          placeholder="每行一个设备，格式: product_id,pod_id,alias"></textarea>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.cloudDeviceManager.bulkUpload()">上传</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Setup search on Enter
        document.getElementById('cloud-device-search').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.search();
        });
    }

    async loadDevices() {
        const token = this.getToken();
        if (!token) return;

        try {
            const params = {
                page: this.currentPage,
                page_size: this.pageSize
            };
            if (this.filterActive !== null) params.is_active = this.filterActive;
            if (this.searchQuery) params.search = this.searchQuery;

            const data = await api.getCloudDevices(token, params);
            this.devices = data.items;
            this.total = data.total;
            this.renderTable();
            this.renderPagination();
            this.updateCount();
        } catch (error) {
            alert('加载设备列表失败: ' + error.message);
        }
    }

    renderTable() {
        const tbody = document.getElementById('cloud-devices-table-body');
        if (!tbody) return;

        tbody.innerHTML = this.devices.map(device => `
            <tr>
                <td>
                    <input type="checkbox" class="device-checkbox" data-id="${device.id}"
                           ${this.selectedIds.has(device.id) ? 'checked' : ''}
                           onchange="window.app.cloudDeviceManager.toggleSelect(${device.id}, this.checked)">
                </td>
                <td>${device.id}</td>
                <td>${device.product_id}</td>
                <td>${device.pod_id}</td>
                <td>${device.alias || '-'}</td>
                <td>
                    ${device.is_active
                        ? '<span class="label label-success">已激活</span>'
                        : '<span class="label label-default">未激活</span>'}
                </td>
                <td>${new Date(device.created_at).toLocaleString()}</td>
                <td>
                    <button class="btn btn-xs btn-info" onclick="window.app.cloudDeviceManager.showEditModal(${device.id})">
                        <span class="glyphicon glyphicon-edit"></span>
                    </button>
                    <button class="btn btn-xs ${device.is_active ? 'btn-warning' : 'btn-success'}"
                            onclick="window.app.cloudDeviceManager.toggleActive(${device.id}, ${!device.is_active})">
                        <span class="glyphicon glyphicon-${device.is_active ? 'pause' : 'play'}"></span>
                    </button>
                    <button class="btn btn-xs btn-danger" onclick="window.app.cloudDeviceManager.deleteDevice(${device.id})">
                        <span class="glyphicon glyphicon-trash"></span>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    renderPagination() {
        const totalPages = Math.ceil(this.total / this.pageSize);
        const pagination = document.getElementById('cloud-device-pagination');
        if (!pagination || totalPages <= 1) {
            if (pagination) pagination.innerHTML = '';
            return;
        }

        let html = '<ul class="pagination">';
        html += `<li class="${this.currentPage === 1 ? 'disabled' : ''}">
                    <a href="#" onclick="window.app.cloudDeviceManager.goToPage(${this.currentPage - 1}); return false;">&laquo;</a>
                 </li>`;

        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                html += `<li class="${i === this.currentPage ? 'active' : ''}">
                            <a href="#" onclick="window.app.cloudDeviceManager.goToPage(${i}); return false;">${i}</a>
                         </li>`;
            } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                html += '<li class="disabled"><a>...</a></li>';
            }
        }

        html += `<li class="${this.currentPage === totalPages ? 'disabled' : ''}">
                    <a href="#" onclick="window.app.cloudDeviceManager.goToPage(${this.currentPage + 1}); return false;">&raquo;</a>
                 </li>`;
        html += '</ul>';
        pagination.innerHTML = html;
    }

    updateCount() {
        const countEl = document.getElementById('cloud-device-count');
        if (countEl) countEl.textContent = `共 ${this.total} 个设备`;
    }

    goToPage(page) {
        const totalPages = Math.ceil(this.total / this.pageSize);
        if (page < 1 || page > totalPages) return;
        this.currentPage = page;
        this.loadDevices();
    }

    setFilter(isActive) {
        this.filterActive = isActive;
        this.currentPage = 1;
        this.loadDevices();
    }

    search() {
        this.searchQuery = document.getElementById('cloud-device-search').value.trim();
        this.currentPage = 1;
        this.loadDevices();
    }

    toggleSelect(id, checked) {
        if (checked) {
            this.selectedIds.add(id);
        } else {
            this.selectedIds.delete(id);
        }
        this.updateBatchButton();
    }

    toggleSelectAll(checked) {
        this.devices.forEach(d => {
            if (checked) {
                this.selectedIds.add(d.id);
            } else {
                this.selectedIds.delete(d.id);
            }
        });
        document.querySelectorAll('.device-checkbox').forEach(cb => cb.checked = checked);
        this.updateBatchButton();
    }

    updateBatchButton() {
        const btn = document.getElementById('batch-actions-btn');
        if (btn) btn.disabled = this.selectedIds.size === 0;
    }

    showCreateModal() {
        document.getElementById('cloud-device-modal-title').textContent = '添加云设备';
        document.getElementById('cloud-device-id').value = '';
        document.getElementById('cloud-device-product-id').value = '';
        document.getElementById('cloud-device-product-id').disabled = false;
        document.getElementById('cloud-device-pod-id').value = '';
        document.getElementById('cloud-device-pod-id').disabled = false;
        document.getElementById('cloud-device-alias').value = '';
        $('#cloud-device-modal').modal('show');
    }

    showEditModal(deviceId) {
        const device = this.devices.find(d => d.id === deviceId);
        if (!device) return;

        document.getElementById('cloud-device-modal-title').textContent = '编辑云设备';
        document.getElementById('cloud-device-id').value = device.id;
        document.getElementById('cloud-device-product-id').value = device.product_id;
        document.getElementById('cloud-device-product-id').disabled = true;
        document.getElementById('cloud-device-pod-id').value = device.pod_id;
        document.getElementById('cloud-device-pod-id').disabled = true;
        document.getElementById('cloud-device-alias').value = device.alias || '';
        $('#cloud-device-modal').modal('show');
    }

    async saveDevice() {
        const token = this.getToken();
        const deviceId = document.getElementById('cloud-device-id').value;
        const productId = document.getElementById('cloud-device-product-id').value.trim();
        const podId = document.getElementById('cloud-device-pod-id').value.trim();
        const alias = document.getElementById('cloud-device-alias').value.trim();

        if (!productId || !podId) {
            alert('Product ID 和 Pod ID 为必填项');
            return;
        }

        try {
            if (deviceId) {
                await api.updateCloudDevice(token, deviceId, { alias: alias || null });
            } else {
                await api.createCloudDevice(token, { product_id: productId, pod_id: podId, alias: alias || null });
            }
            $('#cloud-device-modal').modal('hide');
            this.loadDevices();
        } catch (error) {
            alert('保存失败: ' + error.message);
        }
    }

    async toggleActive(deviceId, isActive) {
        const token = this.getToken();
        try {
            await api.updateCloudDevice(token, deviceId, { is_active: isActive });
            this.loadDevices();
        } catch (error) {
            alert('操作失败: ' + error.message);
        }
    }

    async deleteDevice(deviceId) {
        if (!confirm('确定要删除这个设备吗？')) return;
        const token = this.getToken();
        try {
            await api.deleteCloudDevice(token, deviceId);
            this.loadDevices();
        } catch (error) {
            alert('删除失败: ' + error.message);
        }
    }

    showBulkUploadModal() {
        document.getElementById('csv-file-input').value = '';
        document.getElementById('bulk-upload-text').value = '';
        $('#bulk-upload-modal').modal('show');
    }

    async bulkUpload() {
        const token = this.getToken();
        const fileInput = document.getElementById('csv-file-input');
        const textInput = document.getElementById('bulk-upload-text').value.trim();

        let devices = [];

        if (fileInput.files.length > 0) {
            const text = await fileInput.files[0].text();
            devices = this.parseCSV(text);
        } else if (textInput) {
            devices = this.parseCSV(textInput);
        }

        if (devices.length === 0) {
            alert('没有有效的设备数据');
            return;
        }

        try {
            const result = await api.bulkUploadCloudDevices(token, devices);
            alert(`上传完成: 成功 ${result.success} 个, 失败 ${result.failed} 个` +
                  (result.errors.length > 0 ? '\n\n错误:\n' + result.errors.join('\n') : ''));
            $('#bulk-upload-modal').modal('hide');
            this.loadDevices();
        } catch (error) {
            alert('上传失败: ' + error.message);
        }
    }

    parseCSV(text) {
        const lines = text.split('\n').map(l => l.trim()).filter(l => l);
        const devices = [];

        for (let i = 0; i < lines.length; i++) {
            const parts = lines[i].split(',').map(p => p.trim());
            // Skip header row
            if (i === 0 && parts[0].toLowerCase() === 'product_id') continue;

            if (parts.length >= 2 && parts[0] && parts[1]) {
                devices.push({
                    product_id: parts[0],
                    pod_id: parts[1],
                    alias: parts[2] || null
                });
            }
        }
        return devices;
    }

    async batchActivate() {
        if (this.selectedIds.size === 0) return;
        const token = this.getToken();
        try {
            const result = await api.batchUpdateCloudDeviceStatus(token, Array.from(this.selectedIds), true);
            alert(`激活完成: 成功 ${result.success} 个, 失败 ${result.failed} 个`);
            this.selectedIds.clear();
            this.loadDevices();
        } catch (error) {
            alert('批量激活失败: ' + error.message);
        }
    }

    async batchDeactivate() {
        if (this.selectedIds.size === 0) return;
        const token = this.getToken();
        try {
            const result = await api.batchUpdateCloudDeviceStatus(token, Array.from(this.selectedIds), false);
            alert(`停用完成: 成功 ${result.success} 个, 失败 ${result.failed} 个`);
            this.selectedIds.clear();
            this.loadDevices();
        } catch (error) {
            alert('批量停用失败: ' + error.message);
        }
    }

    async batchDelete() {
        if (this.selectedIds.size === 0) return;
        if (!confirm(`确定要删除选中的 ${this.selectedIds.size} 个设备吗？`)) return;
        const token = this.getToken();
        try {
            const result = await api.batchDeleteCloudDevices(token, Array.from(this.selectedIds));
            alert(`删除完成: 成功 ${result.success} 个, 失败 ${result.failed} 个`);
            this.selectedIds.clear();
            this.loadDevices();
        } catch (error) {
            alert('批量删除失败: ' + error.message);
        }
    }

    async show() {
        this.isVisible = true;
        this.container.style.display = 'block';

        const token = this.getToken();
        if (!token) {
            this.showNoPermission('请登录管理员账号管理设备');
            return;
        }

        // Check if user is admin
        try {
            const user = await api.getCurrentUser(token);
            if (!user.is_superuser) {
                this.showNoPermission('当前账号无权限管理设备');
                return;
            }
            this.render();
            this.loadDevices();
        } catch (error) {
            this.showNoPermission('请登录管理员账号管理设备');
        }
    }

    showNoPermission(message) {
        this.container.innerHTML = `
            <div class="cloud-device-manager">
                <div class="panel panel-default">
                    <div class="panel-heading"><h4>云手机设备管理</h4></div>
                    <div class="panel-body text-center" style="padding: 50px;">
                        <span class="glyphicon glyphicon-lock" style="font-size: 48px; color: #ccc;"></span>
                        <h4 style="margin-top: 20px; color: #999;">${message}</h4>
                    </div>
                </div>
            </div>
        `;
    }

    hide() {
        this.isVisible = false;
        this.container.style.display = 'none';
    }
}
