class DeletedNodesDialog{
    constructor() {
        this.deletedNodesSelected = new Set();
        this.deletedNodeItems = [];
        this.overlay = null;
    }

    /**
     * 显示被删除节点的弹窗界面
     */
    async open() {
        try {
            const deletedNodes = await api.getDeletedNodes();

            // 防止重复创建
            const existing = document.getElementById('deleted-nodes-overlay');
            if (existing) existing.remove();

            // 始终创建并显示对话框，即使没有删除的节点
            this.createModal();
            this.initDeletedNodesGrid(deletedNodes || []);
            this.bindDeletedNodesEvents();

        } catch (err) {
            console.error('Failed to load deleted nodes:', err);
            alert('加载已删除节点失败。');
        }
    }

    createModal() {
        const overlay = document.createElement('div');
        overlay.id = 'deleted-nodes-overlay';
        overlay.className = 'deleted-nodes-overlay';

        overlay.innerHTML = `
            <div id="deleted-nodes-modal" class="deleted-nodes-modal">
                <div class="deleted-nodes-header">
                    <h3>已删除节点</h3>
                    <span id="deleted-nodes-close" class="deleted-nodes-close">&times;</span>
                </div>

                <div class="deleted-nodes-content">
                    <div id="deleted-nodes-grid" class="deleted-nodes-grid"></div>
                </div>

                <div class="deleted-nodes-footer">
                    <span id="deleted-nodes-selected-count">已选择 0 个</span>
                    <button id="deleted-nodes-select-all"
                            class="btn btn-xs btn-default"
                            title="全选 / 取消全选">
                        全选
                    </button>
                    <button id="deleted-nodes-restore-btn"
                            class="btn btn-success"
                            disabled>
                        恢复所选
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
        this.overlay = overlay;
        this.deletedNodesSelected.clear();
    }

    /**
     * 初始化删除节点展示网格
     *  - 为每个节点创建 grid item，包括图片和选中标记
     *  - 点击节点可切换选中状态
     *  - 如果没有删除节点，显示空状态提示
     */
    initDeletedNodesGrid(deletedNodes) {
        const grid = document.getElementById('deleted-nodes-grid');
        grid.innerHTML = '';

        // 如果没有删除的节点，显示空状态提示
        if (!deletedNodes || deletedNodes.length === 0) {
            grid.innerHTML = `
                <div class="deleted-nodes-empty-state">
                    <div class="empty-state-icon">📭</div>
                    <div class="empty-state-text">没有可恢复的已删除节点</div>
                    <div class="empty-state-subtext">从图中删除的节点会显示在这里</div>
                </div>
            `;
            this.deletedNodeItems = [];
            return;
        }

        deletedNodes.forEach(node => {
            const item = document.createElement('div');
            item.className = 'deleted-node-item';
            item.dataset.state = node.state_str;

            item.innerHTML = `
                <div class="deleted-node-image-wrapper">
                    <img src="${node.image}" loading="lazy" />
                    <div class="deleted-node-check">✓</div>
                </div>
            `;

            item.onclick = () => this.toggleDeletedNode(item);
            grid.appendChild(item);
        });

        this.deletedNodeItems = Array.from(
            this.overlay.querySelectorAll('.deleted-node-item')
        );
    }

    /**
     * 切换节点选中状态
     * - 如果已选中则取消选中，否则选中
     * - 更新 footer 和全选按钮状态
     */
    toggleDeletedNode(item) {
        const state = item.dataset.state;
        const check = item.querySelector('.deleted-node-check');

        if (this.deletedNodesSelected.has(state)) {
            this.deletedNodesSelected.delete(state);
            item.classList.remove('selected');
            check.style.opacity = '0';
        } else {
            this.deletedNodesSelected.add(state);
            item.classList.add('selected');
            check.style.opacity = '1';
        }

        this.updateDeletedNodesFooter();
        this.syncSelectAllButton();
    }

    /**
     * 更新 footer 区域显示
     * - 更新选中节点数量
     * - 根据是否有选中节点启用/禁用恢复按钮
     */
    updateDeletedNodesFooter() {
        const countSpan = document.getElementById('deleted-nodes-selected-count');
        const restoreBtn = document.getElementById('deleted-nodes-restore-btn');

        countSpan.textContent = `已选择 ${this.deletedNodesSelected.size} 个`;
        restoreBtn.disabled = this.deletedNodesSelected.size === 0;
    }

    /**
     * 同步全选按钮显示
     */
    syncSelectAllButton() {
        const btn = document.getElementById('deleted-nodes-select-all');
        if (!btn || !this.deletedNodeItems) return;

        const total = this.deletedNodeItems.length;
        const selected = this.deletedNodesSelected.size;
        btn.textContent = selected === total ? '取消全选' : '全选';
    }

    /**
     * 绑定删除节点弹窗的事件
     * - 关闭弹窗（点击 X 或 overlay 或 ESC）
     * - 批量恢复按钮点击事件
     * - 全选/取消全选按钮点击事件
     */
    bindDeletedNodesEvents() {
        const overlay = this.overlay;
        const closeBtn = document.getElementById('deleted-nodes-close');
        const restoreBtn = document.getElementById('deleted-nodes-restore-btn');
        const selectAllBtn = document.getElementById('deleted-nodes-select-all');

        const cleanup = () => {
            overlay?.remove();
            document.removeEventListener('keydown', onEsc);
        };

        const onEsc = (e) => {
            if (e.key === 'Escape') cleanup();
        };

        closeBtn.onclick = cleanup;

        overlay.onclick = (e) => {
            if (e.target === overlay) cleanup();
        };

        document.addEventListener('keydown', onEsc);

        restoreBtn.onclick = async () => {
            const list = Array.from(this.deletedNodesSelected);
            if (!list.length) return;
            const count = list.length;
            
            const restoreMessage = `
                <p>确认恢复 ${count} 个节点吗？</p>
                <div class="alert alert-info">
                    <strong>提示：</strong>恢复节点后会立即更新 UTG 视图。
                </div>
            `;
            const message = `已成功恢复 ${count} 个节点。`;

            // 先关闭显示界面再显示弹窗
            cleanup();
            return new Promise((resolve) => {
                window.confirmDialog.show(restoreMessage, async (confirmed) => {
                    if (!confirmed) {
                        resolve(); // 用户取消
                        return;
                    }

                    try {
                        await api.batchRestoreNodes(list);
                        await window.app.utgViewer.loadUTG();

                        if (window.showSuccess) {
                            window.showSuccess(message);
                        } else {
                            alert(message);
                        }
                        resolve(); 

                    } catch (err) {
                        console.error('Restore error:', err);
                        window.toast.show('恢复节点失败。', 'error');
                        resolve(false); // 操作失败
                    }
                });
            });
        };

        selectAllBtn.onclick = () => {
            // 当前是否有选中
            const anySelected = this.deletedNodesSelected.size > 0; 

            if (anySelected) {
                // 如果有选中 → 取消所有
                this.deletedNodeItems.forEach(item => {
                    const state = item.dataset.state;
                    const check = item.querySelector('.deleted-node-check');
                    this.deletedNodesSelected.delete(state);
                    item.classList.remove('selected');
                    check.style.opacity = '0';
                });
            } else {
                // 如果没有选中 → 全部选中
                this.deletedNodeItems.forEach(item => {
                    const state = item.dataset.state;
                    const check = item.querySelector('.deleted-node-check');
                    this.deletedNodesSelected.add(state);
                    item.classList.add('selected');
                    check.style.opacity = '1';
                });
            }

            this.updateDeletedNodesFooter();
            this.syncSelectAllButton();
            
        };
    }
}
