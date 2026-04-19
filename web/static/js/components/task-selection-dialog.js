/**
 * TaskSelectionDialog
 * 集成分页弹窗与任务/录制数据选择的通用组件
 */
(function(window) {
    var TEXT_NODE = window.Node ? window.Node.TEXT_NODE : 3;
    var DEFAULT_SORT = { columnIndex: 2, order: 'desc' };

    function createDefaultState(selectedValue) {
        return {
            page: 1,
            total: 0,
            items: [],
            baseItems: [],
            selectedValue: selectedValue === undefined ? null : selectedValue,
            selectedItem: null,
            selectedIndex: -1,
            loading: false,
            confirmLoading: false,
            sortKey: null,
            sortOrder: null,
            sortColumnIndex: null,
            keyword: '',
            filters: {}
        };
    }

    function TaskSelectionDialog(options) {
        options = options || {};
        this.modalId = options.modalId || 'task-selection-dialog';
        this.pageSize = options.pageSize || 50;
        this.state = createDefaultState(null);
        this.loadRequestId = 0;
        this.initModal();
    }

    TaskSelectionDialog.prototype.initModal = function() {
        if (document.getElementById(this.modalId)) {
            document.getElementById(this.modalId).remove();
        }

        var template = [
            '<div class="modal fade selection-dialog" id="' + this.modalId + '" tabindex="-1" role="dialog" aria-hidden="true">',
            '  <div class="modal-dialog modal-lg selection-dialog__dialog">',
            '    <div class="modal-content selection-dialog__content">',
            '      <div class="modal-header selection-dialog__header">',
            '        <button type="button" class="close" data-dismiss="modal"><span>&times;</span></button>',
            '        <h4 class="modal-title selection-dialog__title">选择</h4>',
            '      </div>',
            '      <div class="modal-body selection-dialog__body">',
            '        <div class="selection-dialog__search-bar" style="margin-bottom: 10px; display: flex; align-items: center; gap: 6px;">',
            '          <div class="input-group" style="flex: 1;">',
            '            <input type="text" class="form-control selection-dialog__search-input" placeholder="搜索...">',
            '            <span class="input-group-btn">',
            '              <button type="button" class="btn btn-default selection-dialog__search-btn">',
            '                <span class="glyphicon glyphicon-search"></span>',
            '              </button>',
            '            </span>',
            '          </div>',
            '          <div style="position: relative;">',
            '            <button type="button" class="btn btn-default selection-dialog__filter-btn">',
            '              <span class="glyphicon glyphicon-filter"></span>',
            '              <span class="selection-dialog__filter-badge badge" style="display:none; margin-left:4px;"></span>',
            '            </button>',
            '            <div class="selection-dialog__filter-panel" style="display:none; position:absolute; right:0; top:100%; z-index:1060; background:#fff; border:1px solid #ddd; border-radius:4px; padding:12px; min-width:260px; box-shadow:0 2px 8px rgba(0,0,0,0.15); margin-top:4px;">',
            '            </div>',
            '          </div>',
            '        </div>',
            '        <div class="selection-dialog__table-wrapper">',
            '          <table class="table table-hover table-condensed selection-dialog__table">',
            '            <thead></thead>',
            '            <tbody></tbody>',
            '          </table>',
            '        </div>',
            '        <div class="selection-dialog__empty alert alert-info" style="display: none;"></div>',
            '        <div class="selection-dialog__loading" style="display: none;">',
            '          <span class="glyphicon glyphicon-time"></span>',
            '          <span style="margin-left: 6px;">加载中...</span>',
            '        </div>',
            '      </div>',
            '      <div class="modal-footer selection-dialog__footer">',
            '        <div class="selection-dialog__pagination"></div>',
            '        <div class="selection-dialog__actions">',
            '          <button type="button" class="btn btn-default" data-dismiss="modal">取消</button>',
            '          <button type="button" class="btn btn-primary selection-dialog__confirm" disabled>确定</button>',
            '        </div>',
            '      </div>',
            '    </div>',
            '  </div>',
            '</div>'
        ].join('');

        document.body.insertAdjacentHTML('beforeend', template);

        this.modalElement = document.getElementById(this.modalId);
        this.$modal = window.$ ? window.$(this.modalElement) : null;
        this.titleElement = this.modalElement.querySelector('.selection-dialog__title');
        this.thead = this.modalElement.querySelector('thead');
        this.tbody = this.modalElement.querySelector('tbody');
        this.emptyState = this.modalElement.querySelector('.selection-dialog__empty');
        this.loadingState = this.modalElement.querySelector('.selection-dialog__loading');
        this.pagination = this.modalElement.querySelector('.selection-dialog__pagination');
        this.confirmBtn = this.modalElement.querySelector('.selection-dialog__confirm');
        this.searchInput = this.modalElement.querySelector('.selection-dialog__search-input');
        this.searchBtn = this.modalElement.querySelector('.selection-dialog__search-btn');

        var self = this;
        if (this.confirmBtn) {
            this.confirmBtn.addEventListener('click', function() {
                self.confirmSelection();
            });
        }

        if (this.searchBtn) {
            this.searchBtn.addEventListener('click', function() {
                self.handleSearch();
            });
        }

        if (this.searchInput) {
            this.searchInput.addEventListener('keydown', function(event) {
                if (event.key === 'Enter') self.handleSearch();
            });
        }

        var filterBtn = this.modalElement.querySelector('.selection-dialog__filter-btn');
        if (filterBtn) {
            filterBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                self.toggleFilterPanel();
            });
        }
        // 点击模态框其他区域关闭筛选面板
        var modalContent = this.modalElement.querySelector('.modal-content');
        if (modalContent) {
            modalContent.addEventListener('click', function(e) {
                var panel = self.modalElement.querySelector('.selection-dialog__filter-panel');
                if (panel && panel.style.display !== 'none' && !panel.contains(e.target) && !e.target.closest('.selection-dialog__filter-btn')) {
                    panel.style.display = 'none';
                }
            });
        }

        if (this.tbody) {
            this.tbody.addEventListener('click', function(event) {
                var row = self.findRowElement(event.target);
                if (!row) return;
                var index = parseInt(row.getAttribute('data-index'), 10);
                self.setActiveRow(index);
            });
        }

        if (this.pagination) {
            this.pagination.addEventListener('click', function(event) {
                var button = event.target.closest('[data-page]');
                if (!button || button.classList.contains('disabled')) return;
                var page = parseInt(button.getAttribute('data-page'), 10);
                if (!isNaN(page)) {
                    self.loadPage(page);
                }
            });
        }

        if (this.thead) {
            this.thead.addEventListener('click', function(event) {
                var header = self.findHeaderElement(event.target);
                if (!header) return;
                var columnIndex = parseInt(header.getAttribute('data-column-index'), 10);
                if (isNaN(columnIndex)) return;
                self.toggleSort(columnIndex);
            });
        }
    };

    TaskSelectionDialog.prototype.open = function(config) {
        this.config = Object.assign({
            title: '选择',
            confirmText: '确定',
            emptyText: '暂无数据',
            selectedValue: null,
            fetchData: null,
            columns: [],
            filterFields: [],
            pageSize: this.pageSize
        }, config || {});

        if (typeof this.config.fetchData !== 'function') {
            throw new Error('TaskSelectionDialog: fetchData 必须是函数');
        }

        this.pageSize = this.config.pageSize || this.pageSize;
        this.state = createDefaultState(this.config.selectedValue == null ? null : this.config.selectedValue);

        // 加载缓存的筛选条件
        this.state.filters = this.loadCachedFilters();
        this._filterCache = {};
        var filterPanel = this.modalElement.querySelector('.selection-dialog__filter-panel');
        if (filterPanel) filterPanel.innerHTML = '';
        this.updateFilterBadge();

        // 根据权限过滤 adminOnly 字段
        var filterBtnEl = this.modalElement.querySelector('.selection-dialog__filter-btn');
        if (filterBtnEl) filterBtnEl.style.display = 'none';
        if (this.config.filterFields && this.config.filterFields.length) {
            var self = this;
            var token = localStorage.getItem('auth_token');
            api.getCurrentUser(token).then(function(user) {
                if (!user || !user.is_superuser) {
                    self.config.filterFields = self.config.filterFields.filter(function(f) {
                        return !f.adminOnly;
                    });
                }
                if (filterBtnEl) {
                    filterBtnEl.style.display = self.config.filterFields.length ? '' : 'none';
                }
            }).catch(function() {
                // 获取失败时保守处理：移除 adminOnly 字段
                self.config.filterFields = self.config.filterFields.filter(function(f) {
                    return !f.adminOnly;
                });
                if (filterBtnEl) {
                    filterBtnEl.style.display = self.config.filterFields.length ? '' : 'none';
                }
            });
        }
        if (filterBtnEl) {
            filterBtnEl.style.display = (this.config.filterFields && this.config.filterFields.length) ? '' : 'none';
        }

        // 重置搜索框
        if (this.searchInput) {
            this.searchInput.value = '';
            this.searchInput.placeholder = this.config.searchPlaceholder || '搜索...';
        }

        if (this.config.defaultSort && typeof this.config.defaultSort.columnIndex === 'number') {
            this.setSortState(this.config.defaultSort.columnIndex, this.config.defaultSort.order);
        }

        if (this.titleElement) {
            this.titleElement.textContent = this.config.title || '选择';
        }
        if (this.confirmBtn) {
            this.confirmBtn.textContent = this.config.confirmText || '确定';
            this.confirmBtn.disabled = true;
        }

        this.renderHeader();
        this.renderRows();
        this.renderPagination();
        this.toggleEmptyState(false);
        this.toggleLoading(false);

        if (this.$modal) {
            this.$modal.modal('show');
        } else {
            this.modalElement.style.display = 'block';
            this.modalElement.classList.add('in');
        }

        this.loadPage(1);
    };

    TaskSelectionDialog.prototype.close = function() {
        if (this.$modal) {
            this.$modal.modal('hide');
        } else if (this.modalElement) {
            this.modalElement.style.display = 'none';
            this.modalElement.classList.remove('in');
        }
    };

    TaskSelectionDialog.prototype.renderHeader = function() {
        if (!this.thead) return;
        var self = this;
        var columns = this.config.columns || [];
        var headerHtml = columns.map(function(col, index) {
            var attrs = [];
            if (col.width) attrs.push('style="width:' + col.width + ';"');
            attrs.push('data-column-index="' + index + '"');
            var classes = [];
            if (col.sortable) {
                classes.push('selection-dialog__th--sortable');
                if (self.state.sortColumnIndex === index && self.state.sortOrder) {
                    classes.push('sorted-' + self.state.sortOrder);
                }
            }
            if (classes.length) attrs.push('class="' + classes.join(' ') + '"');
            var indicator = col.sortable ? '<span class="selection-dialog__sort-indicator">' + self.getSortIndicator(index) + '</span>' : '';
            return '<th ' + attrs.join(' ') + '>' + (col.label || '') + indicator + '</th>';
        }).join('');
        this.thead.innerHTML = '<tr>' + headerHtml + '</tr>';
    };

    TaskSelectionDialog.prototype.renderRows = function() {
        if (!this.tbody) return;
        var items = this.state.items || [];
        if (!items.length) {
            this.tbody.innerHTML = '';
            this.resetSelectedRow();
            this.toggleEmptyState(!this.state.loading);
            this.updateConfirmState();
            return;
        }

        var self = this;
        var columns = this.config.columns || [];
        var rows = items.map(function(item, index) {
            var cells = columns.map(function(col) {
                if (typeof col.render === 'function') return '<td>' + col.render(item, index) + '</td>';
                var value = item[col.key];
                return '<td>' + (value === undefined ? '' : value) + '</td>';
            }).join('');
            var isActive = index === self.state.selectedIndex;
            return '<tr class="selection-dialog__row' + (isActive ? ' active' : '') + '" data-index="' + index + '">' + cells + '</tr>';
        }).join('');

        this.tbody.innerHTML = rows;
        this.toggleEmptyState(false);
        this.updateConfirmState();
    };

    TaskSelectionDialog.prototype.toggleEmptyState = function(show) {
        if (!this.emptyState) return;
        this.emptyState.style.display = show ? 'block' : 'none';
        if (show) this.emptyState.textContent = this.config.emptyText || '暂无数据';
    };

    TaskSelectionDialog.prototype.toggleLoading = function(show) {
        if (!this.loadingState) return;
        this.loadingState.style.display = show ? 'flex' : 'none';
    };

    TaskSelectionDialog.prototype.renderPagination = function() {
        if (!this.pagination) return;
        var totalPages = this.getTotalPages();
        if (totalPages <= 1) {
            this.pagination.innerHTML = '';
            return;
        }
        var buttons = [];
        var currentPage = this.state.page;
        buttons.push(this.createPageButton('上一页', currentPage - 1, currentPage === 1));
        var pageList = this.buildPageList(totalPages, currentPage);
        for (var i = 0; i < pageList.length; i++) {
            var item = pageList[i];
            if (item === '...') buttons.push('<span class="selection-dialog__ellipsis">…</span>');
            else buttons.push(this.createPageButton(item, item, currentPage === item));
        }
        buttons.push(this.createPageButton('下一页', currentPage + 1, currentPage === totalPages));
        var info = '<span class="selection-dialog__page-info">共 ' + this.state.total + ' 条 · 第 ' + currentPage + '/' + totalPages + ' 页</span>';

        // 页面跳转控件
        var self = this;
        var jumpId = this.modalId + '-page-jump';
        var jumpHtml = '<span style="margin-left: 8px; display: inline-flex; align-items: center; gap: 4px;">' +
            '<input type="number" id="' + jumpId + '" class="form-control input-sm" style="width: 55px; display: inline-block;" min="1" max="' + totalPages + '" placeholder="页码">' +
            '<button type="button" class="btn btn-sm btn-default selection-dialog__jump-btn" data-jump-id="' + jumpId + '" data-total-pages="' + totalPages + '">跳转</button>' +
            '</span>';

        this.pagination.innerHTML = buttons.join('') + info + jumpHtml;

        // 绑定跳转按钮事件（每次渲染后重新绑定）
        var jumpBtn = this.pagination.querySelector('.selection-dialog__jump-btn');
        if (jumpBtn) {
            jumpBtn.addEventListener('click', function() {
                self.jumpToPage();
            });
        }
        var jumpInput = document.getElementById(jumpId);
        if (jumpInput) {
            jumpInput.addEventListener('keydown', function(event) {
                if (event.key === 'Enter') self.jumpToPage();
            });
        }
    };

    TaskSelectionDialog.prototype.createPageButton = function(label, page, disabled) {
        var classes = ['btn', 'btn-default', 'btn-sm', 'selection-dialog__page-btn'];
        if (disabled) classes.push('disabled');
        return '<button type="button" class="' + classes.join(' ') + '" data-page="' + page + '">' + label + '</button>';
    };

    TaskSelectionDialog.prototype.buildPageList = function(totalPages, currentPage) {
        var pages = [];
        var maxButtons = 5;
        var start = Math.max(1, currentPage - 2);
        var end = Math.min(totalPages, start + maxButtons - 1);
        if (end - start < maxButtons - 1) start = Math.max(1, end - maxButtons + 1);
        if (start > 1) {
            pages.push(1);
            if (start > 2) pages.push('...');
        }
        for (var p = start; p <= end; p++) {
            pages.push(p);
        }
        if (end < totalPages) {
            if (end < totalPages - 1) pages.push('...');
            pages.push(totalPages);
        }
        return pages;
    };

    TaskSelectionDialog.prototype.loadPage = async function(page) {
        if (!this.config || typeof this.config.fetchData !== 'function') {
            return;
        }

        var requestId = ++this.loadRequestId;
        this.state.loading = true;
        this.toggleLoading(true);
        try {
            var sortOptions = this.useServerSorting() ? this.resolveSortOptions() : null;
            var result = await this.config.fetchData(page, this.pageSize, sortOptions);
            if (!this.isLatestRequest(requestId)) return;
            this.applyPageResult(page, result);
        } catch (error) {
            if (!this.isLatestRequest(requestId)) return;
            console.error('TaskSelectionDialog: 加载数据失败', error);
            this.applyPageResult(page, { items: [], total: 0 });
        } finally {
            if (!this.isLatestRequest(requestId)) return;
            this.state.loading = false;
            this.toggleLoading(false);
        }
    };

    TaskSelectionDialog.prototype.isLatestRequest = function(requestId) {
        return requestId === this.loadRequestId;
    };

    TaskSelectionDialog.prototype.applyPageResult = function(page, result) {
        this.state.page = page;
        var fetchedItems = (result && result.items) || [];
        this.state.baseItems = fetchedItems.slice();
        this.state.total = result && typeof result.total === 'number' ? result.total : fetchedItems.length;
        if (this.useServerSorting()) {
            this.state.items = this.state.baseItems.slice();
            this.syncSelectedItem();
        } else {
            this.applySorting();
        }
        this.renderRows();
        this.renderPagination();
    };

    TaskSelectionDialog.prototype.getTotalPages = function() {
        if (!this.state.total) return 0;
        return Math.ceil(this.state.total / this.pageSize);
    };

    TaskSelectionDialog.prototype.getRowKey = function(item) {
        if (!item || !this.config) return null;
        if (typeof this.config.rowKey === 'function') return this.config.rowKey(item);
        if ('id' in item) return item.id;
        if ('directory_name' in item) return item.directory_name;
        return JSON.stringify(item);
    };

    TaskSelectionDialog.prototype.resetSelectedRow = function() {
        this.state.selectedItem = null;
        this.state.selectedIndex = -1;
    };

    TaskSelectionDialog.prototype.setActiveRow = function(index) {
        var item = this.state.items[index];
        if (!item) return;
        if (this.state.selectedIndex === index && this.state.selectedItem === item) return;

        var previousIndex = this.state.selectedIndex;
        this.state.selectedValue = this.getRowKey(item);
        this.state.selectedItem = item;
        this.state.selectedIndex = index;
        this.updateActiveRowClass(previousIndex, index);
        this.updateConfirmState();
    };

    TaskSelectionDialog.prototype.updateActiveRowClass = function(previousIndex, nextIndex) {
        if (!this.tbody || previousIndex === nextIndex) return;
        if (previousIndex > -1) {
            var previousRow = this.tbody.querySelector('tr[data-index="' + previousIndex + '"]');
            if (previousRow) previousRow.classList.remove('active');
        }
        if (nextIndex > -1) {
            var nextRow = this.tbody.querySelector('tr[data-index="' + nextIndex + '"]');
            if (nextRow) nextRow.classList.add('active');
        }
    };

    TaskSelectionDialog.prototype.updateConfirmState = function() {
        if (!this.confirmBtn) return;
        this.confirmBtn.disabled = this.shouldDisableConfirm();
    };

    TaskSelectionDialog.prototype.shouldDisableConfirm = function() {
        return !this.state.selectedItem || this.state.confirmLoading;
    };

    TaskSelectionDialog.prototype.setConfirmLoading = function(loading) {
        this.state.confirmLoading = loading;
        if (this.confirmBtn) {
            this.confirmBtn.disabled = this.shouldDisableConfirm();
            this.confirmBtn.innerHTML = loading ? '<span class="glyphicon glyphicon-time"></span> 处理中...' : (this.config.confirmText || '确定');
        }
    };

    TaskSelectionDialog.prototype.confirmSelection = function() {
        if (!this.config || !this.state.selectedItem) {
            return;
        }
        if (typeof this.config.onConfirm !== 'function') {
            this.close();
            return;
        }
        try {
            var result = this.config.onConfirm(this.state.selectedItem);
            if (result && typeof result.then === 'function') {
                var self = this;
                this.setConfirmLoading(true);
                result.then(function(shouldClose) {
                    if (shouldClose !== false) self.close();
                }).catch(function(err) {
                    console.error('TaskSelectionDialog: confirm handler rejected', err);
                }).finally(function() {
                    self.setConfirmLoading(false);
                });
            } else if (result !== false) {
                this.close();
            }
        } catch (error) {
            console.error('TaskSelectionDialog: confirm handler error', error);
            this.setConfirmLoading(false);
        }
    };

    TaskSelectionDialog.prototype.toggleSort = function(columnIndex) {
        var currentOrder = this.state.sortColumnIndex === columnIndex ? this.state.sortOrder : null;
        var nextOrder = !currentOrder ? 'asc' : (currentOrder === 'asc' ? 'desc' : null);
        this.setSortState(nextOrder ? columnIndex : null, nextOrder);

        this.renderHeader();
        if (this.useServerSorting()) {
            this.loadPage(1);
            return;
        }
        this.applySorting();
        this.renderRows();
    };

    TaskSelectionDialog.prototype.resolveSortKey = function(column, columnIndex) {
        return column.sortKey || column.key || ('col_' + columnIndex);
    };

    TaskSelectionDialog.prototype.clearSortState = function() {
        this.state.sortColumnIndex = null;
        this.state.sortOrder = null;
        this.state.sortKey = null;
    };

    TaskSelectionDialog.prototype.setSortState = function(columnIndex, order) {
        if (columnIndex === null || columnIndex === undefined || !order) {
            this.clearSortState();
            return;
        }
        var columns = this.config && this.config.columns ? this.config.columns : [];
        var column = columns[columnIndex];
        if (!column || !column.sortable) {
            this.clearSortState();
            return;
        }
        this.state.sortColumnIndex = columnIndex;
        this.state.sortOrder = order === 'asc' ? 'asc' : 'desc';
        this.state.sortKey = this.resolveSortKey(column, columnIndex);
    };

    TaskSelectionDialog.prototype.useServerSorting = function() {
        return !!(this.config && this.config.serverSorting);
    };

    TaskSelectionDialog.prototype.resolveSortOptions = function() {
        if (!this.state.sortOrder || this.state.sortColumnIndex === null || this.state.sortColumnIndex === undefined) {
            return null;
        }
        var columns = this.config && this.config.columns ? this.config.columns : [];
        var column = columns[this.state.sortColumnIndex];
        if (!column) return null;

        var sortBy = column.sortField || column.sortKey || column.key;
        if (!sortBy) return null;

        return {
            sortBy: sortBy,
            sortOrder: this.state.sortOrder
        };
    };

    TaskSelectionDialog.prototype.applySorting = function() {
        var items = this.state.baseItems ? this.state.baseItems.slice() : [];
        if (this.state.sortKey && this.state.sortOrder !== null && this.state.sortColumnIndex !== null) {
            var column = (this.config.columns || [])[this.state.sortColumnIndex];
            var self = this;
            var orderFactor = this.state.sortOrder === 'asc' ? 1 : -1;
            items.sort(function(a, b) {
                if (column && typeof column.sorter === 'function') {
                    return column.sorter(a, b, orderFactor);
                }
                var va = self.getSortValue(a, column);
                var vb = self.getSortValue(b, column);
                return self.compareValues(va, vb, orderFactor);
            });
        }
        this.state.items = items;
        this.syncSelectedItem();
    };

    TaskSelectionDialog.prototype.getSortValue = function(item, column) {
        if (!column) return null;
        if (typeof column.sortValue === 'function') return column.sortValue(item);
        if (column.sortKey) return item[column.sortKey];
        if (column.key) return item[column.key];
        return null;
    };

    TaskSelectionDialog.prototype.compareValues = function(a, b, orderFactor) {
        if (a === b) return 0;
        if (a === undefined || a === null) return -1 * orderFactor;
        if (b === undefined || b === null) return 1 * orderFactor;
        if (typeof a === 'string') a = a.toLowerCase();
        if (typeof b === 'string') b = b.toLowerCase();
        if (a > b) return 1 * orderFactor;
        if (a < b) return -1 * orderFactor;
        return 0;
    };

    TaskSelectionDialog.prototype.syncSelectedItem = function() {
        if (this.state.selectedValue === null || this.state.selectedValue === undefined) {
            this.resetSelectedRow();
            return;
        }
        var items = this.state.items || [];
        for (var i = 0; i < items.length; i++) {
            if (this.getRowKey(items[i]) === this.state.selectedValue) {
                this.state.selectedItem = items[i];
                this.state.selectedIndex = i;
                return;
            }
        }
        this.resetSelectedRow();
    };

    TaskSelectionDialog.prototype.getSortIndicator = function(columnIndex) {
        if (this.state.sortColumnIndex !== columnIndex || !this.state.sortOrder) return '↕';
        return this.state.sortOrder === 'asc' ? '↑' : '↓';
    };

    TaskSelectionDialog.prototype.findClosestElement = function(target, selector, boundary) {
        if (!target) return null;
        if (target.nodeType === TEXT_NODE) target = target.parentElement;
        if (!target) return null;
        if (typeof target.closest === 'function') {
            var closest = target.closest(selector);
            if (closest && (!boundary || boundary.contains(closest))) return closest;
            return null;
        }
        while (target && target !== boundary) {
            if (this.matchesSelector(target, selector)) return target;
            target = target.parentNode;
        }
        return null;
    };

    TaskSelectionDialog.prototype.findRowElement = function(target) {
        return this.findClosestElement(target, 'tr[data-index]', this.tbody);
    };

    TaskSelectionDialog.prototype.findHeaderElement = function(target) {
        return this.findClosestElement(target, 'th[data-column-index]', this.thead);
    };

    TaskSelectionDialog.prototype.matchesSelector = function(element, selector) {
        if (!element || !selector) return false;
        var fn = element.matches || element.msMatchesSelector || element.webkitMatchesSelector;
        return fn ? fn.call(element, selector) : false;
    };

    TaskSelectionDialog.prototype.openSelector = function(params, options) {
        params = params || {};
        this.open({
            title: options.title,
            confirmText: options.confirmText,
            emptyText: options.emptyText,
            pageSize: this.pageSize,
            defaultSort: DEFAULT_SORT,
            serverSorting: !!options.serverSorting,
            selectedValue: options.selectedValue,
            cacheKey: options.cacheKey,
            fetchData: options.fetchData,
            rowKey: options.rowKey,
            columns: options.columns,
            filterFields: options.filterFields,
            onConfirm: function(item) {
                if (typeof params.onSelect === 'function') {
                    return params.onSelect(item);
                }
            }
        });
    };

    TaskSelectionDialog.prototype.openTaskSelector = function(params) {
        params = params || {};
        this.openSelector(params, this.buildTaskSelectorOptions(params));
    };

    TaskSelectionDialog.prototype.buildTaskSelectorOptions = function(params) {
        var self = this;
        return {
            title: '选择任务',
            confirmText: '确定',
            emptyText: '暂无任务',
            serverSorting: true,
            searchPlaceholder: '搜索任务描述...',
            selectedValue: params.selectedTask ? params.selectedTask.id : null,
            cacheKey: 'task-selection-filters',
            fetchData: function(page, size, sortOptions) {
                return self.fetchTasks(page, size, sortOptions);
            },
            rowKey: function(item) { return item.id; },
            columns: this.getTaskColumns(),
            filterFields: [
                { key: 'batch_id', label: '批次', type: 'select-async', valueKey: 'id', labelKey: 'name',
                  fetchItems: function(token) { return api.getBatches(token, {page_size:100}).then(function(d) { return d.batches||[]; }); } },
                { key: 'status', label: '状态', type: 'select-static',
                  options: [{value:'pending',label:'待执行'},{value:'in_progress',label:'进行中'},{value:'completed',label:'已完成'}] },
                { key: 'date_from', label: '创建时间（起）', type: 'date' },
                { key: 'date_to', label: '创建时间（止）', type: 'date' }
            ]
        };
    };

    TaskSelectionDialog.prototype.openRecordingSelector = function(params) {
        params = params || {};
        this.openSelector(params, this.buildRecordingSelectorOptions(params));
    };

    TaskSelectionDialog.prototype.buildRecordingSelectorOptions = function(params) {
        var self = this;
        var selectedValue = params.selectedRecording ? params.selectedRecording.directory_name : null;
        return {
            title: '选择录制数据',
            confirmText: '使用该录制数据',
            emptyText: '暂无录制数据',
            serverSorting: true,
            searchPlaceholder: '搜索录制数据或任务描述...',
            selectedValue: selectedValue,
            cacheKey: 'recording-selection-filters',
            fetchData: function(page, size, sortOptions) {
                return self.fetchRecordings(page, size, sortOptions);
            },
            rowKey: function(item) { return item.directory_name; },
            columns: this.getRecordingColumns(),
            filterFields: [
                { key: 'batch_id', label: '批次', type: 'select-async', valueKey: 'id', labelKey: 'name',
                  fetchItems: function(token) { return api.getBatches(token, {page_size:100}).then(function(d) { return d.batches||[]; }); } },
                { key: 'recorded_by', label: '录制人', type: 'select-async', adminOnly: true, valueKey: 'id', labelKey: 'username',
                  fetchItems: function(token) { return api.getUsers(token).then(function(u) { return Array.isArray(u)?u:[]; }); } },
                { key: 'date_from', label: '录制时间（起）', type: 'date' },
                { key: 'date_to', label: '录制时间（止）', type: 'date' }
            ]
        };
    };

    TaskSelectionDialog.prototype.fetchPaginatedData = async function(apiMethod, listKey, page, pageSize, sortOptions) {
        var token = localStorage.getItem('auth_token');
        var params = { page: page, page_size: pageSize };
        if (sortOptions && sortOptions.sortBy && sortOptions.sortOrder) {
            params.sort_by = sortOptions.sortBy;
            params.sort_order = sortOptions.sortOrder;
        }
        if (this.state.keyword) {
            params.keyword = this.state.keyword;
        }
        if (this.state.filters) {
            var filters = this.state.filters;
            for (var key in filters) {
                if (filters.hasOwnProperty(key) && filters[key] !== '' && filters[key] !== undefined && filters[key] !== null) {
                    params[key] = filters[key];
                }
            }
        }
        var data = await apiMethod.call(api, token, params);
        data = data || {};
        return { items: data[listKey] || [], total: data.total || 0 };
    };

    TaskSelectionDialog.prototype.handleSearch = function() {
        var keyword = this.searchInput ? this.searchInput.value.trim() : '';
        this.state.keyword = keyword;
        this.loadPage(1);
    };

    TaskSelectionDialog.prototype.jumpToPage = function() {
        var totalPages = this.getTotalPages();
        var jumpId = this.modalId + '-page-jump';
        var input = document.getElementById(jumpId);
        if (!input) return;
        var page = parseInt(input.value, 10);
        if (isNaN(page) || page < 1 || page > totalPages) {
            alert('请输入 1 到 ' + totalPages + ' 之间的页码');
            return;
        }
        input.value = '';
        this.loadPage(page);
    };

    TaskSelectionDialog.prototype.fetchTasks = async function(page, pageSize, sortOptions) {
        return this.fetchPaginatedData(api.getTaskList, 'tasks', page, pageSize, sortOptions);
    };

    TaskSelectionDialog.prototype.fetchRecordings = async function(page, pageSize, sortOptions) {
        return this.fetchPaginatedData(api.getRecordings, 'recordings', page, pageSize, sortOptions);
    };

    TaskSelectionDialog.prototype.toTimestamp = function(value) {
        var date = new Date(value);
        return isNaN(date.getTime()) ? 0 : date.getTime();
    };

    TaskSelectionDialog.prototype.getTaskColumns = function() {
        var self = this;
        return [
            {
                label: '任务',
                width: '50%',
                sortable: true,
                sortField: 'id',
                sortValue: function(item) { return item.id; },
                render: function(item) {
                    var desc = self.escapeHtml(item.description || '');
                    return '<div><strong>#' + item.id + '</strong></div>' +
                        '<div class="text-muted selection-dialog__cell-desc">' + desc + '</div>';
                }
            },
            {
                label: '状态',
                width: '20%',
                sortable: true,
                sortField: 'status',
                sortValue: function(item) { return item.status || ''; },
                render: function(item) {
                    return self.formatTaskStatusLabel(item.status);
                }
            },
            {
                label: '创建时间',
                width: '20%',
                sortable: true,
                sortField: 'created_at',
                sortValue: function(item) {
                    return self.toTimestamp(item.created_at);
                },
                render: function(item) {
                    return self.formatDateTime(item.created_at);
                }
            }
        ];
    };

    TaskSelectionDialog.prototype.getRecordingColumns = function() {
        var self = this;
        return [
            {
                label: '录制数据',
                width: '40%',
                sortable: true,
                sortField: 'directory_name',
                sortValue: function(item) { return (item.directory_name || '').toLowerCase(); },
                render: function(item) {
                    return '<strong>' + self.escapeHtml(item.directory_name || '-') + '</strong>';
                }
            },
            {
                label: '任务描述',
                width: '40%',
                sortable: true,
                sortField: 'task_description',
                sortValue: function(item) { return (item.task_description || '').toLowerCase(); },
                render: function(item) {
                    return self.escapeHtml(item.task_description || '-');
                }
            },
            {
                label: '录制人 / 时间',
                width: '20%',
                sortable: true,
                sortField: 'created_at',
                sortValue: function(item) {
                    return self.toTimestamp(item.created_at);
                },
                render: function(item) {
                    var user = self.escapeHtml(item.recorded_by_username || '-');
                    return user + '<br><span class="text-muted">' + self.formatDateTime(item.created_at) + '</span>';
                }
            }
        ];
    };

    TaskSelectionDialog.prototype.escapeHtml = function(str) {
        if (str === undefined || str === null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\"/g, '&quot;')
            .replace(/'/g, '&#39;');
    };

    TaskSelectionDialog.prototype.formatDateTime = function(value) {
        if (!value) return '-';
        var date = new Date(value);
        if (isNaN(date.getTime())) return '-';
        return date.toLocaleString();
    };

    TaskSelectionDialog.prototype.formatTaskStatusLabel = function(status) {
        var classMap = {
            'pending': 'label label-warning',
            'in_progress': 'label label-info',
            'completed': 'label label-success'
        };
        var textMap = {
            'pending': '待执行',
            'in_progress': '进行中',
            'completed': '已完成'
        };
        var cls = classMap[status] || 'label label-default';
        var text = textMap[status] || (status || '-');
        return '<span class="' + cls + '">' + text + '</span>';
    };

    TaskSelectionDialog.prototype.toggleFilterPanel = function() {
        var panel = this.modalElement.querySelector('.selection-dialog__filter-panel');
        if (!panel) return;
        var isVisible = panel.style.display !== 'none';
        if (isVisible) {
            panel.style.display = 'none';
            return;
        }
        if (!panel.innerHTML.trim()) {
            this.renderFilterPanel();
        }
        panel.style.display = 'block';
    };

    TaskSelectionDialog.prototype.renderFilterPanel = function() {
        var panel = this.modalElement.querySelector('.selection-dialog__filter-panel');
        if (!panel || !this.config.filterFields || !this.config.filterFields.length) {
            var btn = this.modalElement.querySelector('.selection-dialog__filter-btn');
            if (btn) btn.style.display = 'none';
            return;
        }
        var self = this;
        var fields = this.config.filterFields;
        var html = '';
        for (var i = 0; i < fields.length; i++) {
            var f = fields[i];
            html += '<div class="form-group" style="margin-bottom:8px;">';
            html += '<label style="font-size:12px;">' + self.escapeHtml(f.label) + '</label>';
            if (f.type === 'select-static') {
                html += '<select class="form-control input-sm" data-filter-key="' + f.key + '">';
                html += '<option value="">全部</option>';
                for (var j = 0; j < (f.options || []).length; j++) {
                    var opt = f.options[j];
                    html += '<option value="' + opt.value + '">' + self.escapeHtml(opt.label) + '</option>';
                }
                html += '</select>';
            } else if (f.type === 'select-async') {
                html += '<select class="form-control input-sm" data-filter-key="' + f.key + '" data-async-index="' + i + '">';
                html += '<option value="">加载中...</option>';
                html += '</select>';
            } else if (f.type === 'date') {
                html += '<input type="date" class="form-control input-sm" data-filter-key="' + f.key + '">';
            }
            html += '</div>';
        }
        html += '<div style="display:flex; gap:6px; justify-content:flex-end;">';
        html += '<button type="button" class="btn btn-default btn-sm selection-dialog__filter-clear">重置</button>';
        html += '<button type="button" class="btn btn-primary btn-sm selection-dialog__filter-apply">应用</button>';
        html += '</div>';
        panel.innerHTML = html;

        var applyBtn = panel.querySelector('.selection-dialog__filter-apply');
        var clearBtn = panel.querySelector('.selection-dialog__filter-clear');
        if (applyBtn) applyBtn.addEventListener('click', function() { self.applyFilters(); });
        if (clearBtn) clearBtn.addEventListener('click', function() { self.clearFilters(); });

        // 应用缓存的筛选值到静态选择框和日期框
        var staticInputs = panel.querySelectorAll('[data-filter-key]');
        for (var m = 0; m < staticInputs.length; m++) {
            var input = staticInputs[m];
            var key = input.getAttribute('data-filter-key');
            if (self.state.filters && self.state.filters[key] && !input.hasAttribute('data-async-index')) {
                input.value = self.state.filters[key];
            }
        }

        for (var k = 0; k < fields.length; k++) {
            if (fields[k].type === 'select-async' && typeof fields[k].fetchItems === 'function') {
                (function(field, index) {
                    var token = localStorage.getItem('auth_token');
                    if (self._filterCache && self._filterCache[field.key]) {
                        self._populateAsyncSelect(field, self._filterCache[field.key]);
                        return;
                    }
                    field.fetchItems(token).then(function(items) {
                        if (!self._filterCache) self._filterCache = {};
                        self._filterCache[field.key] = items;
                        self._populateAsyncSelect(field, items);
                    }).catch(function() {
                        var select = panel.querySelector('[data-async-index="' + index + '"]');
                        if (select) select.innerHTML = '<option value="">加载失败</option>';
                    });
                })(fields[k], k);
            }
        }
    };

    TaskSelectionDialog.prototype._populateAsyncSelect = function(field, items) {
        var panel = this.modalElement.querySelector('.selection-dialog__filter-panel');
        if (!panel) return;
        var select = panel.querySelector('[data-filter-key="' + field.key + '"]');
        if (!select) return;
        var html = '<option value="">全部</option>';
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var val = item[field.valueKey || 'id'];
            var label = item[field.labelKey || 'name'];
            html += '<option value="' + val + '">' + this.escapeHtml(label) + '</option>';
        }
        select.innerHTML = html;
        if (this.state.filters && this.state.filters[field.key]) {
            select.value = this.state.filters[field.key];
        }
    };

    TaskSelectionDialog.prototype.getFilterCacheKey = function() {
        var baseKey = this.config && this.config.cacheKey ? this.config.cacheKey : 'dialog-filters';
        var token = localStorage.getItem('auth_token');
        if (token) {
            try {
                var payload = JSON.parse(atob(token.split('.')[1]));
                var userId = payload.sub || payload.user_id || '';
                return baseKey + '-user-' + userId;
            } catch (e) {
                return baseKey;
            }
        }
        return baseKey;
    };

    TaskSelectionDialog.prototype.loadCachedFilters = function() {
        try {
            var key = this.getFilterCacheKey();
            var cached = sessionStorage.getItem(key);
            return cached ? JSON.parse(cached) : {};
        } catch (e) {
            return {};
        }
    };

    TaskSelectionDialog.prototype.saveCachedFilters = function() {
        try {
            var key = this.getFilterCacheKey();
            sessionStorage.setItem(key, JSON.stringify(this.state.filters || {}));
        } catch (e) {}
    };

    TaskSelectionDialog.prototype.applyFilters = function() {
        var panel = this.modalElement.querySelector('.selection-dialog__filter-panel');
        if (!panel) return;
        var inputs = panel.querySelectorAll('[data-filter-key]');
        var filters = {};
        for (var i = 0; i < inputs.length; i++) {
            var key = inputs[i].getAttribute('data-filter-key');
            var val = inputs[i].value;
            if (val) filters[key] = val;
        }
        this.state.filters = filters;
        this.saveCachedFilters();
        this.updateFilterBadge();
        panel.style.display = 'none';
        this.loadPage(1);
    };

    TaskSelectionDialog.prototype.clearFilters = function() {
        var panel = this.modalElement.querySelector('.selection-dialog__filter-panel');
        if (!panel) return;
        var inputs = panel.querySelectorAll('[data-filter-key]');
        for (var i = 0; i < inputs.length; i++) {
            inputs[i].value = '';
        }
        this.state.filters = {};
        this.saveCachedFilters();
        this.updateFilterBadge();
        panel.style.display = 'none';
        this.loadPage(1);
    };

    TaskSelectionDialog.prototype.updateFilterBadge = function() {
        var badge = this.modalElement.querySelector('.selection-dialog__filter-badge');
        if (!badge) return;
        var count = 0;
        var filters = this.state.filters || {};
        for (var key in filters) {
            if (filters.hasOwnProperty(key) && filters[key]) count++;
        }
        badge.style.display = count > 0 ? 'inline' : 'none';
        badge.textContent = count;
    };

    window.TaskSelectionDialog = TaskSelectionDialog;
})(window);
