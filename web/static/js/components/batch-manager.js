/**
 * Batch Manager Component
 * 批次管理组件 - 卡片看板布局
 */
class BatchManager {
    constructor(containerId) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.batches = [];
        this.currentPage = 1;
        this.pageSize = 20;
        this.totalPages = 1;
        this.sortBy = 'created_at';
        this.sortOrder = 'desc';
        this.isVisible = false;

        this.init();
    }

    getToken() {
        return localStorage.getItem('auth_token');
    }

    isAdmin() {
        return !!(window.app.userManager &&
                  window.app.userManager.currentUser &&
                  window.app.userManager.currentUser.is_superuser);
    }

    init() {
        this.render();
    }

    render() {
        this.container.innerHTML = `
            <div class="batch-manager">
                <div class="panel panel-default">
                    <div class="panel-heading">
                        <h4>批次管理</h4>
                    </div>
                    <div class="panel-body">
                        <div class="row" style="margin-bottom: 15px;">
                            <div class="col-sm-12">
                                <button class="btn btn-success" onclick="window.app.batchManager.showCreateBatchModal()">
                                    <span class="glyphicon glyphicon-plus"></span> 创建批次
                                </button>
                            </div>
                        </div>
                        <div id="batch-cards-container" class="row"></div>
                        <div id="batch-pagination" class="text-center"></div>
                    </div>
                </div>
            </div>

            <!-- Create/Edit Batch Modal -->
            <div class="modal fade" id="batch-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title" id="batch-modal-title">创建批次</h4>
                        </div>
                        <div class="modal-body">
                            <form id="batch-form">
                                <input type="hidden" id="batch-id">
                                <div class="form-group">
                                    <label for="batch-name">批次名称 *</label>
                                    <input type="text" class="form-control" id="batch-name" required>
                                </div>
                                <div class="form-group">
                                    <label for="batch-description">批次描述</label>
                                    <textarea class="form-control" id="batch-description" rows="3"></textarea>
                                </div>
                                <div id="batch-modal-assign-section" style="display:none;">
                                    <hr>
                                    <div class="form-group">
                                        <label>每人单次最多可认领任务数：</label>
                                        <input type="number" id="batch-modal-claim-limit" min="1" class="form-control" placeholder="例如: 20（默认 10）">
                                    </div>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="window.app.batchManager.saveBatch()">保存</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Allocate Users Modal -->
            <div class="modal fade" id="batch-alloc-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <button type="button" class="close" data-dismiss="modal">&times;</button>
                            <h4 class="modal-title">分配用户</h4>
                        </div>
                        <div class="modal-body">
                            <div id="batch-alloc-add-panel" style="display:none; border:1px solid #5cb85c; padding:8px; border-radius:4px; background:#f9fff9;">
                                <div id="batch-alloc-add-list" style="max-height:300px; overflow-y:auto;"></div>
                                <div style="margin-top:6px; text-align:right;">
                                    <button type="button" class="btn btn-xs btn-success" onclick="window.app.batchManager.confirmAllocAdd()">确定添加</button>
                                </div>
                            </div>
                            <div id="batch-alloc-delete-panel" style="display:none; border:1px solid #d9534f; padding:8px; border-radius:4px; background:#fff9f9;">
                                <div id="batch-alloc-delete-list" style="max-height:300px; overflow-y:auto;"></div>
                                <div style="margin-top:6px; text-align:right;">
                                    <button type="button" class="btn btn-xs btn-danger" style="margin-right:4px;" onclick="window.app.batchManager.deleteAllAllocUsers()">全部删除</button>
                                    <button type="button" class="btn btn-xs btn-danger" onclick="window.app.batchManager.confirmAllocDelete()">确定删除</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async show() {
        this.isVisible = true;
        this.container.style.display = 'block';
        await this.loadBatches();
    }

    hide() {
        this.isVisible = false;
        this.container.style.display = 'none';
    }

    async loadBatches() {
        try {
            const data = await api.getBatches(this.getToken(), {
                page: this.currentPage,
                page_size: this.pageSize,
                sort_by: this.sortBy,
                sort_order: this.sortOrder
            });
            this.batches = data.batches;
            this.totalPages = Math.ceil(data.total / this.pageSize);
            this.renderBatchCards();
            this.renderPagination();
        } catch (error) {
            console.error('Failed to load batches:', error);
            alert('加载批次失败');
        }
    }


    renderBatchCards() {
        const container = document.getElementById('batch-cards-container');
        if (!this.batches.length) {
            container.innerHTML = '<div class="col-sm-12"><p class="text-muted">暂无批次</p></div>';
            return;
        }

        container.innerHTML = this.batches.map(batch => `
            <div class="col-sm-6 col-md-4" style="margin-bottom: 20px;">
                <div class="panel panel-default">
                    <div class="panel-heading">
                        <h5 class="batch-card-title" style="margin: 0; text-align: center;">${this.escapeHtml(batch.name)}</h5>
                    </div>
                    <div class="panel-body">
                        <p class="text-muted batch-card-description" style="min-height: 40px;">${batch.description ? this.escapeHtml(batch.description) : '无描述'}</p>
                        <div style="margin-top: 10px;">
                            <span class="label label-default batch-card-stat">总数: ${batch.statistics.total}</span>
                            <span class="label label-warning batch-card-stat">待执行: ${batch.statistics.pending}</span>
                            <span class="label label-info batch-card-stat">进行中: ${batch.statistics.in_progress}</span>
                            <span class="label label-success batch-card-stat">已完成: ${batch.statistics.completed}</span>
                        </div>
                        <div style="margin-top: 8px;">
                            <span class="text-muted batch-card-assignees">已分配用户: ${batch.statistics.allocated_usernames && batch.statistics.allocated_usernames.length > 0 ? batch.statistics.allocated_usernames.join(', ') : '无'}</span>
                        </div>
                        <div style="margin-top: 10px;">
                            <span class="text-muted batch-card-assignees">已参与录制用户: ${batch.statistics.assigned_usernames && batch.statistics.assigned_usernames.length > 0 ? batch.statistics.assigned_usernames.join(', ') : '无'}</span>
                        </div>
                        <div class="batch-card-created-at" style="margin-top: 10px; color: #999;">
                            创建时间: ${new Date(batch.created_at).toLocaleString()}
                        </div>
                    </div>
                    <div class="panel-footer">
                        <button class="btn btn-xs btn-primary" onclick="window.app.batchManager.viewBatchDetail(${batch.id})">
                            <span class="glyphicon glyphicon-eye-open"></span> 查看任务
                        </button>
                        ${this.isAdmin() ? `
                        <button class="btn btn-xs btn-info" onclick="window.app.batchManager.showEditBatchModal(${batch.id})">
                            <span class="glyphicon glyphicon-edit"></span> 编辑
                        </button>
                        <button class="btn btn-xs btn-danger" onclick="window.app.batchManager.deleteBatch(${batch.id})">
                            <span class="glyphicon glyphicon-trash"></span> 删除
                        </button>
                        <button class="btn btn-xs btn-success" onclick="window.app.batchManager.showAllocModal(${batch.id}, 'add')">
                            <span class="glyphicon glyphicon-plus"></span> 添加用户
                        </button>
                        <button class="btn btn-xs btn-danger" onclick="window.app.batchManager.showAllocModal(${batch.id}, 'delete')">
                            <span class="glyphicon glyphicon-minus"></span> 删除用户
                        </button>
                        ` : ''}
                    </div>
                </div>
            </div>
        `).join('');
    }

    renderPagination() {
        const container = document.getElementById('batch-pagination');
        if (this.totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = '<ul class="pagination">';
        html += `<li class="${this.currentPage === 1 ? 'disabled' : ''}"><a href="#" onclick="window.app.batchManager.goToPage(${this.currentPage - 1}); return false;">&laquo;</a></li>`;

        for (let i = 1; i <= this.totalPages; i++) {
            if (i === 1 || i === this.totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                html += `<li class="${i === this.currentPage ? 'active' : ''}"><a href="#" onclick="window.app.batchManager.goToPage(${i}); return false;">${i}</a></li>`;
            } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                html += '<li class="disabled"><a>...</a></li>';
            }
        }

        html += `<li class="${this.currentPage === this.totalPages ? 'disabled' : ''}"><a href="#" onclick="window.app.batchManager.goToPage(${this.currentPage + 1}); return false;">&raquo;</a></li>`;
        html += '</ul>';
        container.innerHTML = html;
    }

    goToPage(page) {
        if (page < 1 || page > this.totalPages) return;
        this.currentPage = page;
        this.loadBatches();
    }

    // ========== Create/Edit Batch Modal ==========

    showCreateBatchModal() {
        document.getElementById('batch-modal-title').textContent = '创建批次';
        document.getElementById('batch-id').value = '';
        document.getElementById('batch-name').value = '';
        document.getElementById('batch-description').value = '';
        document.getElementById('batch-modal-assign-section').style.display = 'none';

        if (typeof $ !== 'undefined') {
            $('#batch-modal').modal('show');
        } else {
            const modal = document.getElementById('batch-modal');
            modal.style.display = 'block';
            modal.classList.add('in');
            document.body.classList.add('modal-open');
            const backdrop = document.createElement('div');
            backdrop.className = 'modal-backdrop fade in';
            document.body.appendChild(backdrop);
        }
    }

    async showEditBatchModal(batchId) {
        try {
            const batch = await api.getBatch(this.getToken(), batchId);
            document.getElementById('batch-modal-title').textContent = '编辑批次';
            document.getElementById('batch-id').value = batch.id;
            document.getElementById('batch-name').value = batch.name;
            document.getElementById('batch-description').value = batch.description || '';
            document.getElementById('batch-modal-claim-limit').value = batch.claim_limit_per_user != null ? batch.claim_limit_per_user : 10;
            document.getElementById('batch-modal-assign-section').style.display = 'block';
            $('#batch-modal').modal('show');
        } catch (error) {
            console.error('Failed to load batch:', error);
            alert('加载批次失败');
        }
    }

    async saveBatch() {
        const batchId = document.getElementById('batch-id').value;
        const name = document.getElementById('batch-name').value.trim();
        const description = document.getElementById('batch-description').value.trim();
        const claimLimitInput = parseInt(document.getElementById('batch-modal-claim-limit').value, 10);
        const claimLimitPerUser = Number.isInteger(claimLimitInput) && claimLimitInput > 0 ? claimLimitInput : 10;

        if (!name) {
            alert('请输入批次名称');
            return;
        }

        try {
            if (batchId) {
                await api.updateBatch(this.getToken(), batchId, { name, description, claim_limit_per_user: claimLimitPerUser });
            } else {
                await api.createBatch(this.getToken(), { name, description });
            }
            $('#batch-modal').modal('hide');
            await this.loadBatches();
            alert(batchId ? '批次更新成功' : '批次创建成功');
        } catch (error) {
            console.error('Failed to save batch:', error);
            alert('保存失败: ' + error.message);
        }
    }

    // ========== Allocate Users Modal ==========

    async showAllocModal(batchId, mode = 'add') {
        this._alloc = { batchId: batchId, allUsers: [], assignedIds: new Set(), addPage: 1, deletePage: 1 };
        document.getElementById('batch-alloc-add-panel').style.display = 'none';
        document.getElementById('batch-alloc-delete-panel').style.display = 'none';
        document.querySelector('#batch-alloc-modal .modal-title').textContent =
            mode === 'delete' ? '删除用户' : '添加用户';
        $('#batch-alloc-modal').modal('show');

        try {
            const [usersData, allocData] = await Promise.all([
                api.getUsers(this.getToken()),
                api.getBatchAllocations(this.getToken(), batchId)
            ]);
            this._alloc.allUsers = usersData;
            if (allocData && allocData.allocations) {
                for (const a of allocData.allocations) {
                    this._alloc.assignedIds.add(a.user_id);
                }
            }
        } catch (error) {
            console.error('Failed to load users:', error);
        }
        if (mode === 'delete') {
            this.showAllocDeletePanel();
        } else {
            this.showAllocAddPanel();
        }
    }

    showAllocAddPanel() {
        document.getElementById('batch-alloc-delete-panel').style.display = 'none';
        this._alloc.addPage = 1;
        this._allocRenderAddPage();
        document.getElementById('batch-alloc-add-panel').style.display = 'block';
    }

    _allocRenderAddPage() {
        const PAGE_SIZE = 10;
        const unassigned = this._alloc.allUsers.filter(u => !this._alloc.assignedIds.has(u.id));
        const el = document.getElementById('batch-alloc-add-list');
        if (!unassigned.length) {
            el.innerHTML = '<span class="text-muted">所有用户已分配</span>';
            return;
        }
        const totalPages = Math.ceil(unassigned.length / PAGE_SIZE);
        if (this._alloc.addPage > totalPages) this._alloc.addPage = totalPages;
        const page = this._alloc.addPage;
        const start = (page - 1) * PAGE_SIZE;
        const pageUsers = unassigned.slice(start, start + PAGE_SIZE);

        let html = `<table class="table table-condensed table-bordered" style="margin-bottom:4px; font-size:12px;">
            <thead><tr>
                <th style="width:28px;"><input type="checkbox" onclick="window.app.batchManager.selectAllAllocAdd(this)"></th>
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
                <button class="btn btn-xs btn-default" ${page <= 1 ? 'disabled' : ''} onclick="window.app.batchManager.allocAddPrev()">«</button>
                <button class="btn btn-xs btn-default" ${page >= totalPages ? 'disabled' : ''} onclick="window.app.batchManager.allocAddNext()">»</button>
            </div>
        </div>`;
        el.innerHTML = html;
    }

    allocAddPrev() {
        if (this._alloc.addPage > 1) { this._alloc.addPage--; this._allocRenderAddPage(); }
    }

    allocAddNext() {
        this._alloc.addPage++;
        this._allocRenderAddPage();
    }

    selectAllAllocAdd(cb) {
        const checked = cb ? cb.checked : true;
        document.querySelectorAll('#batch-alloc-add-list input[type=checkbox]').forEach(c => c.checked = checked);
    }

    hideAllocAddPanel() {
        document.getElementById('batch-alloc-add-panel').style.display = 'none';
    }

    async confirmAllocAdd() {
        const checked = document.querySelectorAll('#batch-alloc-add-list tbody input:checked');
        if (!checked.length) { alert('请选择要添加的用户'); return; }
        if (!confirm(`确定添加选中的 ${checked.length} 位用户吗？`)) return;
        checked.forEach(cb => this._alloc.assignedIds.add(parseInt(cb.value)));
        await this.saveAlloc();
    }

    showAllocDeletePanel() {
        document.getElementById('batch-alloc-add-panel').style.display = 'none';
        this._alloc.deletePage = 1;
        this._allocRenderDeletePage();
        document.getElementById('batch-alloc-delete-panel').style.display = 'block';
    }

    _allocRenderDeletePage() {
        const PAGE_SIZE = 10;
        const assigned = this._alloc.allUsers.filter(u => this._alloc.assignedIds.has(u.id));
        const el = document.getElementById('batch-alloc-delete-list');
        if (!assigned.length) {
            el.innerHTML = '<span class="text-muted">暂无已分配用户</span>';
            return;
        }
        const totalPages = Math.ceil(assigned.length / PAGE_SIZE);
        if (this._alloc.deletePage > totalPages) this._alloc.deletePage = totalPages;
        const page = this._alloc.deletePage;
        const start = (page - 1) * PAGE_SIZE;
        const pageUsers = assigned.slice(start, start + PAGE_SIZE);

        let html = `<table class="table table-condensed table-bordered" style="margin-bottom:4px; font-size:12px;">
            <thead><tr>
                <th style="width:28px;"><input type="checkbox" onclick="window.app.batchManager.selectAllAllocDelete(this)"></th>
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
                <button class="btn btn-xs btn-default" ${page <= 1 ? 'disabled' : ''} onclick="window.app.batchManager.allocDeletePrev()">«</button>
                <button class="btn btn-xs btn-default" ${page >= totalPages ? 'disabled' : ''} onclick="window.app.batchManager.allocDeleteNext()">»</button>
            </div>
        </div>`;
        el.innerHTML = html;
    }

    allocDeletePrev() {
        if (this._alloc.deletePage > 1) { this._alloc.deletePage--; this._allocRenderDeletePage(); }
    }

    allocDeleteNext() {
        this._alloc.deletePage++;
        this._allocRenderDeletePage();
    }

    selectAllAllocDelete(cb) {
        const checked = cb ? cb.checked : true;
        document.querySelectorAll('#batch-alloc-delete-list input[type=checkbox]').forEach(c => c.checked = checked);
    }

    hideAllocDeletePanel() {
        document.getElementById('batch-alloc-delete-panel').style.display = 'none';
    }

    async confirmAllocDelete() {
        const checked = document.querySelectorAll('#batch-alloc-delete-list tbody input:checked');
        if (!checked.length) { alert('请选择要删除的用户'); return; }
        if (!confirm(`确定删除选中的 ${checked.length} 位用户吗？`)) return;
        checked.forEach(cb => this._alloc.assignedIds.delete(parseInt(cb.value)));
        await this.saveAlloc();
    }

    async deleteAllAllocUsers() {
        if (!confirm('确定删除所有已分配用户吗？')) return;
        this._alloc.assignedIds.clear();
        await this.saveAlloc();
    }

    async saveAlloc() {
        const userIds = Array.from(this._alloc.assignedIds);

        try {
            await api.saveBatchAllocations(this.getToken(), this._alloc.batchId, userIds);
            $('#batch-alloc-modal').modal('hide');
            await this.loadBatches();
            alert('用户分配已保存');
        } catch (error) {
            console.error('Failed to save allocation:', error);
            alert('保存分配失败: ' + error.message);
        }
    }

    // ========== Other ==========

    async deleteBatch(batchId) {
        if (!confirm('确定要删除此批次吗？批次内的所有任务也将被删除，此操作不可恢复！')) return;

        try {
            await api.deleteBatch(this.getToken(), batchId);
            await this.loadBatches();
            alert('批次删除成功');
        } catch (error) {
            alert('删除失败: ' + error.message);
        }
    }

    viewBatchDetail(batchId) {
        this.hide();
        window.app.taskManager.batchMode = true;
        window.app.taskManager.show();
        window.app.taskManager.showBatchDetail(batchId);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
