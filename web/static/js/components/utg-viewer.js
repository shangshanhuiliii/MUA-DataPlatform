class UTGViewer {
    constructor(containerId, detailsId) {
        this.container = document.getElementById(containerId);
        // Use the sidebar content area for details instead of original detailsId
        this.detailsPanel = document.getElementById('utg_details_content');
        this.network = null;
        this.utg = null;
        this.showGlobalEventId = false; // Default to showing local event sequence numbers

        // Initialize editors
        this.nodeEditor = null;

        // Task Info properties
        this.taskInfoPanel = null;
        this.taskInfoContent = null;
        this.taskInfoCodeMirror = null;  // CodeMirror instance
        this.taskInfoEditBtn = null;
        this.taskInfoSaveBtn = null;
        this.taskInfoCancelBtn = null;
        this.taskInfoCollapseBtn = null;
        this.taskInfoDatasetName = null;
        this.taskInfoStatus = null;
        this.taskInfoLoaded = false;
        this.taskInfoEditMode = false;
        this.taskInfoCollapsed = true;  // Default to collapsed
        this.activeRecordingName = null;
        this.cachedProcessedData = null;// 缓存处理后的UTG数据
        this.lastUtg = null;// 上一次的UTG原始数据
        this.lastShowGlobal = null;// 上一次的显示模式（全局/本地ID）
        // Create floating control panel
        this.createFloatingControls();

        // Create Task Info panel (always exists, even without content)
        this.createTaskInfoPanel();

        // Setup keyboard shortcuts
        this.setupKeyboardShortcuts();
    }

    createFloatingControls() {
        // Remove existing controls if any
        const existingControls = document.getElementById('utg-floating-controls');
        if (existingControls) {
            existingControls.remove();
        }

        // Detect platform for modifier key display
        const isMac = /Mac|iPhone|iPod|iPad/.test(navigator.userAgent);
        const modKey = isMac ? '⌘' : 'Alt';

        // Create floating control panel
        const controlPanel = document.createElement('div');
        controlPanel.id = 'utg-floating-controls';
        controlPanel.className = 'utg-floating-controls';

        controlPanel.innerHTML = `
            <div class="utg-controls-section utg-shortcuts-section">
                <div class="utg-controls-title" style="cursor: pointer; display: flex; justify-content: space-between; align-items: center;" id="shortcuts-toggle">
                    <span>快捷键</span>
                    <span class="glyphicon glyphicon-chevron-up" id="shortcuts-icon"></span>
                </div>
                <div id="shortcuts-content" class="shortcuts-collapsed">
                    <div class="shortcut-item"><kbd>W</kbd> <span>上一个节点</span></div>
                    <div class="shortcut-item"><kbd>D</kbd> <span>删除节点</span></div>
                    <div class="shortcut-item"><kbd>S</kbd> <span>下一个节点</span></div>
                    <div class="shortcut-item"><kbd>${modKey}+D</kbd> <span>删除分支</span></div>
                    <div class="shortcut-item"><kbd>A</kbd> <span>添加事件</span></div>
                    <div class="shortcut-item"><kbd>F</kbd> <span>设为首状态</span></div>
                    <div class="shortcut-item"><kbd>E</kbd> <span>编辑第 1 个事件</span></div>
                    <div class="shortcut-item"><kbd>${modKey}+F</kbd> <span>设为末状态</span></div>
                    <div class="shortcut-item"><kbd>1-9</kbd> <span>编辑第 N 个事件</span></div>
                    <div class="shortcut-item"><kbd>T</kbd> <span>编辑状态标签</span></div>
                </div>
            </div>

            <div class="utg-controls-separator"></div>

            <div class="utg-controls-section utg-display-options-section">
                <div class="utg-controls-title" style="cursor: pointer; display: flex; justify-content: space-between; align-items: center;" id="display-options-toggle">
                    <span>显示选项</span>
                    <span class="glyphicon glyphicon-chevron-up" id="display-options-icon"></span>
                </div>
                <div id="display-options-content" class="display-options-collapsed">
                    <label class="utg-controls-checkbox-container">
                        <input type="checkbox" id="global-event-id-checkbox"
                               ${this.showGlobalEventId ? 'checked' : ''}
                               class="utg-controls-checkbox">
                        <span>全局事件 ID</span>
                    </label>
                    <div class="utg-controls-description">
                        ${this.showGlobalEventId ? '当前显示全局事件 ID' : '当前显示源状态内事件序号'}
                    </div>
                </div>
            </div>
        `;

        // Add event listener for checkbox
        const checkbox = controlPanel.querySelector('#global-event-id-checkbox');
        checkbox.addEventListener('change', (e) => {
            this.toggleEdgeLabelMode(e.target.checked);
        });

        // Add toggle functionality for shortcuts section
        const shortcutsToggle = controlPanel.querySelector('#shortcuts-toggle');
        const shortcutsContent = controlPanel.querySelector('#shortcuts-content');
        const shortcutsIcon = controlPanel.querySelector('#shortcuts-icon');

        shortcutsToggle.addEventListener('click', () => {
            const isCollapsed = shortcutsContent.classList.contains('shortcuts-collapsed');
            if (isCollapsed) {
                shortcutsContent.classList.remove('shortcuts-collapsed');
                shortcutsIcon.className = 'glyphicon glyphicon-chevron-down';
            } else {
                shortcutsContent.classList.add('shortcuts-collapsed');
                shortcutsIcon.className = 'glyphicon glyphicon-chevron-up';
            }
        });

        // Add toggle functionality for display options section
        const displayOptionsToggle = controlPanel.querySelector('#display-options-toggle');
        const displayOptionsContent = controlPanel.querySelector('#display-options-content');
        const displayOptionsIcon = controlPanel.querySelector('#display-options-icon');

        displayOptionsToggle.addEventListener('click', () => {
            const isCollapsed = displayOptionsContent.classList.contains('display-options-collapsed');
            if (isCollapsed) {
                displayOptionsContent.classList.remove('display-options-collapsed');
                displayOptionsIcon.className = 'glyphicon glyphicon-chevron-down';
            } else {
                displayOptionsContent.classList.add('display-options-collapsed');
                displayOptionsIcon.className = 'glyphicon glyphicon-chevron-up';
            }
        });

        // Append to the UTG div container for proper relative positioning
        const utgDiv = document.getElementById('utg_div');
        if (utgDiv) {
            // Ensure the UTG div has relative positioning for absolute positioning to work
            if (getComputedStyle(utgDiv).position === 'static') {
                utgDiv.style.position = 'relative';
            }
            utgDiv.appendChild(controlPanel);
            console.log('Control panel appended to utg_div with relative positioning');
        } else {
            // Fallback: append to body with fixed positioning
            controlPanel.classList.add('utg-floating-controls--fallback');
            document.body.appendChild(controlPanel);
            console.log('Control panel appended to body (fallback)');
        }

        // Double check the panel is in the DOM
        setTimeout(() => {
            const addedPanel = document.getElementById('utg-floating-controls');
            console.log('Control panel in DOM:', !!addedPanel);
            if (addedPanel) {
                console.log('Panel classes:', addedPanel.className);
            }
        }, 100);
    }

    createTaskInfoPanel() {
        // Remove existing panel if any
        const existingPanel = document.getElementById('task-info-floating-panel');
        if (existingPanel) {
            existingPanel.remove();
        }

        // Create Task Info floating panel
        const panel = document.createElement('div');
        panel.id = 'task-info-floating-panel';
        panel.className = 'task-info-floating-panel';
        panel.style.display = 'none';

        panel.innerHTML = `
            <div class="task-info-header">
                <div class="task-info-title">
                    <span id="task-info-dataset-name" class="task-info-dataset-name">录制数据</span>
                </div>
                <button id="task-info-collapse-btn"
                        class="btn btn-sm btn-default"
                        title="折叠/展开"
                        style="padding: 0; margin: 0;">
                    <span class="glyphicon glyphicon-chevron-down"></span>
                </button>
            </div>
            <div id="task-info-content" class="task-info-content" style="display: none;">
                <div id="task-info-codemirror-container" class="task-info-codemirror-container"></div>
                <div class="task-info-actions">
                    <button id="task-info-edit-btn" class="btn btn-sm btn-primary">编辑</button>
                    <button id="task-info-save-btn" class="btn btn-sm btn-success" style="display: none;">保存</button>
                    <button id="task-info-cancel-btn" class="btn btn-sm btn-default" style="display: none;">取消</button>
                    <span id="task-info-status" class="text-muted" style="font-size: 11px;"></span>
                    <button id="restore-nodes-btn" class="btn btn-sm btn-primary">召回已删除节点</button>
                </div>
            </div>
        `;

        // Append to the UTG div container
        const utgDiv = document.getElementById('utg_div');
        if (utgDiv) {
            if (getComputedStyle(utgDiv).position === 'static') {
                utgDiv.style.position = 'relative';
            }
            utgDiv.appendChild(panel);
        }

        // Initialize element references
        this.taskInfoPanel = document.getElementById('task-info-floating-panel');
        this.taskInfoContent = document.getElementById('task-info-content');
        this.taskInfoEditBtn = document.getElementById('task-info-edit-btn');
        this.taskInfoSaveBtn = document.getElementById('task-info-save-btn');
        this.taskInfoCancelBtn = document.getElementById('task-info-cancel-btn');
        this.taskInfoCollapseBtn = document.getElementById('task-info-collapse-btn');
        this.taskInfoDatasetName = document.getElementById('task-info-dataset-name');
        this.taskInfoStatus = document.getElementById('task-info-status');
        this.restoreBtn = document.getElementById('restore-nodes-btn');
        
        // Initialize CodeMirror
        this.initializeCodeMirror();

        // Bind events
        this.bindTaskInfoEvents();
    }

    initializeCodeMirror() {
        const container = document.getElementById('task-info-codemirror-container');
        if (!container) {
            console.error('CodeMirror container not found');
            return;
        }

        // Create CodeMirror instance
        this.taskInfoCodeMirror = CodeMirror(container, {
            mode: 'yaml',
            theme: 'default',
            lineNumbers: true,
            lineWrapping: false,
            readOnly: true,
            tabSize: 2,              // Tab 显示为 2 个空格宽度
            indentUnit: 2,           // 缩进单位为 2 个空格
            indentWithTabs: false,   // 使用空格而不是 Tab 字符
            placeholder: '开始录制或选择录制数据后，这里会显示任务信息...',
            viewportMargin: Infinity,  // Render all lines
            extraKeys: {
                'Tab': function(cm) {
                    // 如果有选中的文本，缩进选中的行；否则插入空格
                    if (cm.somethingSelected()) {
                        cm.indentSelection('add');  // 正向缩进文本
                    } else {
                        // 整行缩进，不符合预期
                        // cm.indentLine(cm.getCursor().line, "add");
                        // 光标处插入 indentUnit 个空格
                        cm.replaceSelection(Array(cm.getOption("indentUnit") + 1).join(" "), "end", "+input");
                    }
                },
                'Shift-Tab': function(cm) {
                    // 反向缩进
                    if (cm.somethingSelected()) {
                        cm.indentSelection('subtract');  // 反向缩进
                    } else {
                        // 直接缩进整行
                        cm.indentLine(cm.getCursor().line, "subtract");
                    }
                    return;
                }
            }
        });

        // Set initial height
        this.taskInfoCodeMirror.setSize(null, '250px');
    }

    bindTaskInfoEvents() {
        const self = this;

        // Edit button
        if (this.taskInfoEditBtn) {
            this.taskInfoEditBtn.addEventListener('click', function() {
                self.enterTaskInfoEditMode();
            });
        }

        // Save button
        if (this.taskInfoSaveBtn) {
            this.taskInfoSaveBtn.addEventListener('click', function() {
                self.saveTaskInfo();
            });
        }

        // Cancel button
        if (this.taskInfoCancelBtn) {
            this.taskInfoCancelBtn.addEventListener('click', function() {
                self.cancelTaskInfoEdit();
            });
        }

        // Collapse/Expand button
        if (this.taskInfoCollapseBtn) {
            this.taskInfoCollapseBtn.addEventListener('click', function() {
                self.toggleTaskInfoCollapse();
            });
        }
        // Restore Deleted Nodes button
        if (this.restoreBtn) {
            this.restoreBtn.addEventListener('click', () =>{
                const dialog = new DeletedNodesDialog();
                dialog.open();
            });
        }
    }

    toggleEdgeLabelMode(showGlobal) {
        this.showGlobalEventId = showGlobal;

        // Update the description text
        const controlPanel = document.getElementById('utg-floating-controls');
        if (controlPanel) {
            const description = controlPanel.querySelector('.utg-controls-description');
            if (description) {
                description.textContent = showGlobal ?
                    '当前显示全局事件 ID' :
                    '当前显示源状态内事件序号';
            }
        }

        // Regenerate UTG data with new edge labels
        if (this.utg && this.network) {
            // Save currently selected nodes before redrawing
            const selectedNodes = this.network.getSelectedNodes();

            const processedData = this.processUTGData(this.utg);
            this.network.setData(processedData);
            this.network.redraw();

            // Restore node selection after redrawing
            if (selectedNodes.length > 0) {
                this.network.selectNodes(selectedNodes);
            }
        }
    }

    async loadUTG() {
        try {
            // ✅ 清理旧的 UTG 引用以便 GC 回收
            this.utg = null;

            this.utg = await api.getUTG();
            this.initializeEditors();
            this.draw();

            // Ensure floating controls are created after UTG is loaded
            // This is important because the container might not be ready during constructor
            if (!document.getElementById('utg-floating-controls')) {
                console.log('Creating floating controls after UTG load...');
                this.createFloatingControls();
            }

        } catch (error) {
            console.error('Failed to load UTG data:', error);
            if (this.isWorkspaceScopedError(error)) {
                this.resetWorkspaceState();
            }
            this.showError('从服务器加载 UTG 数据失败。');
        }
    }

    initializeEditors() {
        // Initialize editors after UTG data is loaded
        if (!this.detailsPanel) {
            // No details panel available, skip editor initialization
            return;
        }
        
        if (!this.nodeEditor) {
            this.nodeEditor = new NodeEditor(this.detailsPanel.id, this);
            // Make it globally accessible for onclick handlers
            window.nodeEditor = this.nodeEditor;
        }
        
    }

    processUTGData(utgData) {
        if (!utgData || !utgData.nodes) return utgData;
        
        if (this.cachedProcessedData && 
            this.lastUtg === utgData && 
            this.lastShowGlobal === this.showGlobalEventId) {
            return this.cachedProcessedData;
        } 

        // Create a copy to avoid modifying original data
        const displayUtg = JSON.parse(JSON.stringify(utgData));
        
        // Add numbers to node labels for display only
        for (let i = 0; i < displayUtg.nodes.length; i++) {
            const node = displayUtg.nodes[i];
            const nodeNumber = i + 1;
            
            // Add number prefix to label for display
            node.label = nodeNumber + ". " + node.label;

            //调用NodeEditor的组件生成悬停预览
            const imageComponent = window.nodeEditor.createEventVisualizationImage(node, 270, 'hover');
            const textComponent = window.nodeEditor.createEventTextPreview(node, 270);
            node.title = `
                <div style="width: fit-content; padding: 6px; background: white; border-radius: 6px;">
                    ${imageComponent}
                    <div style="margin-top: 6px;">
                        ${textComponent}
                    </div>
                </div>
            `;            
        }
        
        // Process edge labels based on display mode
        this.processEdgeLabels(displayUtg);

        this.cachedProcessedData = displayUtg;
        this.lastUtg = utgData;
        this.lastShowGlobal = this.showGlobalEventId;

        return displayUtg;
    }

    processEdgeLabels(utgData) {
        if (!utgData || !utgData.edges) return;
        
        if (this.showGlobalEventId) {
            // Use original global event IDs (already in data)
            // No change needed as backend already provides global event_id in labels
            return;
        }
        
        // Generate from_state event sequence numbers
        // Group edges by from_state and calculate local sequence numbers
        const fromStateEventMap = new Map();
        
        // First pass: collect all events from each state and sort by global event_id
        for (const edge of utgData.edges) {
            if (!edge.events || !Array.isArray(edge.events)) continue;
            
            const fromState = edge.from;
            if (!fromStateEventMap.has(fromState)) {
                fromStateEventMap.set(fromState, []);
            }
            
            for (const event of edge.events) {
                fromStateEventMap.get(fromState).push({
                    event_id: event.event_id,
                    edge_id: edge.id,
                    event_str: event.event_str
                });
            }
        }
        
        // Sort events by global event_id for each from_state
        for (const [fromState, events] of fromStateEventMap) {
            events.sort((a, b) => a.event_id - b.event_id);
        }
        
        // Second pass: update edge labels with local sequence numbers
        for (const edge of utgData.edges) {
            if (!edge.events || !Array.isArray(edge.events)) continue;
            
            const fromState = edge.from;
            const stateEvents = fromStateEventMap.get(fromState);
            const localSequenceNumbers = [];
            
            for (const event of edge.events) {
                // Find this event's position in the from_state's event sequence
                const localIndex = stateEvents.findIndex(e => e.event_id === event.event_id && e.event_str === event.event_str);
                if (localIndex !== -1) {
                    localSequenceNumbers.push(localIndex + 1); // 1-based indexing
                }
            }
            
            // Update edge label with local sequence numbers
            edge.label = localSequenceNumbers.join(', ');
        }
    }

    addNodeNumbers(utgData) {
        // Keep this method for backward compatibility, but use the new processUTGData
        return this.processUTGData(utgData);
    }

    getNodeDisplayLabel(nodeId) {
        if (!this.utg || !this.utg.nodes) return nodeId;
        
        for (let i = 0; i < this.utg.nodes.length; i++) {
            const node = this.utg.nodes[i];
            if (node.id === nodeId) {
                const nodeNumber = i + 1;
                return nodeNumber + ". " + node.label;
            }
        }
        return nodeId;
    }

    draw() {
        if (!this.utg) {
            this.showError('当前没有可用的 UTG 数据。');
            return;
        }

        const processedData = this.processUTGData(this.utg);

        if (!this.network) {
            // 首次初始化network实例
            const options = {
                autoResize: true,
                height: '100%',
                width: '100%',
                locale: 'en',

                nodes: {
                    shapeProperties: {
                        useBorderWithImage: true
                    },
                    borderWidth: 0,
                    borderWidthSelected: 5,
                    color: {
                        border: '#FFFFFF',
                        background: '#FFFFFF',
                        highlight: {
                            border: '#0000FF',
                            background: '#0000FF',
                        }
                    },
                    font: {
                        size: 12,
                        color: '#000'
                    }
                },
                edges: {
                    color: 'black',
                    arrows: {
                        to: {
                            enabled: true,
                            scaleFactor: 0.5
                        }
                    },
                    font: {
                        size: 12,
                        color: '#000'
                    }
                }
            };
            this.network = new vis.Network(this.container, processedData, options);
            this.setupEventHandlers();
        } else {
            // 增量更新数据，不重建实例
            const selectedNodes = this.network.getSelectedNodes();
            this.network.setData(processedData);// 更新数据
            this.network.redraw();
            // 重新draw后回复节点选择
            if (selectedNodes.length > 0) {
                this.network.selectNodes(selectedNodes);
            }
        }
    }

    setupEventHandlers() {
        if (this.eventHandlersBound) return;//防止多次调用draw方法导致的重复绑定click事件，避免多次执行
        this.network.on("click", (params) => {
            if (params.nodes.length > 0) {
                const node = params.nodes[0];

                // Show sidebar and use NodeEditor to show node details
                    window.showDetailsSidebar('节点详情', '');
                this.nodeEditor.showNodeDetails(node);
            } else if (params.edges.length > 0) {
                const edge = params.edges[0];
                const baseEdge = this.network.clustering.getBaseEdge(edge);
                const edgeToShow = baseEdge == null || baseEdge == edge ? edge : baseEdge;

                // Find the from_state node for this edge and show its NodeEditor
                const edgeData = this.utg.edges.find(e => e.id === edgeToShow);
                if (edgeData && edgeData.from) {
                    // Show sidebar and use NodeEditor to show from_state node details
                    window.showDetailsSidebar('起始状态详情', '');
                    this.nodeEditor.showNodeDetails(edgeData.from);
                }
            }
        });
        this.eventHandlersBound = true;
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ignore shortcuts if editing in text input fields, textareas, or CodeMirror
            // But allow shortcuts for checkboxes, radio buttons, etc.
            const activeElement = document.activeElement;
            const isTextInput = activeElement.tagName === 'INPUT' &&
                !['checkbox', 'radio', 'button', 'submit', 'reset', 'file', 'image', 'color', 'range'].includes(activeElement.type);

            if (isTextInput ||
                activeElement.tagName === 'TEXTAREA' ||
                activeElement.isContentEditable ||
                activeElement.closest('.CodeMirror')) {
                return;
            }

            // Get currently selected node
            if (!this.network) return;
            const selectedNodes = this.network.getSelectedNodes();
            if (selectedNodes.length !== 1) return;

            const nodeId = selectedNodes[0];
            const isMac = /Mac|iPhone|iPod|iPad/.test(navigator.userAgent);
            const modifierKey = isMac ? e.metaKey : e.altKey;

            // Handle Number (1-9) for editing nth event
            if (/^[1-9]$/.test(e.key)) {
                e.preventDefault();
                // Release focus before opening dialog
                this.releaseFocus();
                const eventIndex = parseInt(e.key, 10);
                this.editNthEvent(nodeId, eventIndex);
                return;
            }

            // Release focus BEFORE handling shortcuts that open dialogs
            // This ensures tooltip is hidden before dialogs are displayed
            // Only release for shortcuts that open dialogs/modals
            const shortcutsThatOpenDialogs = ['a', 'e', 't', '1', '2', '3', '4', '5', '6', '7', '8', '9'];
            if (shortcutsThatOpenDialogs.includes(e.key.toLowerCase())) {
                this.releaseFocus();
            }

            // Handle keyboard shortcuts
            switch(e.key.toLowerCase()) {
                case 'd':
                    e.preventDefault();
                    if (modifierKey) {
                        // Alt/Command + D: Delete Branch
                        this.nodeEditor.deleteBranch(nodeId);
                    } else {
                        // D: Delete Node
                        this.nodeEditor.deleteNode(nodeId);
                    }
                    break;

                case 'a':
                    e.preventDefault();
                    // A: Add Event
                    this.nodeEditor.addNewEvent(nodeId);
                    break;

                case 'e':
                    e.preventDefault();
                    // E: Edit first event
                    this.editFirstEvent(nodeId);
                    break;

                case 'f':
                    e.preventDefault();
                    if (modifierKey) {
                        // Alt/Command + F: Set Last State
                        this.nodeEditor.setLastState(nodeId);
                    } else {
                        // F: Set First State
                        this.nodeEditor.setFirstState(nodeId);
                    }
                    break;

                case 't':
                    e.preventDefault();
                    // T: Set Labels
                    this.nodeEditor.showSetLabelsDialog(nodeId);
                    break;

                case 'w':
                    e.preventDefault();
                    // W: Select previous node (incoming edge)
                    this.selectPreviousNode(nodeId);
                    break;

                case 's':
                    e.preventDefault();
                    // S: Select next node (outgoing edge)
                    this.selectNextNode(nodeId);
                    break;
            }
        });
    }

    /**
     * Release focus from vis.js network to clear hover state and tooltip
     * 
     * When a dialog/modal opens, the network should release focus because:
     * 1. The dialog overlays the network visualization
     * 2. vis.js is no longer responsive (in the background)
     * 3. The tooltip should not persist when the user interacts with the dialog
     * 
     * Implementation: Trigger mousemove event to a position outside the canvas.
     * This forces the browser to hide the native tooltip and vis.js to clear hover state.
     */
    releaseFocus() {
        if (!this.network || !this.container) return;

        const canvas = this.container.querySelector('canvas');
        if (!canvas) return;

        // Trigger mousemove to a position outside the canvas
        // This is reliable for forcing browser to hide tooltip
        const rect = canvas.getBoundingClientRect();
        const mouseMoveEvent = new MouseEvent('mousemove', {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: rect.left - 10,  // Move outside canvas
            clientY: rect.top - 10
        });
        canvas.dispatchEvent(mouseMoveEvent);
    }

    editFirstEvent(nodeId) {
        // Get the first outgoing event of this node
        const outgoingEvents = this.nodeEditor.getOutgoingEvents(nodeId);
        if (outgoingEvents.length > 0) {
            this.nodeEditor.editOutgoingEvent(outgoingEvents[0].id);
        }
    }

    editNthEvent(nodeId, n) {
        // Get the nth outgoing event of this node (1-based index)
        const outgoingEvents = this.nodeEditor.getOutgoingEvents(nodeId);
        if (n >= 1 && n <= outgoingEvents.length) {
            this.nodeEditor.editOutgoingEvent(outgoingEvents[n - 1].id);
        } else {
            console.log(`Event ${n} not found. Node has ${outgoingEvents.length} events.`);
        }
    }

    selectPreviousNode(nodeId) {
        if (!this.utg || !this.utg.edges || !this.utg.nodes) return;

        // Find all edges pointing to the current node
        const incomingEdges = this.utg.edges.filter(edge => edge.to === nodeId);
        if (incomingEdges.length === 0) return;

        // Find the edge with the smallest event_id (earliest arrival)
        let earliestEdge = null;
        let minEventId = Infinity;

        for (const edge of incomingEdges) {
            if (edge.events && edge.events.length > 0) {
                // Get the minimum event_id from this edge's events
                const edgeMinEventId = Math.min(...edge.events.map(e => e.event_id));
                if (edgeMinEventId < minEventId) {
                    minEventId = edgeMinEventId;
                    earliestEdge = edge;
                }
            }
        }

        if (earliestEdge) {
            this.network.selectNodes([earliestEdge.from]);
            window.showDetailsSidebar('节点详情', '');
            this.nodeEditor.showNodeDetails(earliestEdge.from);
        }
    }

    selectNextNode(nodeId) {
        if (!this.utg || !this.utg.edges || !this.utg.nodes) return;

        // Find all edges from the current node
        const outgoingEdges = this.utg.edges.filter(edge => edge.from === nodeId);
        if (outgoingEdges.length === 0) return;

        // Find the edge with the smallest event_id (earliest departure)
        let earliestEdge = null;
        let minEventId = Infinity;

        for (const edge of outgoingEdges) {
            if (edge.events && edge.events.length > 0) {
                // Get the minimum event_id from this edge's events
                const edgeMinEventId = Math.min(...edge.events.map(e => e.event_id));
                if (edgeMinEventId < minEventId) {
                    minEventId = edgeMinEventId;
                    earliestEdge = edge;
                }
            }
        }

        if (earliestEdge) {
            this.network.selectNodes([earliestEdge.to]);
            window.showDetailsSidebar('节点详情', '');
            this.nodeEditor.showNodeDetails(earliestEdge.to);
        }
    }

    showError(message) {
        if (this.detailsPanel) {
            this.detailsPanel.innerHTML = `<h2>错误</h2><p>${message}</p>`;
        } else {
            console.error('UTG Error:', message);
        }
    }

    isWorkspaceScopedError(error) {
        if (!error) {
            return false;
        }
        return ['WORKSPACE_EXPIRED', 'RECORDING_REQUIRED'].includes(error.code);
    }

    resetWorkspaceState() {
        this.hideTaskInfo();
        this.activeRecordingName = null;
        this.utg = null;
        this.cachedProcessedData = null;
        this.lastUtg = null;
        this.lastShowGlobal = null;

        if (this.network) {
            this.network.destroy();
            this.network = null;
        }

        if (this.detailsPanel) {
            this.detailsPanel.innerHTML = '<p>请选择录制数据后查看详情。</p>';
        }
    }

    // Task Info methods
    async loadTaskInfo() {
        try {
            // 显示加载状态
            if (this.taskInfoStatus) {
                this.taskInfoStatus.textContent = '加载中...';
                this.taskInfoStatus.className = 'text-muted';
            }

            // 调用 API 获取 task-info（后端从 workspace 读取 current_recording）
            const data = await api.getTaskInfo();

            if (data && data.task_info) {
                // 更新 recording 名称显示（使用后端返回的 recording）
                if (this.taskInfoDatasetName && data.recording) {
                    this.taskInfoDatasetName.textContent = data.recording;
                }

                // 显示 Task Info 悬浮框（必须先显示，CodeMirror 才能正确渲染）
                if (this.taskInfoPanel) {
                    this.taskInfoPanel.style.display = 'block';
                }

                // 显示在 CodeMirror 中
                if (this.taskInfoCodeMirror) {
                    this.taskInfoCodeMirror.setValue(data.task_info);
                    // 强制 CodeMirror 刷新布局（容器从隐藏变为显示后需要重新计算）
                    this.taskInfoCodeMirror.refresh();
                }

                this.taskInfoLoaded = true;

                if (this.taskInfoStatus) {
                    this.taskInfoStatus.textContent = '加载成功';
                    setTimeout(() => {
                        this.taskInfoStatus.textContent = '';
                    }, 2000);
                }

                console.log('Task info loaded for dataset:', data.dataset);
            } else {
                // Task info 数据为空
                this.showTaskInfoError(404, '服务器未返回任务信息数据');
            }
        } catch (error) {
            console.error('Failed to load task info:', error);
            if (this.isWorkspaceScopedError(error)) {
                this.resetWorkspaceState();
            }

            // 使用统一的错误显示方法
            this.showTaskInfoError(error.status || 500, error.message);
        }
    }

    enterTaskInfoEditMode() {
        this.taskInfoEditMode = true;

        // 启用 CodeMirror 编辑
        if (this.taskInfoCodeMirror) {
            this.taskInfoCodeMirror.setOption('readOnly', false);
            this.taskInfoCodeMirror.focus();
        }

        // 切换按钮显示: Edit 隐藏, Save 和 Cancel 显示
        if (this.taskInfoEditBtn) {
            this.taskInfoEditBtn.style.display = 'none';
        }
        if (this.taskInfoSaveBtn) {
            this.taskInfoSaveBtn.style.display = 'inline-block';
        }
        if (this.taskInfoCancelBtn) {
            this.taskInfoCancelBtn.style.display = 'inline-block';
        }

        if (this.taskInfoStatus) {
            this.taskInfoStatus.textContent = '编辑中...';
            this.taskInfoStatus.className = 'text-info';
        }
    }

    exitTaskInfoEditMode() {
        this.taskInfoEditMode = false;

        // 禁用 CodeMirror 编辑
        if (this.taskInfoCodeMirror) {
            this.taskInfoCodeMirror.setOption('readOnly', true);
        }

        // 切换按钮显示: Edit 显示, Save 和 Cancel 隐藏
        if (this.taskInfoEditBtn) {
            this.taskInfoEditBtn.style.display = 'inline-block';
        }
        if (this.taskInfoSaveBtn) {
            this.taskInfoSaveBtn.style.display = 'none';
        }
        if (this.taskInfoCancelBtn) {
            this.taskInfoCancelBtn.style.display = 'none';
        }
    }

    async cancelTaskInfoEdit() {
        // 退出编辑模式
        this.exitTaskInfoEditMode();

        if (this.taskInfoStatus) {
            this.taskInfoStatus.textContent = '重新加载中...';
            this.taskInfoStatus.className = 'text-muted';
        }

        // 重新加载 task info 以恢复原始内容
        await this.loadTaskInfo();
    }

    async saveTaskInfo() {
        const newTaskInfo = this.taskInfoCodeMirror ? this.taskInfoCodeMirror.getValue() : '';

        try {
            // 禁用 Save 和 Cancel 按钮，防止重复点击
            if (this.taskInfoSaveBtn) {
                this.taskInfoSaveBtn.disabled = true;
            }
            if (this.taskInfoCancelBtn) {
                this.taskInfoCancelBtn.disabled = true;
            }
            if (this.taskInfoStatus) {
                this.taskInfoStatus.textContent = '保存中...';
                this.taskInfoStatus.className = 'text-info';
            }

            // 调用 API 更新 task-info（后端从 workspace 读取 current_recording）
            const data = await api.updateTaskInfo(newTaskInfo);

            if (data && data.task_info) {
                // 更新 CodeMirror 内容（后端可能格式化过）
                if (this.taskInfoCodeMirror) {
                    this.taskInfoCodeMirror.setValue(data.task_info);
                }

                // 退出编辑模式
                this.exitTaskInfoEditMode();

                if (this.taskInfoStatus) {
                    this.taskInfoStatus.textContent = '保存成功';
                    this.taskInfoStatus.className = 'text-success';
                    setTimeout(() => {
                        this.taskInfoStatus.textContent = '';
                    }, 2000);
                }

                if (window.showSuccess) {
                    window.showSuccess('任务信息更新成功');
                }

                console.log('Task info saved for dataset:', data.dataset);
            }
        } catch (error) {
            console.error('Failed to save task info:', error);

            if (this.taskInfoStatus) {
                this.taskInfoStatus.textContent = '保存失败';
                this.taskInfoStatus.className = 'text-danger';
            }

            // 根据错误类型显示不同的错误信息
            let errorMessage = '保存任务信息失败';
            if (error.status === 400) {
                errorMessage = 'YAML 格式无效或缺少必填字段';
            } else if (error.status === 404) {
                errorMessage = '任务信息不存在';
            } else if (error.message) {
                errorMessage = error.message;
            }

            console.error(errorMessage);
        } finally {
            // 恢复按钮状态
            if (this.taskInfoSaveBtn) {
                this.taskInfoSaveBtn.disabled = false;
            }
            if (this.taskInfoCancelBtn) {
                this.taskInfoCancelBtn.disabled = false;
            }
        }
    }

    toggleTaskInfoCollapse() {
        this.taskInfoCollapsed = !this.taskInfoCollapsed;

        if (this.taskInfoContent) {
            this.taskInfoContent.style.display = this.taskInfoCollapsed ? 'none' : 'block';
        }

        // 更新折叠按钮图标
        if (this.taskInfoCollapseBtn) {
            const icon = this.taskInfoCollapseBtn.querySelector('.glyphicon');
            if (icon) {
                icon.className = this.taskInfoCollapsed ?
                    'glyphicon glyphicon-chevron-down' :
                    'glyphicon glyphicon-chevron-up';
            }
        }
    }

    /**
     * 显示 Task Info 加载失败的提示信息
     * @param {number} errorStatus - HTTP 错误状态码 (404, 400, etc.)
     * @param {string} errorMessage - 错误消息 (可选)
     */
    showTaskInfoError(errorStatus, errorMessage = '') {
        let message = '';
        let statusText = '';
        let statusClass = 'text-muted';

        switch (errorStatus) {
            case 404:
                // Task info 文件不存在
                message = '当前录制数据未找到任务信息文件。\n\n你可以点击“编辑”按钮创建。';
                statusText = '未找到';
                statusClass = 'text-warning';
                break;
            case 400:
                // 没有选中 dataset
                message = '尚未选择录制数据。\n\n请先在“数据编辑”或“任务录制”中选择一条录制数据。';
                statusText = '未选择录制数据';
                statusClass = 'text-muted';
                break;
            default:
                // 其他错误
                message = `加载任务信息失败：${errorMessage || '未知错误'}`;
                statusText = '加载失败';
                statusClass = 'text-danger';
                break;
        }

        // 显示面板（必须先显示，CodeMirror 才能正确渲染）
        if (this.taskInfoPanel) {
            this.taskInfoPanel.style.display = 'block';
        }

        // 在 CodeMirror 中显示提示信息
        if (this.taskInfoCodeMirror) {
            this.taskInfoCodeMirror.setValue(message);
            // 强制 CodeMirror 刷新布局
            this.taskInfoCodeMirror.refresh();
        }

        // 更新状态文本
        if (this.taskInfoStatus) {
            this.taskInfoStatus.textContent = statusText;
            this.taskInfoStatus.className = statusClass;
        }

        this.taskInfoLoaded = false;

        // 确保退出编辑模式
        if (this.taskInfoEditMode) {
            this.exitTaskInfoEditMode();
        }
    }

    hideTaskInfo() {
        if (this.taskInfoPanel) {
            this.taskInfoPanel.style.display = 'none';
        }

        if (this.taskInfoCodeMirror) {
            this.taskInfoCodeMirror.setValue('');
        }

        if (this.taskInfoDatasetName) {
            this.taskInfoDatasetName.textContent = '';
        }

        if (this.taskInfoStatus) {
            this.taskInfoStatus.textContent = '';
            this.taskInfoStatus.className = 'text-muted';
        }

        this.taskInfoLoaded = false;

        // 确保退出编辑模式
        if (this.taskInfoEditMode) {
            this.exitTaskInfoEditMode();
        }
    }

    /**
     * Switches to a recording and loads its task info and UTG
     * @param {string} directoryName - The recording directory name to switch to
     */
    async switchToRecording(directoryName) {
        try {
            console.log(`UTGViewer: Switching to recording: ${directoryName}`);

            // 1. Set current recording in backend session
            await api.setCurrentRecording(directoryName);
            console.log(`UTGViewer: Recording switched to ${directoryName}`);
            this.activeRecordingName = directoryName;

            // 2. Load task info for this recording
            await this.loadTaskInfo();

            // 3. Load UTG visualization
            await this.loadUTG();

            console.log(`UTGViewer: Successfully loaded recording ${directoryName}`);
        } catch (error) {
            console.error(`UTGViewer: Failed to switch to recording ${directoryName}:`, error);
            if (this.isWorkspaceScopedError(error)) {
                this.resetWorkspaceState();
            }
            throw error;
        }
    }

    /**
     * Restores the current workspace recording without rewriting workspace state.
     * @param {string|null} directoryName - The already-mounted recording directory name
     */
    async restoreWorkspaceRecording(directoryName) {
        if (!directoryName) {
            this.resetWorkspaceState();
            return;
        }

        if (this.activeRecordingName === directoryName && this.utg && this.taskInfoLoaded) {
            return;
        }

        try {
            this.activeRecordingName = directoryName;
            if (this.taskInfoDatasetName) {
                this.taskInfoDatasetName.textContent = directoryName;
            }

            await this.loadTaskInfo();
            await this.loadUTG();
        } catch (error) {
            console.error(`UTGViewer: Failed to restore workspace recording ${directoryName}:`, error);
            if (this.isWorkspaceScopedError(error)) {
                this.resetWorkspaceState();
            }
            throw error;
        }
    }

    fitForRestore() {
        if (!this.network || !this.container) {
            return false;
        }

        const rect = typeof this.container.getBoundingClientRect === 'function'
            ? this.container.getBoundingClientRect()
            : null;
        const width = rect ? rect.width : this.container.clientWidth;
        const height = rect ? rect.height : this.container.clientHeight;

        if (!width || !height) {
            return false;
        }

        this.network.redraw();
        this.network.fit({
            animation: false
        });
        return true;
    }

    // 清理方法，用于销毁UTGViewer实例时调用
    destroy() {
        if (this.network) {
            this.network.destroy();
            this.network = null;
        }
    }
}
