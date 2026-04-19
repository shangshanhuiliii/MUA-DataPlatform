class EventEditDialog {
    constructor() {
        this.overlay = null;
        this.currentCallback = null;
        this.currentData = null;
        this.isInitialized = false;
        this.currentParsedFields = null;
        this.allowedEventTypes = ['touch', 'swipe', 'put_text', 'hotkey'];
        
        // Store original HTML for point coordinate display
        this.originalPointCoordHTML = null;
        
        // Point/Bbox image editor related properties
        this.pointImageEditor = {
            overlay: null,
            currentFieldName: null,
            currentImageSrc: null,
            isInitialized: false,
            selectedX: 0,
            selectedY: 0,
            zoomLevel: 1.0,
            originalImageSize: null,
            // Bbox editing properties
            mode: 'point', // 'point' or 'bbox'
            bboxDragging: false,
            bboxStartX: 0,
            bboxStartY: 0,
            bboxEndX: 0,
            bboxEndY: 0,
            // Bbox result properties
            bboxLeft: 0,
            bboxTop: 0,
            bboxWidth: 0,
            bboxHeight: 0
        };
    }

    init() {
        if (this.isInitialized) return;
        
        this.overlay = document.getElementById('edit-dialog-overlay');
        if (!this.overlay) {
            console.error('Edit dialog overlay not found');
            return;
        }
        
        // Close dialog when clicking outside
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.close();
            }
        });
        
        // Close dialog on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen()) {
                this.close();
            }
        });
        
        this.isInitialized = true;
    }

    isOpen() {
        return this.overlay && this.overlay.style.display !== 'none';
    }

    isAllowedEventType(eventType) {
        return this.allowedEventTypes.includes(eventType);
    }

    clearLegacyEventTypeOptions(selectElement) {
        if (!selectElement) return;

        Array.from(selectElement.options).forEach((option) => {
            if (option.dataset.legacyOption === 'true') {
                option.remove();
            }
        });
    }

    getUiEventTypeFromClassName(eventType) {
        if (!eventType || !window.eventStrParser) {
            return eventType;
        }

        const mapping = window.eventStrParser.eventTypeMapping || {};
        for (const [uiEventType, className] of Object.entries(mapping)) {
            if (className === eventType) {
                return uiEventType;
            }
        }

        return eventType;
    }

    getDisplayEventType(eventType) {
        if (!eventType) {
            return 'touch';
        }

        return this.getUiEventTypeFromClassName(eventType) || eventType;
    }

    prepareEventTypeSelect(selectElement, currentEventType) {
        if (!selectElement) return;

        const displayEventType = this.getDisplayEventType(currentEventType);
        this.clearLegacyEventTypeOptions(selectElement);

        if (displayEventType && !this.isAllowedEventType(displayEventType)) {
            const option = document.createElement('option');
            option.value = displayEventType;
            option.textContent = displayEventType;
            option.dataset.legacyOption = 'true';
            selectElement.insertBefore(option, selectElement.firstChild);
        }

        selectElement.value = displayEventType;
    }

    open(config) {
        console.log('EventEditDialog.open() received config:', config);
        this.init();
        if (!this.overlay) return;

        // Store callback and data
        this.currentCallback = config.onSave || null;
        this.currentData = config.data || {};

        // Set dialog title
        const titleElement = document.getElementById('dialog-title');
        if (titleElement) {
            titleElement.textContent = config.title || '编辑事件';
        }

        // Configure from state dropdown
        const fromStateGroup = document.getElementById('dialog-from-state-group');
        const fromStateSelect = document.getElementById('dialog-from-state');
        
        console.log('From State Config:', { showFromState: config.showFromState, nodes: config.nodes, fromState: config.data?.fromState });
        
        if (config.showFromState && fromStateGroup && fromStateSelect) {
            fromStateGroup.style.display = 'block';
            
            // Clear existing options
            fromStateSelect.innerHTML = '';
            
            // Populate with nodes if provided
            if (config.nodes) {
                config.nodes.forEach((node, index) => {
                    const option = document.createElement('option');
                    option.value = node.id;
                    option.textContent = `${index + 1}. ${node.label || node.id}`;
                    fromStateSelect.appendChild(option);
                });
            }
            
            // Set current value
            if (config.data && config.data.fromState) {
                fromStateSelect.value = config.data.fromState;
            }
        } else if (fromStateGroup) {
            fromStateGroup.style.display = 'none';
        }

        // Configure target state dropdown
        const targetStateGroup = document.getElementById('dialog-target-state-group');
        const targetStateSelect = document.getElementById('dialog-target-state');
        
        console.log('Target State Config:', { showTargetState: config.showTargetState, targetState: config.data?.targetState });
        
        if (config.showTargetState && targetStateGroup && targetStateSelect) {
            targetStateGroup.style.display = 'block';
            
            // Clear existing options
            targetStateSelect.innerHTML = '';
            
            // Populate with nodes if provided
            if (config.nodes) {
                config.nodes.forEach((node, index) => {
                    const option = document.createElement('option');
                    option.value = node.id;
                    option.textContent = `${index + 1}. ${node.label || node.id}`;
                    targetStateSelect.appendChild(option);
                });
            }
            
            // Set current value
            if (config.data && config.data.targetState) {
                targetStateSelect.value = config.data.targetState;
            }
        } else if (targetStateGroup) {
            targetStateGroup.style.display = 'none';
        }

        // Set form values
        const eventTypeSelect = document.getElementById('dialog-event-type');
        const initialEventType = (config.data && config.data.eventType) || 'touch';
        
        if (eventTypeSelect) {
            this.prepareEventTypeSelect(eventTypeSelect, initialEventType);
        }
        
        // Setup event type change listener to re-parse fields
        if (eventTypeSelect) {
            eventTypeSelect.onchange = () => {
                this.clearLegacyEventTypeOptions(eventTypeSelect);
                this.handleEventTypeChange();
            };
        }

        // Show dialog
        this.overlay.style.display = 'flex';
        
        // Initialize field editing with the provided EventStr
        this.initializeFieldEditing(
            (config.data && config.data.eventStr) || '', 
            initialEventType
        );
    }

    close() {
        if (!this.overlay) return;
        
        this.overlay.style.display = 'none';
        this.currentCallback = null;
        this.currentData = null;
        this.currentParsedFields = null;
    }

    async save() {
        if (!this.currentCallback) {
            this.close();
            return;
        }

        // Collect form data
        const fromStateSelect = document.getElementById('dialog-from-state');
        const targetStateSelect = document.getElementById('dialog-target-state');
        const eventTypeSelect = document.getElementById('dialog-event-type');
        
        // Generate EventStr from fields
        const finalEventStr = this.generateEventStrFromFields() || '';
        
        const formData = {
            fromState: fromStateSelect ? fromStateSelect.value : null,
            targetState: targetStateSelect ? targetStateSelect.value : null,
            eventType: eventTypeSelect ? eventTypeSelect.value : this.getDisplayEventType(this.currentParsedFields?.eventType),
            eventStr: finalEventStr
        };

        try {
            // Call the save callback
            await this.currentCallback(formData);
            this.close();
        } catch (error) {
            console.error('Error saving dialog data:', error);
            if (window.showError) {
                window.showError('保存失败，请重试');
            } else {
                alert('保存失败，请重试');
            }
        }
    }

    // Convenience method for node editing
    openForNodeEditing(config) {
        return this.open({
            title: config.isAddingNewEdge ? '添加新边' : '编辑边',
            showFromState: config.showFromState,
            showTargetState: true,
            nodes: config.nodes,
            data: {
                fromState: config.fromState,
                targetState: config.targetState,
                eventType: config.eventType || 'touch',
                eventStr: config.eventStr || ''
            },
            onSave: config.onSave
        });
    }

    // Convenience method for edge event editing
    openForEdgeEditing(config) {
        console.log('openForEdgeEditing received config:', config);
        const finalConfig = {
            title: '编辑事件',
            showFromState: config.showFromState,
            showTargetState: config.showTargetState,
            nodes: config.nodes,
            data: {
                fromState: config.fromState,
                targetState: config.targetState,
                eventType: config.eventType || 'touch',
                eventStr: config.eventStr || ''
            },
            onSave: config.onSave
        };
        console.log('openForEdgeEditing final config:', finalConfig);
        return this.open(finalConfig);
    }

    /**
     * 初始化字段编辑模式
     * @param {string} eventStr - 初始EventStr
     * @param {string} eventType - 事件类型
     */
    initializeFieldEditing(eventStr, eventType) {
        // 如果有EventStr，解析它；否则根据事件类型创建空字段
        if (eventStr && eventStr.trim()) {
            this.parseEventStrToFields(eventStr);
            this.syncEventTypeSelection(eventType);
        } else {
            this.createEmptyFields(eventType);
            this.syncEventTypeSelection(eventType);
        }
    }

    syncEventTypeSelection(fallbackEventType) {
        const eventTypeSelect = document.getElementById('dialog-event-type');
        if (!eventTypeSelect) {
            return;
        }

        const currentEventType = this.currentParsedFields?.eventType || fallbackEventType;
        this.prepareEventTypeSelect(eventTypeSelect, currentEventType);
        this.updateGeneratedEventStr();
    }

    /**
     * 处理事件类型改变
     */
    handleEventTypeChange() {
        const eventTypeSelect = document.getElementById('dialog-event-type');
        if (!eventTypeSelect) return;

        const newEventType = this.isAllowedEventType(eventTypeSelect.value) ? eventTypeSelect.value : 'touch';
        const newClassName = window.eventStrParser ? window.eventStrParser.getClassName(newEventType) : newEventType;
        
        // 保存当前字段值
        const currentFields = this.currentParsedFields ? { ...this.currentParsedFields.fields } : {};
        
        // 创建新事件类型的字段结构
        this.createEmptyFields(newEventType);
        
        // 将兼容的字段值迁移到新结构中
        this.migrateCompatibleFields(currentFields, newClassName);
        
        // 重新渲染字段编辑器
        const fieldsContainer = document.getElementById('dialog-parsed-fields');
        if (fieldsContainer && this.currentParsedFields) {
            this.renderFieldEditors(this.currentParsedFields, fieldsContainer);
            this.updateGeneratedEventStr();
        }
    }

    /**
     * 将兼容的字段值迁移到新的事件类型结构中
     * @param {Object} oldFields - 旧的字段值
     * @param {string} newEventType - 新的事件类型类名
     */
    migrateCompatibleFields(oldFields, newEventType) {
        if (!this.currentParsedFields || !window.eventStrParser) return;
        
        const newSchema = window.eventStrParser.eventTypeSchema[newEventType] || [];
        
        // 遍历新结构中的每个字段，尝试从旧字段中迁移兼容的值
        for (const fieldName of newSchema) {
            if (oldFields[fieldName] && this.isFieldValueCompatible(fieldName, oldFields[fieldName], newEventType)) {
                this.currentParsedFields.fields[fieldName] = oldFields[fieldName];
            }
        }
        
        // 更新事件类型
        this.currentParsedFields.eventType = newEventType;
    }

    /**
     * 检查字段值是否与新事件类型兼容
     * @param {string} fieldName - 字段名
     * @param {*} fieldValue - 字段值
     * @param {string} newEventType - 新事件类型
     * @returns {boolean} 是否兼容
     */
    isFieldValueCompatible(fieldName, fieldValue, newEventType) {
        if (!fieldValue) return false;
        
        // 检查基本字段类型兼容性
        if (typeof fieldValue === 'object') {
            // point 类型字段
            if (fieldValue.type === 'point' && fieldName.includes('point')) {
                return true;
            }
            // bbox 类型字段
            if (fieldValue.type === 'bbox' && fieldName.includes('bbox')) {
                return true;
            }
            // view 类型字段
            if (fieldValue.type === 'view' && fieldName === 'view') {
                return true;
            }
        }
        
        // 简单值类型字段
        if (typeof fieldValue === 'string' || typeof fieldValue === 'number') {
            // 基本字段名兼容性检查
            const compatibleFields = ['text', 'name', 'intent', 'time', 'duration', 'direction'];
            return compatibleFields.includes(fieldName);
        }
        
        return false;
    }

    /**
     * 为特定字段获取默认值
     * @param {string} fieldName - 字段名
     * @param {string} eventType - 事件类型
     * @returns {*} 默认值
     */
    getDefaultValueForField(fieldName, eventType) {
        const defaults = {
            // KeyEvent 字段
            'name': 'BACK',
            
            // ManualEvent 字段
            'time': Math.floor(Date.now() / 1000),
            
            // SetTextEvent 字段
            'text': '',
            
            // LongTouchEvent 字段
            'duration': 2000,
            
            // ScrollEvent 字段
            'direction': 'DOWN',
            
            // SwipeEvent 字段
            'duration': 1000,
            
            // IntentEvent 字段
            'intent': ''
        };
        
        return defaults[fieldName] || '';
    }

    /**
     * 获取特定字段的选项列表
     * @param {string} fieldName - 字段名
     * @returns {Array|null} 选项列表或null（如果不需要下拉选择）
     */
    getFieldOptions(fieldName) {
        const fieldOptions = {
            'direction': [
                { value: 'UP', label: 'UP' },
                { value: 'DOWN', label: 'DOWN' },
                { value: 'LEFT', label: 'LEFT' },
                { value: 'RIGHT', label: 'RIGHT' }
            ],
            'name': [
                { value: 'BACK', label: 'BACK' },
                { value: 'HOME', label: 'HOME' },
                // { value: 'MENU', label: 'MENU' },
                // { value: 'POWER', label: 'POWER' },
                // { value: 'VOLUME_UP', label: 'VOLUME_UP' },
                // { value: 'VOLUME_DOWN', label: 'VOLUME_DOWN' },
                // { value: 'ENTER', label: 'ENTER' },
                // { value: 'DEL', label: 'DEL' },
                // { value: 'SEARCH', label: 'SEARCH' }
            ]
        };
        
        return fieldOptions[fieldName] || null;
    }

    /**
     * 根据事件类型创建空字段
     * @param {string} eventType - 事件类型
     */
    createEmptyFields(eventType) {
        if (!window.eventStrParser) {
            console.error('EventStrParser not available');
            return;
        }

        const className = window.eventStrParser.getClassName(eventType);
        const schema = window.eventStrParser.eventTypeSchema[className] || [];
        
        const parsed = {
            eventType: className,
            original: '',
            fields: {}
        };

        // 根据schema创建默认字段，提供更好的默认值
        for (const fieldName of schema) {
            if (fieldName === 'view') {
                parsed.fields[fieldName] = {
                    type: 'view',
                    viewStr: '',
                    activity: '',
                    className: '',
                    text: ''
                };
            } else if (fieldName.includes('point')) {
                parsed.fields[fieldName] = {
                    type: 'point',
                    x: -1,
                    y: -1
                };
            } else if (fieldName.includes('bbox')) {
                parsed.fields[fieldName] = {
                    type: 'bbox',
                    left: -1,
                    top: -1,
                    width: -1,
                    height: -1
                };
            } else {
                // 为不同字段提供特定的默认值
                parsed.fields[fieldName] = this.getDefaultValueForField(fieldName, className);
            }
        }

        this.currentParsedFields = parsed;
        const fieldsContainer = document.getElementById('dialog-parsed-fields');
        if (fieldsContainer) {
            this.renderFieldEditors(parsed, fieldsContainer);
            this.updateGeneratedEventStr();
        }
    }

    /**
     * 解析EventStr到字段编辑界面
     * @param {string} inputEventStr - 可选的EventStr输入，如果不提供则从生成的EventStr获取
     */
    parseEventStrToFields(inputEventStr) {
        if (!window.eventStrParser) {
            console.error('EventStrParser not available');
            return;
        }

        const fieldsContainer = document.getElementById('dialog-parsed-fields');
        const eventTypeSelect = document.getElementById('dialog-event-type');
        
        if (!fieldsContainer) {
            return;
        }

        let eventStr;
        if (inputEventStr) {
            eventStr = inputEventStr.trim();
        } else if (this.currentParsedFields) {
            // 从当前字段重新生成EventStr并使用新的事件类型
            const currentEventType = eventTypeSelect ? eventTypeSelect.value : this.currentParsedFields.eventType;
            eventStr = window.eventStrParser.generateEventStr(this.currentParsedFields.fields, currentEventType);
        } else {
            // 创建空字段
            const currentEventType = eventTypeSelect ? eventTypeSelect.value : 'touch';
            this.createEmptyFields(currentEventType);
            return;
        }
        if (!eventStr) {
            fieldsContainer.innerHTML = '<p class="text-muted">没有可解析的事件字符串</p>';
            this.currentParsedFields = null;
            return;
        }

        try {
            const parsed = window.eventStrParser.parseEventStr(eventStr);
            
            if (parsed.error) {
                fieldsContainer.innerHTML = `<div class="alert alert-warning">${parsed.error}</div>`;
                this.currentParsedFields = null;
                return;
            }

            this.currentParsedFields = parsed;
            this.renderFieldEditors(parsed, fieldsContainer);
            this.updateGeneratedEventStr();

        } catch (error) {
            console.error('Error parsing EventStr:', error);
            fieldsContainer.innerHTML = `<div class="alert alert-danger">事件字符串解析失败：${error.message}</div>`;
            this.currentParsedFields = null;
        }
    }

    /**
     * 渲染字段编辑器
     */
    renderFieldEditors(parsed, container) {
        let html = `<h5>编辑事件字段（${parsed.eventType}）</h5>`;
        
        if (Object.keys(parsed.fields).length === 0) {
            html += '<p class="text-muted">当前事件没有可编辑字段。</p>';
        } else {
            for (const [fieldName, fieldValue] of Object.entries(parsed.fields)) {
                html += this.renderSingleField(fieldName, fieldValue);
            }
        }

        container.innerHTML = html;

        // Setup event listeners for field inputs
        this.setupFieldInputListeners();
    }

    /**
     * 渲染单个字段编辑器
     */
    renderSingleField(fieldName, fieldValue) {
        let html = `<div class="form-group" data-field="${fieldName}">`;
        html += `<label>${fieldName}:</label>`;

        if (fieldValue && typeof fieldValue === 'object') {
            if (fieldValue.type === 'point') {
                html += '<div class="row">';
                html += `<div class="col-md-6">`;
                html += `<label class="control-label">X 坐标：</label>`;
                html += `<input type="number" class="form-control field-input" data-field="${fieldName}" data-subfield="x" value="${fieldValue.x}">`;
                html += `</div>`;
                html += `<div class="col-md-6">`;
                html += `<label class="control-label">Y 坐标：</label>`;
                html += `<input type="number" class="form-control field-input" data-field="${fieldName}" data-subfield="y" value="${fieldValue.y}">`;
                html += `</div>`;
                html += '</div>';
                html += '<div class="row" style="margin-top: 10px;">';
                html += `<div class="col-md-12">`;
                html += `<button type="button" class="btn btn-primary btn-sm edit-point-btn" data-field="${fieldName}">`;
                html += `<span class="glyphicon glyphicon-picture"></span> 在图片上编辑`;
                html += `</button>`;
                html += `</div>`;
                html += '</div>';
                if (fieldValue._incomplete) {
                    html += `<small class="text-warning">原始不完整值：${fieldValue._originalValue}</small>`;
                }
            } else if (fieldValue.type === 'bbox') {
                html += '<div class="row">';
                html += `<div class="col-md-3">`;
                html += `<label class="control-label">左侧：</label>`;
                html += `<input type="number" class="form-control field-input" data-field="${fieldName}" data-subfield="left" value="${fieldValue.left}">`;
                html += `</div>`;
                html += `<div class="col-md-3">`;
                html += `<label class="control-label">顶部：</label>`;
                html += `<input type="number" class="form-control field-input" data-field="${fieldName}" data-subfield="top" value="${fieldValue.top}">`;
                html += `</div>`;
                html += `<div class="col-md-3">`;
                html += `<label class="control-label">宽度：</label>`;
                html += `<input type="number" class="form-control field-input" data-field="${fieldName}" data-subfield="width" value="${fieldValue.width}">`;
                html += `</div>`;
                html += `<div class="col-md-3">`;
                html += `<label class="control-label">高度：</label>`;
                html += `<input type="number" class="form-control field-input" data-field="${fieldName}" data-subfield="height" value="${fieldValue.height}">`;
                html += `</div>`;
                html += '</div>';
                html += '<div class="row" style="margin-top: 10px;">';
                html += `<div class="col-md-12">`;
                html += `<button type="button" class="btn btn-primary btn-sm edit-bbox-btn" data-field="${fieldName}">`;
                html += `<span class="glyphicon glyphicon-picture"></span> 在图片上编辑`;
                html += `</button>`;
                html += `</div>`;
                html += '</div>';
                if (fieldValue._incomplete) {
                    html += `<small class="text-warning">原始不完整值：${fieldValue._originalValue}</small>`;
                }
            } else if (fieldValue.type === 'view') {
                // 简化view字段显示为一个输入框，显示完整的view信息
                let fullViewValue = '';
                if (fieldValue.viewStr && fieldValue.activity && fieldValue.className !== undefined && fieldValue.text !== undefined) {
                    fullViewValue = `${fieldValue.viewStr}(${fieldValue.activity}/${fieldValue.className}-${fieldValue.text})`;
                } else if (fieldValue.viewStr && fieldValue.descriptor) {
                    fullViewValue = `${fieldValue.viewStr}(${fieldValue.descriptor})`;
                } else {
                    fullViewValue = fieldValue.viewStr || fieldValue.value || '';
                }
                html += `<input type="text" class="form-control field-input" data-field="${fieldName}" data-subfield="full" value="${fullViewValue}" placeholder="例如：view_str(activity/class-text)">`;
            } else {
                html += `<textarea class="form-control field-input" data-field="${fieldName}" rows="2">${JSON.stringify(fieldValue, null, 2)}</textarea>`;
            }
        } else {
            // 为特定字段提供下拉选择或特殊输入
            const fieldOptions = this.getFieldOptions(fieldName);
            if (fieldOptions) {
                html += `<select class="form-control field-input" data-field="${fieldName}">`;
                for (const option of fieldOptions) {
                    const selected = (fieldValue === option.value) ? 'selected' : '';
                    html += `<option value="${option.value}" ${selected}>${option.label}</option>`;
                }
                html += `</select>`;
            } else if (fieldName === 'time' || fieldName === 'duration') {
                html += `<input type="number" class="form-control field-input" data-field="${fieldName}" value="${fieldValue || ''}" ${fieldName === 'time' ? 'readonly' : ''}>`;
            } else {
                html += `<input type="text" class="form-control field-input" data-field="${fieldName}" value="${fieldValue || ''}">`;
            }
        }

        html += '</div>';
        return html;
    }

    /**
     * 设置字段输入监听器
     */
    setupFieldInputListeners() {
        const inputs = document.querySelectorAll('.field-input');
        inputs.forEach(input => {
            input.addEventListener('input', () => {
                this.updateFieldValue(input);
                this.updateGeneratedEventStr();
            });
        });

        // 设置 point 编辑按钮的事件监听器
        const editPointBtns = document.querySelectorAll('.edit-point-btn');
        editPointBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const fieldName = btn.dataset.field;
                this.openPointImageEditor(fieldName);
            });
        });
        
        // 设置 bbox 编辑按钮的事件监听器
        const editBboxBtns = document.querySelectorAll('.edit-bbox-btn');
        editBboxBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const fieldName = btn.dataset.field;
                this.openBboxImageEditor(fieldName);
            });
        });
    }

    /**
     * 更新字段值
     */
    updateFieldValue(input) {
        if (!this.currentParsedFields) return;

        const fieldName = input.dataset.field;
        const subfield = input.dataset.subfield;
        
        if (subfield) {
            // Handle complex field types
            if (!this.currentParsedFields.fields[fieldName]) {
                this.currentParsedFields.fields[fieldName] = {};
            }
            
            let value = input.value;
            if (input.type === 'number') {
                value = parseInt(value) || 0;
            }
            
            if (subfield === 'full' && this.currentParsedFields.fields[fieldName].type === 'view') {
                // 处理完整的view字段输入，重新解析
                this.currentParsedFields.fields[fieldName] = this.parseViewInput(value);
            } else {
                this.currentParsedFields.fields[fieldName][subfield] = value;
            }
        } else {
            // Handle simple field types
            let value = input.value;
            if (input.type === 'number') {
                value = parseInt(value) || 0;
            }
            
            this.currentParsedFields.fields[fieldName] = value;
        }
    }

    /**
     * 生成EventStr从字段
     */
    generateEventStrFromFields() {
        if (!this.currentParsedFields || !window.eventStrParser) {
            return '';
        }

        try {
            const eventStr = window.eventStrParser.generateEventStr(
                this.currentParsedFields.fields, 
                this.currentParsedFields.eventType
            );
            return eventStr;
        } catch (error) {
            console.error('Error generating EventStr:', error);
            return '';
        }
    }

    /**
     * 解析view输入字符串
     * @param {string} viewInput - view输入字符串
     * @returns {Object} 解析后的view对象
     */
    parseViewInput(viewInput) {
        if (!viewInput || !viewInput.trim()) {
            return {
                type: 'view',
                viewStr: '',
                activity: '',
                className: '',
                text: ''
            };
        }

        // 使用EventStrParser的view解析逻辑
        if (window.eventStrParser) {
            const parsed = window.eventStrParser.parseViewValue(viewInput);
            return parsed;
        } else {
            return {
                type: 'view',
                value: viewInput
            };
        }
    }

    /**
     * 更新生成的EventStr显示
     */
    updateGeneratedEventStr() {
        const textarea = document.getElementById('dialog-generated-event-str');
        if (textarea) {
            const generated = this.generateEventStrFromFields();
            textarea.value = generated;
        }
    }

    /**
     * 打开 point 字段的图片编辑器
     * @param {string} fieldName - 字段名称
     */
    openPointImageEditor(fieldName) {
        if (!this.initPointImageEditor()) {
            return;
        }

        this.pointImageEditor.currentFieldName = fieldName;
        this.pointImageEditor.mode = 'point'; // 确保设置为point模式
        
        // 获取当前状态的图片
        this.getCurrentStateImage().then(imageSrc => {
            if (imageSrc) {
                this.pointImageEditor.currentImageSrc = imageSrc;
                this.displayImageInEditor(imageSrc);
                this.pointImageEditor.overlay.style.display = 'flex';
                
                // 设置标题
                const titleElement = document.getElementById('point-editor-title');
                if (titleElement) {
                    titleElement.textContent = `点击图片设置 ${fieldName}`;
                }

                // 重置说明文本
                const instructionsElement = document.getElementById('point-editor-instructions');
                if (instructionsElement) {
                    instructionsElement.innerHTML = '<strong>说明：</strong>点击图片设置绝对像素坐标，使用缩放按钮或 Ctrl+滚轮调整图片大小。';
                }
                
                // 重置坐标标签为point模式
                this.resetPointCoordinateLabels();
            } else {
                alert('无法加载状态截图进行编辑');
            }
        }).catch(error => {
            console.error('Error loading state image:', error);
            alert('加载状态截图失败：' + error.message);
        });
    }

    /**
     * 初始化图片编辑器
     */
    initPointImageEditor() {
        if (this.pointImageEditor.isInitialized) return true;
        
        this.pointImageEditor.overlay = document.getElementById('point-image-editor-overlay');
        if (!this.pointImageEditor.overlay) {
            console.error('Point image editor overlay not found');
            return false;
        }
        
        // 设置滚轮缩放事件监听器
        const scrollContainer = document.getElementById('point-editor-scroll-container');
        if (scrollContainer) {
            scrollContainer.addEventListener('wheel', (e) => {
                if (e.ctrlKey) {
                    e.preventDefault();
                    const factor = e.deltaY > 0 ? 0.9 : 1.1;
                    this.zoomImage(factor);
                }
            });
        }
        
        this.pointImageEditor.isInitialized = true;
        return true;
    }

    /**
     * 设置图片编辑器的事件监听器
     */
    setupImageEventListeners() {
        const image = document.getElementById('point-editor-image');
        if (!image) return;
        
        // 清除所有现有的事件监听器
        const newImage = image.cloneNode(true);
        image.parentNode.replaceChild(newImage, image);
        
        // 根据当前模式设置相应的事件监听器
        if (this.pointImageEditor.mode === 'bbox') {
            // bbox模式的事件监听器
            newImage.addEventListener('mousedown', (e) => {
                this.handleBboxMouseDown(e);
            });
            newImage.addEventListener('mousemove', (e) => {
                this.handleBboxMouseMove(e);
            });
            newImage.addEventListener('mouseup', (e) => {
                this.handleBboxMouseUp(e);
            });
            newImage.style.cursor = 'crosshair';
        } else {
            // point模式的事件监听器
            newImage.addEventListener('click', (e) => {
                this.handleImageClick(e);
            });
            newImage.style.cursor = 'crosshair';
        }
    }

    /**
     * 获取当前状态的图片
     */
    async getCurrentStateImage() {
        try {
            // 方案1: 从 nodeEditor 获取当前选中的节点图片
            if (window.nodeEditor && window.nodeEditor.currentNodeId && window.utgViewer && window.utgViewer.utg) {
                const currentNode = window.utgViewer.utg.nodes.find(n => n.id === window.nodeEditor.currentNodeId);
                if (currentNode && currentNode.image) {
                    return currentNode.image;
                }
            }
            
            // 方案2: 从网络组件获取选中的节点
            if (window.utgViewer && window.utgViewer.network && window.utgViewer.utg) {
                const selectedNodes = window.utgViewer.network.getSelectedNodes();
                if (selectedNodes && selectedNodes.length > 0) {
                    const selectedNodeId = selectedNodes[0];
                    const selectedNode = window.utgViewer.utg.nodes.find(n => n.id === selectedNodeId);
                    if (selectedNode && selectedNode.image) {
                        return selectedNode.image;
                    }
                }
            }
            
            // 方案3: 从当前编辑的数据中获取 from state
            if (this.currentData && this.currentData.fromState && window.utgViewer && window.utgViewer.utg) {
                const fromNode = window.utgViewer.utg.nodes.find(n => n.id === this.currentData.fromState);
                if (fromNode && fromNode.image) {
                    return fromNode.image;
                }
            }
            
            throw new Error('当前没有可编辑的状态截图，请先选择节点。');
        } catch (error) {
            console.error('Error getting current state image:', error);
            throw error;
        }
    }


    /**
     * 在编辑器中显示图片
     */
    displayImageInEditor(imageSrc) {
        const image = document.getElementById('point-editor-image');
        if (image) {
            image.src = imageSrc;
            image.onload = () => {
                // 保存原始图片尺寸
                this.pointImageEditor.originalImageSize = {
                    width: image.naturalWidth,
                    height: image.naturalHeight
                };
                
                // 设置正确的事件监听器
                this.setupImageEventListeners();
                
                // 计算合适的初始缩放比例
                this.calculateInitialZoom();
                this.applyZoom();
                
                // 图片加载完成后，如果有当前字段的值，显示在图片上
                this.showCurrentPointOnImage();
            };
        }
    }

    /**
     * 在图片上显示当前 point 的位置
     */
    showCurrentPointOnImage() {
        if (!this.pointImageEditor.currentFieldName || !this.currentParsedFields) {
            return;
        }
        
        const fieldValue = this.currentParsedFields.fields[this.pointImageEditor.currentFieldName];
        if (fieldValue && fieldValue.type === 'point' && fieldValue.x !== undefined && fieldValue.y !== undefined) {
            // 转换坐标为图片上的位置 - 使用绝对坐标
            const image = document.getElementById('point-editor-image');
            const crosshair = document.getElementById('point-editor-crosshair');
            
            if (image && crosshair && this.pointImageEditor.originalImageSize) {
                const rect = image.getBoundingClientRect();
                // 计算绝对坐标在当前显示图片上的位置
                const x = (fieldValue.x / this.pointImageEditor.originalImageSize.width) * rect.width;
                const y = (fieldValue.y / this.pointImageEditor.originalImageSize.height) * rect.height;
                
                this.setCrosshairPosition(x, y);
                this.pointImageEditor.selectedX = fieldValue.x;
                this.pointImageEditor.selectedY = fieldValue.y;
                
                // 更新坐标显示
                document.getElementById('point-editor-x').value = fieldValue.x;
                document.getElementById('point-editor-y').value = fieldValue.y;
            }
        }
        
        // Show bbox preview if there are bbox fields in current parsed fields
        this.showBboxPreviewInPointMode();
    }

    /**
     * 处理图片点击事件
     */
    handleImageClick(event) {
        const image = event.target;
        const rect = image.getBoundingClientRect();
        
        // 计算相对于图片的点击位置
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        
        // 转换为绝对坐标（基于原始图片尺寸）
        if (this.pointImageEditor.originalImageSize) {
            const absoluteX = Math.round((x / rect.width) * this.pointImageEditor.originalImageSize.width);
            const absoluteY = Math.round((y / rect.height) * this.pointImageEditor.originalImageSize.height);
            
            // 确保坐标在有效范围内
            this.pointImageEditor.selectedX = Math.max(0, Math.min(this.pointImageEditor.originalImageSize.width, absoluteX));
            this.pointImageEditor.selectedY = Math.max(0, Math.min(this.pointImageEditor.originalImageSize.height, absoluteY));
        } else {
            // 后备方案：如果没有原始图片尺寸，使用显示尺寸作为绝对坐标
            this.pointImageEditor.selectedX = Math.max(0, Math.round(x));
            this.pointImageEditor.selectedY = Math.max(0, Math.round(y));
        }
        
        // 设置十字准线位置 (相对于图片的坐标)
        this.setCrosshairPosition(x, y);
        
        // 更新坐标显示
        document.getElementById('point-editor-x').value = this.pointImageEditor.selectedX;
        document.getElementById('point-editor-y').value = this.pointImageEditor.selectedY;
    }

    /**
     * 设置十字准线位置
     */
    setCrosshairPosition(x, y) {
        const crosshair = document.getElementById('point-editor-crosshair');
        if (crosshair) {
            crosshair.style.left = x + 'px';
            crosshair.style.top = y + 'px';
            crosshair.style.display = 'block';
            
            // 确保十字准线大小与当前缩放级别匹配
            this.updateCrosshairSize();
        }
    }

    /**
     * 更新十字准线大小
     */
    updateCrosshairSize() {
        const crosshair = document.getElementById('point-editor-crosshair');
        if (crosshair) {
            const baseCrosshairSize = 15; // 基础大小
            const minCrosshairSize = 15;   // 最小大小
            const maxCrosshairSize = 20;  // 最大大小
            
            let crosshairSize = baseCrosshairSize * this.pointImageEditor.zoomLevel;
            crosshairSize = Math.max(minCrosshairSize, Math.min(maxCrosshairSize, crosshairSize));
            
            const halfSize = crosshairSize / 2;
            crosshair.style.width = crosshairSize + 'px';
            crosshair.style.height = crosshairSize + 'px';
            crosshair.style.marginLeft = -halfSize + 'px';
            crosshair.style.marginTop = -halfSize + 'px';
        }
    }

    /**
     * 应用选择的坐标 (统一接口)
     */
    applyPointCoordinates() {
        if (this.pointImageEditor.mode === 'bbox') {
            this.applyBboxCoordinates();
            return;
        }
        
        if (!this.pointImageEditor.currentFieldName || !this.currentParsedFields) {
            this.closePointImageEditor();
            return;
        }
        
        // 更新字段值
        if (!this.currentParsedFields.fields[this.pointImageEditor.currentFieldName]) {
            this.currentParsedFields.fields[this.pointImageEditor.currentFieldName] = {
                type: 'point',
                x: 0,
                y: 0
            };
        }
        
        this.currentParsedFields.fields[this.pointImageEditor.currentFieldName].x = this.pointImageEditor.selectedX;
        this.currentParsedFields.fields[this.pointImageEditor.currentFieldName].y = this.pointImageEditor.selectedY;
        
        // 关闭图片编辑器
        this.closePointImageEditor();
        
        // 重新渲染字段编辑器以显示新值
        const fieldsContainer = document.getElementById('dialog-parsed-fields');
        if (fieldsContainer && this.currentParsedFields) {
            this.renderFieldEditors(this.currentParsedFields, fieldsContainer);
            this.updateGeneratedEventStr();
        }
    }

    /**
     * 关闭图片编辑器 (统一接口)
     */
    closePointImageEditor() {
        if (this.pointImageEditor.mode === 'bbox') {
            this.closeBboxImageEditor();
            return;
        }
        
        if (this.pointImageEditor.overlay) {
            this.pointImageEditor.overlay.style.display = 'none';
        }
        
        // 重置状态
        this.pointImageEditor.mode = 'point';
        this.pointImageEditor.currentFieldName = null;
        this.pointImageEditor.currentImageSrc = null;
        this.pointImageEditor.selectedX = 0;
        this.pointImageEditor.selectedY = 0;
        this.pointImageEditor.zoomLevel = 1.0;
        this.pointImageEditor.originalImageSize = null;
        
        // 隐藏十字准线
        const crosshair = document.getElementById('point-editor-crosshair');
        if (crosshair) {
            crosshair.style.display = 'none';
        }
        
        // 隐藏任何可能显示的bbox选择框
        const selection = document.getElementById('bbox-selection');
        if (selection) {
            selection.style.display = 'none';
        }
        
        // 重置坐标标签为默认的point模式
        this.resetPointCoordinateLabels();
        
        // 隐藏预览元素
        this.hideBboxPreview();
        this.hidePointPreview();
    }

    /**
     * 计算合适的初始缩放比例
     */
    calculateInitialZoom() {
        const scrollContainer = document.getElementById('point-editor-scroll-container');
        const image = document.getElementById('point-editor-image');
        
        if (!scrollContainer || !image || !this.pointImageEditor.originalImageSize) {
            this.pointImageEditor.zoomLevel = 1.0;
            return;
        }
        
        // 使用固定的容器尺寸，不受当前图片大小影响
        // 基于对话框的实际可用空间计算固定尺寸
        const dialogContainer = scrollContainer.closest('.dialog-container');
        let containerWidth, containerHeight;
        
        if (dialogContainer) {
            // 对话框容器的可用空间（考虑各种边距和控件）
            const dialogRect = dialogContainer.getBoundingClientRect();
            containerWidth = Math.min(dialogRect.width - 60, 800); // 减去边距，最大800px
            containerHeight = 400 - 20; // 固定最大高度400px，减去边距
        } else {
            // 后备方案：使用固定尺寸
            containerWidth = 800;
            containerHeight = 380;
        }
        
        const imageWidth = this.pointImageEditor.originalImageSize.width;
        const imageHeight = this.pointImageEditor.originalImageSize.height;
        
        // 计算宽高缩放比例
        const scaleX = containerWidth / imageWidth;
        const scaleY = containerHeight / imageHeight;
        
        // 取较小的缩放比例以确保图片完全显示
        let scale = Math.min(scaleX, scaleY, 1.0); // 不超过原始大小
        
        // 设置最小缩放为0.1，最大为3.0
        scale = Math.max(0.1, Math.min(3.0, scale));
        
        this.pointImageEditor.zoomLevel = scale;
    }

    /**
     * 应用缩放
     */
    applyZoom() {
        const image = document.getElementById('point-editor-image');
        const zoomLevelSpan = document.getElementById('zoom-level');
        
        if (!image || !this.pointImageEditor.originalImageSize) return;
        
        const newWidth = this.pointImageEditor.originalImageSize.width * this.pointImageEditor.zoomLevel;
        const newHeight = this.pointImageEditor.originalImageSize.height * this.pointImageEditor.zoomLevel;
        
        image.style.width = newWidth + 'px';
        image.style.height = newHeight + 'px';
        
        // 更新十字准线大小
        this.updateCrosshairSize();
        
        // 更新缩放级别显示
        if (zoomLevelSpan) {
            zoomLevelSpan.textContent = Math.round(this.pointImageEditor.zoomLevel * 100) + '%';
        }
    }

    /**
     * 缩放图片
     */
    zoomImage(factor) {
        const newZoom = this.pointImageEditor.zoomLevel * factor;
        
        // 限制缩放范围
        if (newZoom < 0.1 || newZoom > 5.0) {
            return;
        }
        
        this.pointImageEditor.zoomLevel = newZoom;
        this.applyZoom();
        
        // 如果有十字准线，需要重新计算位置
        this.updateCrosshairAfterZoom();
    }

    /**
     * 重置缩放
     */
    resetZoom() {
        // 重新计算合适的缩放级别（基于原始图片尺寸和当前容器尺寸）
        this.calculateInitialZoom();
        this.applyZoom();
        this.updateCrosshairAfterZoom();
    }

    /**
     * 缩放后更新十字准线位置
     */
    updateCrosshairAfterZoom() {
        if (this.pointImageEditor.mode === 'point') {
            // 更新point模式的十字准线
            if (this.pointImageEditor.selectedX > 0 || this.pointImageEditor.selectedY > 0) {
                const image = document.getElementById('point-editor-image');
                if (image && this.pointImageEditor.originalImageSize) {
                    const rect = image.getBoundingClientRect();
                    
                    // 计算绝对坐标在当前显示图片上的位置
                    const x = (this.pointImageEditor.selectedX / this.pointImageEditor.originalImageSize.width) * rect.width;
                    const y = (this.pointImageEditor.selectedY / this.pointImageEditor.originalImageSize.height) * rect.height;
                    
                    this.setCrosshairPosition(x, y);
                }
            }
            // 更新bbox预览
            this.updateBboxPreviewAfterZoom();
        } else if (this.pointImageEditor.mode === 'bbox') {
            // 更新bbox模式的选择框
            this.updateBboxPreviewAfterZoom();
            // 更新point预览
            this.updatePointPreviewAfterZoom();
        }
    }

    /**
     * 缩放后更新bbox预览
     */
    updateBboxPreviewAfterZoom() {
        if (this.pointImageEditor.mode === 'bbox') {
            // bbox编辑模式下更新选择框
            if (this.pointImageEditor.bboxLeft !== undefined && this.pointImageEditor.bboxTop !== undefined && 
                this.pointImageEditor.bboxWidth !== undefined && this.pointImageEditor.bboxHeight !== undefined) {
                
                const image = document.getElementById('point-editor-image');
                if (image && this.pointImageEditor.originalImageSize) {
                    const rect = image.getBoundingClientRect();
                    // 计算绝对坐标在当前显示图片上的位置
                    const left = (this.pointImageEditor.bboxLeft / this.pointImageEditor.originalImageSize.width) * rect.width;
                    const top = (this.pointImageEditor.bboxTop / this.pointImageEditor.originalImageSize.height) * rect.height;
                    const width = (this.pointImageEditor.bboxWidth / this.pointImageEditor.originalImageSize.width) * rect.width;
                    const height = (this.pointImageEditor.bboxHeight / this.pointImageEditor.originalImageSize.height) * rect.height;
                    
                    this.setBboxSelection(left, top, left + width, top + height);
                }
            }
        } else if (this.pointImageEditor.mode === 'point') {
            // point编辑模式下更新bbox预览
            this.showBboxPreviewInPointMode();
        }
    }

    /**
     * 打开 bbox 字段的图片编辑器
     * @param {string} fieldName - 字段名称
     */
    openBboxImageEditor(fieldName) {
        if (!this.initBboxImageEditor()) {
            return;
        }

        this.pointImageEditor.currentFieldName = fieldName;
        this.pointImageEditor.mode = 'bbox';
        
        // 立即更新坐标标签，不等待图片加载
        this.updateBboxCoordinateLabels();
        
        // 获取当前状态的图片
        this.getCurrentStateImage().then(imageSrc => {
            if (imageSrc) {
                this.pointImageEditor.currentImageSrc = imageSrc;
                this.displayImageInBboxEditor(imageSrc);
                this.pointImageEditor.overlay.style.display = 'flex';
                
                // 设置标题
                const titleElement = document.getElementById('point-editor-title');
                if (titleElement) {
                    titleElement.textContent = `为 ${fieldName} 绘制边界框`;
                }

                // 更新说明文本
                const instructionsElement = document.getElementById('point-editor-instructions');
                if (instructionsElement) {
                    instructionsElement.innerHTML = '<strong>说明：</strong>点击并拖动图片，绘制带绝对像素坐标的边界框。可使用缩放按钮或 Ctrl+滚轮调整图片大小。';
                }
            } else {
                alert('无法加载状态截图进行编辑');
            }
        }).catch(error => {
            console.error('Error loading state image:', error);
            alert('加载状态截图失败：' + error.message);
        });
    }

    /**
     * 初始化bbox图片编辑器
     */
    initBboxImageEditor() {
        // 使用统一的初始化方法
        return this.initPointImageEditor();
    }

    /**
     * 在bbox编辑器中显示图片
     */
    displayImageInBboxEditor(imageSrc) {
        const image = document.getElementById('point-editor-image');
        if (image) {
            image.src = imageSrc;
            image.onload = () => {
                // 保存原始图片尺寸
                this.pointImageEditor.originalImageSize = {
                    width: image.naturalWidth,
                    height: image.naturalHeight
                };
                
                // 设置正确的事件监听器
                this.setupImageEventListeners();
                
                // 计算合适的初始缩放比例
                this.calculateInitialZoom();
                this.applyZoom();
                
                // 图片加载完成后，如果有当前字段的值，显示在图片上
                this.showCurrentBboxOnImage();
                
                // Show point preview in bbox mode
                this.showPointPreviewInBboxMode();
            };
        }
    }

    /**
     * 在图片上显示当前 bbox 的位置
     */
    showCurrentBboxOnImage() {
        if (!this.pointImageEditor.currentFieldName || !this.currentParsedFields) {
            return;
        }
        
        const fieldValue = this.currentParsedFields.fields[this.pointImageEditor.currentFieldName];
        if (fieldValue && fieldValue.type === 'bbox' && fieldValue.left !== undefined) {
            // 转换坐标为图片上的位置 - 使用绝对坐标
            const image = document.getElementById('point-editor-image');
            
            if (image && this.pointImageEditor.originalImageSize) {
                const rect = image.getBoundingClientRect();
                // 计算绝对坐标在当前显示图片上的位置
                const left = (fieldValue.left / this.pointImageEditor.originalImageSize.width) * rect.width;
                const top = (fieldValue.top / this.pointImageEditor.originalImageSize.height) * rect.height;
                const width = (fieldValue.width / this.pointImageEditor.originalImageSize.width) * rect.width;
                const height = (fieldValue.height / this.pointImageEditor.originalImageSize.height) * rect.height;
                
                // 创建bbox选择框以显示预览
                this.createBboxSelection();
                this.setBboxSelection(left, top, left + width, top + height);
                
                // 更新内部状态以与显示保持一致
                this.pointImageEditor.bboxLeft = fieldValue.left;
                this.pointImageEditor.bboxTop = fieldValue.top;
                this.pointImageEditor.bboxWidth = fieldValue.width;
                this.pointImageEditor.bboxHeight = fieldValue.height;
                
                // 更新坐标显示 (使用bbox专用的输入框)
                const leftInput = document.getElementById('bbox-editor-left');
                const topInput = document.getElementById('bbox-editor-top');
                const widthInput = document.getElementById('bbox-editor-width');
                const heightInput = document.getElementById('bbox-editor-height');
                
                if (leftInput) leftInput.value = fieldValue.left;
                if (topInput) topInput.value = fieldValue.top;
                if (widthInput) widthInput.value = fieldValue.width;
                if (heightInput) heightInput.value = fieldValue.height;
            }
        }
    }

    /**
     * 处理bbox鼠标按下事件
     */
    handleBboxMouseDown(event) {
        const image = event.target;
        const rect = image.getBoundingClientRect();
        
        // 计算相对于图片的点击位置
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        
        // 开始拖拽
        this.pointImageEditor.bboxDragging = true;
        this.pointImageEditor.bboxStartX = x;
        this.pointImageEditor.bboxStartY = y;
        this.pointImageEditor.bboxEndX = x;
        this.pointImageEditor.bboxEndY = y;
        
        // 创建或显示bbox选择框
        this.createBboxSelection();
        this.setBboxSelection(x, y, x, y);
        
        event.preventDefault();
    }

    /**
     * 处理bbox鼠标移动事件
     */
    handleBboxMouseMove(event) {
        if (!this.pointImageEditor.bboxDragging) return;
        
        const image = event.target;
        const rect = image.getBoundingClientRect();
        
        // 计算相对于图片的当前位置
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        
        this.pointImageEditor.bboxEndX = x;
        this.pointImageEditor.bboxEndY = y;
        
        // 更新bbox选择框
        this.setBboxSelection(
            this.pointImageEditor.bboxStartX,
            this.pointImageEditor.bboxStartY,
            x,
            y
        );
        
        // 实时更新坐标显示
        this.updateBboxCoordinateDisplay();
    }

    /**
     * 处理bbox鼠标抬起事件
     */
    handleBboxMouseUp() {
        if (!this.pointImageEditor.bboxDragging) return;
        
        this.pointImageEditor.bboxDragging = false;
        
        // 最终更新坐标显示
        this.updateBboxCoordinateDisplay();
    }

    /**
     * 创建bbox选择框
     */
    createBboxSelection() {
        let selection = document.getElementById('bbox-selection');
        if (!selection) {
            selection = document.createElement('div');
            selection.id = 'bbox-selection';
            selection.style.position = 'absolute';
            selection.style.border = '2px solid #ff4444';
            selection.style.backgroundColor = 'rgba(255, 68, 68, 0.15)';
            selection.style.pointerEvents = 'none';
            selection.style.zIndex = '10';
            selection.style.boxSizing = 'border-box';
            // 添加一些视觉效果使其更明显
            selection.style.boxShadow = '0 0 0 1px rgba(255, 255, 255, 0.8), 0 0 6px rgba(255, 68, 68, 0.5)';
            
            const imageContainer = document.getElementById('point-editor-image-container');
            if (imageContainer) {
                imageContainer.appendChild(selection);
            }
        }
        selection.style.display = 'block';
        return selection;
    }

    /**
     * 设置bbox选择框位置和大小
     */
    setBboxSelection(startX, startY, endX, endY) {
        const selection = document.getElementById('bbox-selection');
        if (!selection) return;
        
        // 确保左上角和右下角坐标正确
        const left = Math.min(startX, endX);
        const top = Math.min(startY, endY);
        const width = Math.abs(endX - startX);
        const height = Math.abs(endY - startY);
        
        selection.style.left = left + 'px';
        selection.style.top = top + 'px';
        selection.style.width = width + 'px';
        selection.style.height = height + 'px';
    }

    /**
     * 更新bbox坐标显示
     */
    updateBboxCoordinateDisplay() {
        const image = document.getElementById('point-editor-image');
        if (!image || !this.pointImageEditor.originalImageSize) return;
        
        const rect = image.getBoundingClientRect();
        
        // 计算bbox的左上角和大小
        const left = Math.min(this.pointImageEditor.bboxStartX, this.pointImageEditor.bboxEndX);
        const top = Math.min(this.pointImageEditor.bboxStartY, this.pointImageEditor.bboxEndY);
        const width = Math.abs(this.pointImageEditor.bboxEndX - this.pointImageEditor.bboxStartX);
        const height = Math.abs(this.pointImageEditor.bboxEndY - this.pointImageEditor.bboxStartY);
        
        // 转换为绝对坐标（基于原始图片尺寸）
        const absoluteLeft = Math.round((left / rect.width) * this.pointImageEditor.originalImageSize.width);
        const absoluteTop = Math.round((top / rect.height) * this.pointImageEditor.originalImageSize.height);
        const absoluteWidth = Math.round((width / rect.width) * this.pointImageEditor.originalImageSize.width);
        const absoluteHeight = Math.round((height / rect.height) * this.pointImageEditor.originalImageSize.height);
        
        // 确保坐标在有效范围内
        const finalLeft = Math.max(0, Math.min(this.pointImageEditor.originalImageSize.width, absoluteLeft));
        const finalTop = Math.max(0, Math.min(this.pointImageEditor.originalImageSize.height, absoluteTop));
        const finalWidth = Math.max(0, Math.min(this.pointImageEditor.originalImageSize.width - finalLeft, absoluteWidth));
        const finalHeight = Math.max(0, Math.min(this.pointImageEditor.originalImageSize.height - finalTop, absoluteHeight));
        
        // 更新存储的坐标
        this.pointImageEditor.bboxLeft = finalLeft;
        this.pointImageEditor.bboxTop = finalTop;
        this.pointImageEditor.bboxWidth = finalWidth;
        this.pointImageEditor.bboxHeight = finalHeight;
        
        // 更新坐标显示 (使用bbox专用的输入框)
        const leftInput = document.getElementById('bbox-editor-left');
        const topInput = document.getElementById('bbox-editor-top');
        const widthInput = document.getElementById('bbox-editor-width');
        const heightInput = document.getElementById('bbox-editor-height');
        
        if (leftInput) leftInput.value = finalLeft;
        if (topInput) topInput.value = finalTop;
        if (widthInput) widthInput.value = finalWidth;
        if (heightInput) heightInput.value = finalHeight;
    }

    /**
     * 更新为bbox坐标显示
     */
    updateBboxCoordinateLabels() {
        // 查找坐标容器并替换为bbox版本
        const coordContainer = document.querySelector('#point-editor-x').closest('.row').parentNode;
        if (!coordContainer) return;
        
        // 检查是否已经是bbox模式
        if (document.getElementById('bbox-editor-left')) {
            // 已经是bbox模式，只需要更新数值
            this.fillCurrentBboxValues();
            return;
        }
        
        // 替换为bbox坐标显示
        const bboxCoordHTML = `
            <div class="row">
                <div class="col-md-6">
                    <label>区域左边界坐标：</label>
                    <input type="number" id="bbox-editor-left" class="form-control" readonly style="background-color: #f9f9f9;" />
                </div>
                <div class="col-md-6">
                    <label>区域上边界坐标：</label>
                    <input type="number" id="bbox-editor-top" class="form-control" readonly style="background-color: #f9f9f9;" />
                </div>
            </div>
            <div class="row" style="margin-top: 10px;">
                <div class="col-md-6">
                    <label>区域宽度：</label>
                    <input type="number" id="bbox-editor-width" class="form-control" readonly style="background-color: #f9f9f9;" />
                </div>
                <div class="col-md-6">
                    <label>区域高度：</label>
                    <input type="number" id="bbox-editor-height" class="form-control" readonly style="background-color: #f9f9f9;" />
                </div>
            </div>
            <div class="row" style="margin-top: 10px;">
                <div class="col-md-12">
                    <small class="text-muted">坐标为基于原图尺寸的绝对像素值。</small>
                </div>
            </div>
        `;
        
        // 保存原始HTML以便恢复
        if (!this.originalPointCoordHTML) {
            this.originalPointCoordHTML = coordContainer.innerHTML;
        }
        
        coordContainer.innerHTML = bboxCoordHTML;
        
        // 立即填充当前bbox字段的值
        this.fillCurrentBboxValues();
    }

    /**
     * 填充当前bbox字段的值
     */
    fillCurrentBboxValues() {
        if (!this.pointImageEditor.currentFieldName || !this.currentParsedFields) {
            return;
        }
        
        const fieldValue = this.currentParsedFields.fields[this.pointImageEditor.currentFieldName];
        if (fieldValue && fieldValue.type === 'bbox') {
            // 更新所有bbox相关的输入框
            const leftInput = document.getElementById('bbox-editor-left');
            const topInput = document.getElementById('bbox-editor-top');
            const widthInput = document.getElementById('bbox-editor-width');
            const heightInput = document.getElementById('bbox-editor-height');
            
            if (leftInput && fieldValue.left !== undefined) leftInput.value = fieldValue.left;
            if (topInput && fieldValue.top !== undefined) topInput.value = fieldValue.top;
            if (widthInput && fieldValue.width !== undefined) widthInput.value = fieldValue.width;
            if (heightInput && fieldValue.height !== undefined) heightInput.value = fieldValue.height;
        }
    }

    /**
     * 重置坐标标签为point模式
     */
    resetPointCoordinateLabels() {
        // 如果有原始HTML，则恢复它
        if (this.originalPointCoordHTML) {
            const coordContainer = document.querySelector('#bbox-editor-left, #point-editor-x')?.closest('.row')?.parentNode;
            if (coordContainer) {
                coordContainer.innerHTML = this.originalPointCoordHTML;
            }
        }
        
        // 清理可能存在的旧的bbox字段
        const bboxRow = document.getElementById('bbox-coordinates-row');
        if (bboxRow) {
            bboxRow.remove();
        }
        
        const oldBboxDivs = document.querySelectorAll('.bbox-width, .bbox-height');
        oldBboxDivs.forEach(div => {
            const row = div.closest('.row');
            if (row) {
                row.remove();
            }
        });
    }

    /**
     * 应用选择的bbox坐标
     */
    applyBboxCoordinates() {
        if (!this.pointImageEditor.currentFieldName || !this.currentParsedFields) {
            this.closeBboxImageEditor();
            return;
        }
        
        // 更新字段值
        if (!this.currentParsedFields.fields[this.pointImageEditor.currentFieldName]) {
            this.currentParsedFields.fields[this.pointImageEditor.currentFieldName] = {
                type: 'bbox',
                left: 0,
                top: 0,
                width: 0,
                height: 0
            };
        }
        
        this.currentParsedFields.fields[this.pointImageEditor.currentFieldName].left = this.pointImageEditor.bboxLeft || 0;
        this.currentParsedFields.fields[this.pointImageEditor.currentFieldName].top = this.pointImageEditor.bboxTop || 0;
        this.currentParsedFields.fields[this.pointImageEditor.currentFieldName].width = this.pointImageEditor.bboxWidth || 0;
        this.currentParsedFields.fields[this.pointImageEditor.currentFieldName].height = this.pointImageEditor.bboxHeight || 0;
        
        // 关闭图片编辑器
        this.closeBboxImageEditor();
        
        // 重新渲染字段编辑器以显示新值
        const fieldsContainer = document.getElementById('dialog-parsed-fields');
        if (fieldsContainer && this.currentParsedFields) {
            this.renderFieldEditors(this.currentParsedFields, fieldsContainer);
            this.updateGeneratedEventStr();
        }
    }

    /**
     * 关闭bbox图片编辑器
     */
    closeBboxImageEditor() {
        if (this.pointImageEditor.overlay) {
            this.pointImageEditor.overlay.style.display = 'none';
        }
        
        // 重置状态
        this.pointImageEditor.mode = 'point';
        this.pointImageEditor.currentFieldName = null;
        this.pointImageEditor.currentImageSrc = null;
        this.pointImageEditor.bboxDragging = false;
        this.pointImageEditor.bboxStartX = 0;
        this.pointImageEditor.bboxStartY = 0;
        this.pointImageEditor.bboxEndX = 0;
        this.pointImageEditor.bboxEndY = 0;
        this.pointImageEditor.zoomLevel = 1.0;
        this.pointImageEditor.originalImageSize = null;
        
        // 重置bbox相关坐标属性
        this.pointImageEditor.bboxLeft = 0;
        this.pointImageEditor.bboxTop = 0;
        this.pointImageEditor.bboxWidth = 0;
        this.pointImageEditor.bboxHeight = 0;
        
        // 隐藏bbox选择框
        const selection = document.getElementById('bbox-selection');
        if (selection) {
            selection.style.display = 'none';
        }
        
        // 恢复鼠标样式
        const image = document.getElementById('point-editor-image');
        if (image) {
            image.style.cursor = 'crosshair';
        }
        
        // 重置坐标标签为默认的point模式
        this.resetPointCoordinateLabels();
        
        // 隐藏预览元素
        this.hideBboxPreview();
        this.hidePointPreview();
    }

    /**
     * 在 point 编辑模式下显示 bbox 字段的预览
     */
    showBboxPreviewInPointMode() {
        if (!this.currentParsedFields || this.pointImageEditor.mode !== 'point') {
            return;
        }

        // 查找所有 bbox 字段
        const bboxFields = Object.entries(this.currentParsedFields.fields).filter(([, fieldValue]) => 
            fieldValue && fieldValue.type === 'bbox' && 
            fieldValue.left !== undefined && fieldValue.top !== undefined &&
            fieldValue.width !== undefined && fieldValue.height !== undefined &&
            fieldValue.left >= 0 && fieldValue.top >= 0 && fieldValue.width > 0 && fieldValue.height > 0
        );

        if (bboxFields.length === 0) {
            this.hideBboxPreview();
            return;
        }

        const image = document.getElementById('point-editor-image');
        if (!image || !this.pointImageEditor.originalImageSize) {
            return;
        }

        const rect = image.getBoundingClientRect();
        
        // 为每个 bbox 字段创建预览
        bboxFields.forEach(([fieldName, fieldValue], index) => {
            // 计算绝对坐标在当前显示图片上的位置
            const left = (fieldValue.left / this.pointImageEditor.originalImageSize.width) * rect.width;
            const top = (fieldValue.top / this.pointImageEditor.originalImageSize.height) * rect.height;
            const width = (fieldValue.width / this.pointImageEditor.originalImageSize.width) * rect.width;
            const height = (fieldValue.height / this.pointImageEditor.originalImageSize.height) * rect.height;

            this.createBboxPreview(fieldName, left, top, width, height, index);
        });
    }

    /**
     * 创建 bbox 预览框
     */
    createBboxPreview(fieldName, left, top, width, height, index) {
        const previewId = `bbox-preview-${index}`;
        let preview = document.getElementById(previewId);
        
        if (!preview) {
            preview = document.createElement('div');
            preview.id = previewId;
            preview.style.position = 'absolute';
            preview.style.border = '2px dashed #007bff';
            preview.style.backgroundColor = 'rgba(0, 123, 255, 0.1)';
            preview.style.pointerEvents = 'none';
            preview.style.zIndex = '5';
            preview.style.boxSizing = 'border-box';

            const imageContainer = document.getElementById('point-editor-image-container');
            if (imageContainer) {
                imageContainer.appendChild(preview);
            }
        }

        preview.style.left = left + 'px';
        preview.style.top = top + 'px';
        preview.style.width = width + 'px';
        preview.style.height = height + 'px';
        preview.style.display = 'block';
    }

    /**
     * 隐藏 bbox 预览
     */
    hideBboxPreview() {
        // 移除所有 bbox 预览
        for (let i = 0; i < 10; i++) { // 假设最多10个bbox字段
            const preview = document.getElementById(`bbox-preview-${i}`);
            if (preview) {
                preview.remove();
            }
        }
    }

    /**
     * 在 bbox 编辑模式下显示 point 字段的预览
     */
    showPointPreviewInBboxMode() {
        if (!this.currentParsedFields || this.pointImageEditor.mode !== 'bbox') {
            return;
        }

        // 查找所有 point 字段
        const pointFields = Object.entries(this.currentParsedFields.fields).filter(([, fieldValue]) => 
            fieldValue && fieldValue.type === 'point' && 
            fieldValue.x !== undefined && fieldValue.y !== undefined &&
            fieldValue.x >= 0 && fieldValue.y >= 0
        );

        if (pointFields.length === 0) {
            this.hidePointPreview();
            return;
        }

        const image = document.getElementById('point-editor-image');
        if (!image || !this.pointImageEditor.originalImageSize) {
            return;
        }

        const rect = image.getBoundingClientRect();
        
        // 为每个 point 字段创建预览
        pointFields.forEach(([fieldName, fieldValue], index) => {
            // 计算绝对坐标在当前显示图片上的位置
            const x = (fieldValue.x / this.pointImageEditor.originalImageSize.width) * rect.width;
            const y = (fieldValue.y / this.pointImageEditor.originalImageSize.height) * rect.height;

            this.createPointPreview(fieldName, x, y, index);
        });
    }

    /**
     * 创建 point 预览圆圈
     */
    createPointPreview(fieldName, x, y, index) {
        const previewId = `point-preview-${index}`;
        let preview = document.getElementById(previewId);
        
        if (!preview) {
            preview = document.createElement('div');
            preview.id = previewId;
            preview.style.position = 'absolute';
            preview.style.border = '2px dashed #007bff';
            preview.style.backgroundColor = 'rgba(0, 123, 255, 0.1)';
            preview.style.borderRadius = '50%';
            preview.style.pointerEvents = 'none';
            preview.style.zIndex = '5';
            preview.style.width = '20px';
            preview.style.height = '20px';
            preview.style.marginLeft = '-10px';
            preview.style.marginTop = '-10px';

            const imageContainer = document.getElementById('point-editor-image-container');
            if (imageContainer) {
                imageContainer.appendChild(preview);
            }
        }

        preview.style.left = x + 'px';
        preview.style.top = y + 'px';
        preview.style.display = 'block';
    }

    /**
     * 隐藏 point 预览
     */
    hidePointPreview() {
        // 移除所有 point 预览
        for (let i = 0; i < 10; i++) { // 假设最多10个point字段
            const preview = document.getElementById(`point-preview-${i}`);
            if (preview) {
                preview.remove();
            }
        }
    }

    /**
     * 缩放后更新 point 预览位置
     */
    updatePointPreviewAfterZoom() {
        if (!this.currentParsedFields || this.pointImageEditor.mode !== 'bbox') {
            return;
        }

        // 重新显示 point 预览以更新位置
        this.showPointPreviewInBboxMode();
    }
}

// Create global instance
window.eventEditDialog = new EventEditDialog();

// Ensure initialization when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (window.eventEditDialog) {
        window.eventEditDialog.init();
        console.log('EventEditDialog initialized');
    }
});
