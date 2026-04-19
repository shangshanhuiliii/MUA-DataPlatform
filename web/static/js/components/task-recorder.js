/**
 * 设备屏幕实时显示组件
 * 提供实时屏幕流显示和设备控制功能
 */

function TaskRecorder(containerId) {
    // Initialize properties
    this.containerId = containerId || 'control_panel';
    this.container = null;
    this.isVisible = false;
    this.websocket = null;
    this.deviceSerial = null;
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 2000;
    this.touchCoordinates = { x: 0, y: 0 };
    this.swipeStartCoordinates = null;
    this.isSwipeMode = false;
    this.userDisconnected = false;
    this.frameCount = 0;
    
    // Recording properties
    this.isRecording = false;
    this.isPaused = false;
    this.recordedActionsCount = 0;  // 只记录操作数量，不保存操作详情
    this.explorationTaskId = null;
    this.recordingSessionId = null;
    this.deviceSessionId = null;
    this.recordingMode = 'new_task';  // 'new_task' or 'append_data'
    this.currentRecording = null;  // 当前选中的 recording
    this.selectedTask = null;  // modal 选中的任务
    this.selectedRecording = null;  // modal 选中的录制
    this.token = localStorage.getItem('auth_token');  // 认证 token
    this.selectionPageSize = 5;
    this.selectionDialog = window.TaskSelectionDialog
        ? new TaskSelectionDialog({ pageSize: this.selectionPageSize })
        : null;
    
    // Operation timing tracking
    this.currentOperation = null;
    this.operationStartTime = null;
    this.recordingStartTime = null;
    this.operationStatusTimer = null;
    
    // Operation state management for blocking
    this.operationPending = false;
    this.operationQueue = [];

    // Heartbeat properties
    this.heartbeatInterval = null;
    this.heartbeatTimeout = null;
    this.heartbeatIntervalMs = 15000;  // 每15秒发送一次心跳
    this.heartbeatTimeoutMs = 10000;  // 10秒未收到pong认为连接断开
    this.lastPongTime = null;
    this.runtimeKeepaliveTimer = null;

}

TaskRecorder.prototype.constructor = TaskRecorder;

TaskRecorder.prototype.show = async function() {
    if (!this.containerId) return;
    
    this.container = document.getElementById(this.containerId);
    if (!this.container) return;
    
    this.isVisible = true;
    try {
        const taskRecorderHTML = await this.getTaskRecorderInterface();
        this.container.innerHTML = taskRecorderHTML;
        
        // Initialize elements immediately after DOM insertion
        this.initializeElements();
        this.bindEvents();
        
        // Always reload tasks and devices and reset to touch mode when showing
        this.loadTasks();
        this.loadDevices();
        this.setTouchMode();
        
    } catch (error) {
        console.error('Failed to show task record interface:', error);
        this.container.innerHTML = '<hr /><h2>错误</h2><p>加载任务录制界面失败。</p>';
    }
};

TaskRecorder.prototype.hide = function() {
    this.isVisible = false;
    
    // Disconnect if connected and reset state
    if (this.isConnected) {
        this.disconnect();
    }
    
    // Clean up timing system
    this.clearOperationStatus();
    
    // Reset operation pending state
    this.setOperationPending(false);
    
    // Reset all states to ensure clean restart next time
    this.deviceSerial = null;
    this.frameCount = 0;
    this.reconnectAttempts = 0;
    this.userDisconnected = false;
    
    // Reset recording state
    this.isRecording = false;
    this.isPaused = false;
    this.recordedActionsCount = 0;
    this.explorationTaskId = null;
    this.recordingSessionId = null;
    this.deviceSessionId = null;
    this.recordingStartTime = null;
};

TaskRecorder.prototype.getTaskRecorderInterface = async function() {
    return `
        <hr />
        <h2>任务录制</h2>
        <div class="task-recorder-container" id="task-recorder-container">
            <div class="screen-device-selection">
                <!-- Task Selection -->
                <div class="control-section">
                    <h5>任务选择</h5>
                    <!-- Recording Mode Selection -->
                    <div>
                        <label style="font-weight: normal; margin-right: 20px;">
                            <input type="radio" name="recording-mode" id="new-task-mode" value="new_task" checked style="margin-right: 5px;"> 录制新任务
                        </label>
                        <label style="font-weight: normal;">
                            <input type="radio" name="recording-mode" id="append-data-mode" value="append_data" style="margin-right: 5px;"> 更新录制数据
                        </label>
                    </div>
                    <!-- Task/Dataset Selection Control -->
                    <div class="input-group" style="margin-top: 10px;">
                        <input id="task-select-display" type="text" class="form-control" value="请选择任务" readonly>
                        <span class="input-group-btn">
                            <button id="open-task-selection-btn" class="btn btn-default" type="button">选择</button>
                        </span>
                        <span class="input-group-btn">
                            <button id="clear-task-selection-btn" class="btn btn-link" type="button">清除</button>
                        </span>
                    </div>
                    <small id="task-selection-hint" class="help-block" style="margin-bottom: 0;">请选择任务后开始录制</small>
                    <input type="hidden" id="task-select" value="">
                </div>
                <div class="control-section">
                    <h5>设备选择</h4>
                    <div class="form-group">
                        <select id="screen-device-select" class="form-control">
                            <option value="">正在加载设备...</option>
                        </select>
                    </div>
                    <div class="screen-connection-controls">
                        <button id="screen-toggle-connection-btn" class="btn btn-primary">连接</button>
                        <span id="screen-status" class="screen-status status-disconnected">未连接</span>
                        <span id="device-info" class="device-info"></span>
                        <span id="frame-counter" class="frame-counter"></span>
                    </div>
                </div>
            </div>
            
            <div class="screen-display-container">
                <!-- 屏幕显示区域 -->
                <div class="screen-display-section">
                    <img id="screen-display" class="screen-display" style="display: none;" alt="设备屏幕" />
                    <div class="screen-placeholder" id="screen-placeholder">
                        连接设备后可查看屏幕
                    </div>
                </div>
                <!-- 状态显示区域 -->
                <div class="status-display-section">
                    <div style="margin-bottom: 8px;">
                        <span id="recording-status-display">-</span>
                    </div>
                    <div>
                        操作状态: <span id="operation-status-display">-</span>
                    </div>
                </div>
            </div>
            
            <div id="screen-controls" class="screen-controls">
                <!-- Screen Recording -->
                <div class="control-section">
                    <h5>屏幕录制</h5>
                    <div>
                        <label style="font-weight: normal;">
                            <input id="use-image-state-checkbox" type="checkbox" checked style="margin-right: 5px;"> 使用图像状态（use_image_state）
                        </label>
                        <div>
                            <p style="font-weight:bold;">视图模式</p>
                            <div>
                                <label style="font-weight: normal; margin-right: 20px;" title="使用对特定UI元素进行训练的YOLO模型进行视图解析">
                                    <input type="radio" name="view-mode" id="yolo-view-mode" value="yolo_mode" checked style="margin-right: 5px;"> YOLO 模式
                                </label>
                                <label style="font-weight: normal; margin-right: 20px;" title="使用基于计算机视觉的方法进行视图解析">
                                    <input type="radio" name="view-mode" id="cv-view-mode" value="cv_mode" style="margin-right: 5px;"> CV 模式
                                </label>
                                <label style="font-weight: normal;" title="使用UIAutomator2获取的UI层级结构进行视图解析">
                                    <input type="radio" name="view-mode" id="xml-view-mode" value="xml_mode" style="margin-right: 5px;"> UI 层级模式
                                </label>
                            </div>
                        </div>
                    </div>
                    <div class="control-buttons">
                        <button id="toggle-recording-btn" class="btn btn-success">
                            <span class="glyphicon glyphicon-play"></span> 开始录制
                        </button>
                        <button id="pause-recording-btn" class="btn btn-warning" disabled>
                            <span class="glyphicon glyphicon-pause"></span> 暂停录制
                        </button>
                        <div id="recording-status-container" class="recording-status-container" style="margin-left: 10px;">
                            <span id="recording-indicator" class="recording-indicator"></span>
                            <span id="recording-status-text" class="recording-status-text"></span>
                        </div>
                    </div>
                </div>
                
                <!-- Control Mode -->
                <div class="control-section">
                    <h5>控制模式</h5>
                    <div class="control-buttons">
                        <button id="touch-mode-btn" class="btn btn-default">点击模式</button>
                        <button id="swipe-mode-btn" class="btn btn-default">滑动模式</button>
                    </div>
                </div>
                
                <!-- System Keys -->
                <div class="control-section">
                    <h5>系统按键</h5>
                    <div class="control-buttons">
                        <button id="back-key-btn" class="btn btn-default">
                            <span class="glyphicon glyphicon-arrow-left"></span> 返回
                        </button>
                        <button id="home-key-btn" class="btn btn-default">
                            <span class="glyphicon glyphicon-home"></span> 主页
                        </button>
                    </div>
                </div>
                
                <!-- Put Text -->
                <div class="control-section">
                    <h5>输入文本</h5>
                    <div class="text-input-group">
                        <input id="text-input" type="text" class="form-control" placeholder="输入要填入当前焦点输入框的文本...">
                        <button id="send-text-btn" class="btn btn-primary">输入文本</button>
                    </div>
                </div>
                
            </div>
        </div>
    `;
};

TaskRecorder.prototype.initializeElements = function() {
    // 获取DOM元素
    this.taskRecorderContainer = document.getElementById('task-recorder-container');
    this.taskSelect = document.getElementById('task-select');
    this.taskSelectionDisplay = document.getElementById('task-select-display');
    this.openTaskSelectionBtn = document.getElementById('open-task-selection-btn');
    this.clearTaskSelectionBtn = document.getElementById('clear-task-selection-btn');
    this.taskSelectionHint = document.getElementById('task-selection-hint');
    this.newTaskModeRadio = document.getElementById('new-task-mode');
    this.appendDataModeRadio = document.getElementById('append-data-mode');
    this.deviceSelect = document.getElementById('screen-device-select');
    this.toggleConnectionBtn = document.getElementById('screen-toggle-connection-btn');
    this.statusIndicator = document.getElementById('screen-status');
    this.screenImage = document.getElementById('screen-display');
    this.screenPlaceholder = document.getElementById('screen-placeholder');
    this.controlPanel = document.getElementById('screen-controls');
    this.touchModeBtn = document.getElementById('touch-mode-btn');
    this.swipeModeBtn = document.getElementById('swipe-mode-btn');
    this.backBtn = document.getElementById('back-key-btn');
    this.homeBtn = document.getElementById('home-key-btn');
    this.textInput = document.getElementById('text-input');
    this.sendTextBtn = document.getElementById('send-text-btn');
    this.deviceInfo = document.getElementById('device-info');
    this.frameCounter = document.getElementById('frame-counter');
    
    // Recording control elements
    this.toggleRecordingBtn = document.getElementById('toggle-recording-btn');
    this.pauseRecordingBtn = document.getElementById('pause-recording-btn');
    this.recordingIndicator = document.getElementById('recording-indicator');
    this.recordingStatusText = document.getElementById('recording-status-text');
    this.useImageStateCheckbox = document.getElementById('use-image-state-checkbox');
    
    // Status display elements
    this.recordingStatusDisplay = document.getElementById('recording-status-display');
    this.operationStatusDisplay = document.getElementById('operation-status-display');

    // 初始化状态
    this.updateConnectionState(false);
    this.syncRecordingModeControls();
    this.updateSelectionDisplay();
};

TaskRecorder.prototype.bindEvents = function() {
    var self = this;
    
    // 设备连接切换按钮
    if (this.toggleConnectionBtn) {
        this.toggleConnectionBtn.addEventListener('click', function() {
            if (self.isConnected) {
                self.disconnect();
            } else {
                self.connect();
            }
        });
    }
    
    // 屏幕交互事件
    if (this.screenImage) {
        this.screenImage.addEventListener('click', function(e) {
            self.handleScreenClick(e);
        });
        this.screenImage.addEventListener('mousedown', function(e) {
            self.handleMouseDown(e);
        });
        this.screenImage.addEventListener('mousemove', function(e) {
            self.handleMouseMove(e);
        });
        this.screenImage.addEventListener('mouseup', function(e) {
            self.handleMouseUp(e);
        });
        // 阻止图片的拖拽开始事件 - 在所有模式下都禁用
        this.screenImage.addEventListener('dragstart', function(e) {
            e.preventDefault();
            return false;
        });
    }
    
    // 控制模式切换
    if (this.touchModeBtn) {
        this.touchModeBtn.addEventListener('click', function() {
            self.setTouchMode();
        });
    }
    
    if (this.swipeModeBtn) {
        this.swipeModeBtn.addEventListener('click', function() {
            self.setSwipeMode();
        });
    }
    
    // 系统按键
    if (this.backBtn) {
        this.backBtn.addEventListener('click', function() {
            self.sendKey('KEYCODE_BACK');
        });
    }
    
    if (this.homeBtn) {
        this.homeBtn.addEventListener('click', function() {
            self.sendKey('KEYCODE_HOME');
        });
    }
    
    // 文本输入
    if (this.sendTextBtn) {
        this.sendTextBtn.addEventListener('click', function() {
            self.sendText();
        });
    }
    
    if (this.textInput) {
        this.textInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' || e.keyCode === 13) {
                self.sendText();
            }
        });
    }
    
    // Recording control button
    if (this.toggleRecordingBtn) {
        this.toggleRecordingBtn.addEventListener('click', function() {
            self.toggleRecording();
        });
    }

    if (this.pauseRecordingBtn) {
        this.pauseRecordingBtn.addEventListener('click', function() {
            if (self.isPaused) {
                self.resumeRecording();
            } else {
                self.pauseRecording();
            }
        });
    }
    
    if (this.openTaskSelectionBtn) {
        this.openTaskSelectionBtn.addEventListener('click', function() {
            if (self.recordingMode === 'append_data') {
                self.openRecordingSelection();
            } else {
                self.openTaskSelection();
            }
        });
    }

    if (this.clearTaskSelectionBtn) {
        this.clearTaskSelectionBtn.addEventListener('click', function() {
            self.clearCurrentSelection();
        });
    }

    // Recording mode radio button listeners
    if (this.newTaskModeRadio) {
        this.newTaskModeRadio.addEventListener('change', function() {
            if (this.checked) {
                self.switchRecordingMode('new_task');
            }
        });
    }

    if (this.appendDataModeRadio) {
        this.appendDataModeRadio.addEventListener('change', function() {
            if (this.checked) {
                self.switchRecordingMode('append_data');
            }
        });
    }
    
    // 监听窗口大小变化，调整 canvas 尺寸和位置
    window.addEventListener('resize', function() {
        if (self.swipeCanvas && self.screenImage) {
            var rect = self.screenImage.getBoundingClientRect();
            var containerRect = self.swipeCanvas.parentElement.getBoundingClientRect();
            
            self.swipeCanvas.width = rect.width;
            self.swipeCanvas.height = rect.height;
            self.swipeCanvas.style.width = rect.width + 'px';
            self.swipeCanvas.style.height = rect.height + 'px';
            self.swipeCanvas.style.left = (rect.left - containerRect.left) + 'px';
            self.swipeCanvas.style.top = (rect.top - containerRect.top) + 'px';
        }
    });
};

TaskRecorder.prototype.loadTasks = async function() {
    // 新的弹窗选择模式仅需刷新显示，不再预加载全部任务
    this.updateSelectionDisplay();
};

TaskRecorder.prototype.loadDevices = async function() {
    var self = this;

    try {
        self.token = localStorage.getItem('auth_token');
        // 调用云设备 API，只获取激活的设备（响应中包含 locked_device_ids）
        var data = await api.getCloudDevices(self.token, { is_active: true });

        // 锁定设备列表直接从响应中获取
        var lockedDevices = data.locked_device_ids || [];

        if (self.deviceSelect) {
            self.deviceSelect.innerHTML = '<option value="">请选择设备...</option>';

            data.items.forEach(function(device) {
                var option = document.createElement('option');
                option.value = device.id;
                option.dataset.productId = device.product_id;
                option.dataset.podId = device.pod_id;

                // 显示名称：有别名显示别名，否则显示 pod_id
                var displayName = device.alias || device.pod_id;

                // 如果设备被锁定，显示锁定标记
                if (lockedDevices.includes(device.id)) {
                    displayName += ' 🔒';
                }

                option.textContent = displayName;
                self.deviceSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Failed to load cloud devices:', error);
        self.showError('加载设备列表失败');
    }
};

TaskRecorder.prototype.loadDatasets = async function() {
    // Append Data 模式下同样只需刷新显示，真正的数据在弹窗中分页加载
    this.updateSelectionDisplay();
};

// ============================================================================
// Task / Recording Selection Helpers
// ============================================================================

TaskRecorder.prototype.updateSelectionDisplay = function() {
    var displayText = '请选择任务';
    var hintText = '请选择任务后开始录制';
    var buttonText = '选择任务';
    var hasValue = false;
    var value = '';

    if (this.recordingMode === 'append_data') {
        buttonText = '选择录制数据';
        hintText = '选择一条已有录制以追加数据';
        if (this.selectedRecording && this.selectedRecording.directory_name) {
            displayText = this.formatRecordingLabel(this.selectedRecording);
            value = this.selectedRecording.directory_name;
            hasValue = true;
        } else if (this.currentRecording) {
            displayText = this.currentRecording;
            value = this.currentRecording;
            hasValue = true;
        } else {
            displayText = '请选择需要追加的录制数据';
        }
    } else {
        if (this.selectedTask && this.selectedTask.id) {
            displayText = this.formatTaskLabel(this.selectedTask);
            value = this.selectedTask.id;
            hasValue = true;
        } else {
            displayText = '请选择待录制的任务';
        }
    }

    if (this.taskSelectionDisplay) {
        this.taskSelectionDisplay.value = displayText;
        this.taskSelectionDisplay.title = displayText;
    }
    if (this.taskSelectionHint) {
        this.taskSelectionHint.textContent = hintText;
    }
    if (this.openTaskSelectionBtn) {
        this.openTaskSelectionBtn.textContent = buttonText;
    }
    if (this.taskSelect) {
        this.taskSelect.value = hasValue ? value : '';
    }
    if (this.clearTaskSelectionBtn) {
        this.clearTaskSelectionBtn.disabled = !hasValue || this.isRecording;
    }
};

TaskRecorder.prototype.hasSelectionForCurrentMode = function() {
    if (this.recordingMode === 'append_data') {
        return !!(this.selectedRecording && this.selectedRecording.directory_name) || !!this.currentRecording;
    }
    return !!(this.selectedTask && this.selectedTask.id);
};

TaskRecorder.prototype.openTaskSelection = function() {
    if (!this.selectionDialog) {
        this.showError('选择组件不可用');
        return;
    }
    var self = this;
    this.selectionDialog.openTaskSelector({
        selectedTask: this.selectedTask,
        onSelect: function(item) {
            self.selectedTask = item;
            if (self.taskSelect) {
                self.taskSelect.value = item ? item.id : '';
            }
            self.updateSelectionDisplay();
        }
    });
};

TaskRecorder.prototype.openRecordingSelection = function() {
    if (!this.selectionDialog) {
        this.showError('选择组件不可用');
        return;
    }
    var self = this;
    var selected = this.selectedRecording
        ? this.selectedRecording
        : (this.currentRecording ? { directory_name: this.currentRecording } : null);

    this.selectionDialog.openRecordingSelector({
        selectedRecording: selected,
        onSelect: function(item) {
            var previous = self.selectedRecording;
            self.selectedRecording = item;
            self.updateSelectionDisplay();
            return self.applyRecordingSelection(item.directory_name, previous);
        }
    });
};

TaskRecorder.prototype.clearCurrentSelection = async function() {
    if (this.isRecording) {
        this.showError('录制进行中，无法切换任务或录制数据');
        return;
    }

    if (this.recordingMode === 'append_data') {
        if (!this.selectedRecording && !this.currentRecording) {
            return;
        }
        var previousRecording = this.selectedRecording;
        this.selectedRecording = null;
        this.updateSelectionDisplay();
        await this.applyRecordingSelection(null, previousRecording);
    } else {
        if (!this.selectedTask) {
            return;
        }
        this.selectedTask = null;
        this.updateSelectionDisplay();
    }
};

TaskRecorder.prototype.setSelectionControlsDisabled = function(disabled) {
    if (this.openTaskSelectionBtn) {
        this.openTaskSelectionBtn.disabled = disabled;
    }
    if (this.clearTaskSelectionBtn) {
        this.clearTaskSelectionBtn.disabled = disabled || !this.hasSelectionForCurrentMode();
    }
    if (this.taskSelectionDisplay) {
        this.taskSelectionDisplay.style.opacity = disabled ? '0.6' : '1';
    }
};

TaskRecorder.prototype.applyRecordingSelection = async function(directoryName, previousRecording) {
    if (this.recordingMode !== 'append_data') {
        return true;
    }

    var previousValue = previousRecording ? previousRecording.directory_name : (this.currentRecording || null);

    if (!directoryName) {
        try {
            this.setSelectionControlsDisabled(true);
            await api.releaseCurrentRecording();
            this.currentRecording = null;
            if (window.dataEditor) {
                window.dataEditor.currentRecording = null;
            }
            if (window.app && window.app.utgViewer && typeof window.app.utgViewer.hideTaskInfo === 'function') {
                window.app.utgViewer.hideTaskInfo();
            }
            if (window.showSuccess) {
                window.showSuccess('已清除当前录制数据');
            }
            return true;
        } catch (error) {
            console.error('Failed to release recording:', error);
            if (window.showError) {
                window.showError('清除录制数据失败：' + error.message);
            }
            if (!previousRecording && previousValue) {
                this.selectedRecording = { directory_name: previousValue };
            } else {
                this.selectedRecording = previousRecording || null;
            }
            if (this.taskSelect) {
                this.taskSelect.value = previousValue || '';
            }
            this.updateSelectionDisplay();
            return false;
        } finally {
            this.setSelectionControlsDisabled(this.isRecording);
        }
    }

    if (directoryName === this.currentRecording) {
        return true;
    }

    try {
        this.setSelectionControlsDisabled(true);
        var response = await api.setCurrentRecording(directoryName);

        if (response && response.current) {
            this.currentRecording = response.current;
            if (window.showSuccess) {
                window.showSuccess('已切换到录制数据：' + directoryName);
            }
            if (window.dataEditor) {
                window.dataEditor.currentRecording = response.current;
            }
            if (window.app && window.app.utgViewer) {
                if (typeof window.app.utgViewer.loadTaskInfo === 'function') {
                    await window.app.utgViewer.loadTaskInfo();
                }
                if (typeof window.app.utgViewer.loadUTG === 'function') {
                    await window.app.utgViewer.loadUTG();
                }
            }
        } else if (response && response.current === undefined) {
            this.currentRecording = null;
            if (window.app && window.app.utgViewer && typeof window.app.utgViewer.hideTaskInfo === 'function') {
                window.app.utgViewer.hideTaskInfo();
            }
        }
        return true;
    } catch (error) {
        console.error('Failed to switch recording:', error);
        if (window.showError) {
            var errorMessage = (api && typeof api.formatRecordingLockConflict === 'function')
                ? api.formatRecordingLockConflict(error)
                : error.message;
            window.showError('切换录制数据失败：' + errorMessage);
        }
        if (!previousRecording && previousValue) {
            this.selectedRecording = { directory_name: previousValue };
        } else {
            this.selectedRecording = previousRecording || null;
        }
        if (this.taskSelect) {
            this.taskSelect.value = previousValue || '';
        }
        this.updateSelectionDisplay();
        return false;
    } finally {
        this.setSelectionControlsDisabled(this.isRecording);
    }
};

TaskRecorder.prototype.formatTaskLabel = function(task) {
    if (!task) {
        return '请选择任务';
    }
    var description = task.description || '';
    if (description.length > 80) {
        description = description.substring(0, 77) + '...';
    }
    return '#' + task.id + ' · ' + description;
};

TaskRecorder.prototype.formatRecordingLabel = function(recording) {
    if (!recording) {
        return '请选择录制数据';
    }
    var label = recording.directory_name || '';
    if (recording.task_description) {
        label += ' (' + recording.task_description + ')';
    }
    if (recording.recorded_by_username) {
        label += ' - ' + recording.recorded_by_username;
    }
    return label;
};

TaskRecorder.prototype.formatTaskStatusLabel = function(status) {
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
    return '<span class=\"' + cls + '\">' + text + '</span>';
};

TaskRecorder.prototype.formatDateTime = function(value) {
    if (!value) {
        return '-';
    }
    var date = new Date(value);
    if (isNaN(date.getTime())) {
        return '-';
    }
    return date.toLocaleString();
};

TaskRecorder.prototype.escapeHtml = function(str) {
    if (str === undefined || str === null) {
        return '';
    }
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\"/g, '&quot;')
        .replace(/'/g, '&#39;');
};

TaskRecorder.prototype.switchRecordingMode = function(mode) {
    this.recordingMode = mode;

    if (mode === 'new_task') {
        // 切换到任务列表
        this.loadTasks();
    } else if (mode === 'append_data') {
        // 切换到录制列表
        this.loadDatasets();
    }
};

TaskRecorder.prototype.connect = async function() {
    var self = this;
    var selectedDeviceId = this.deviceSelect ? this.deviceSelect.value : null;

    if (!selectedDeviceId) {
        this.showError('请选择设备');
        return;
    }

    try {
        this.userDisconnected = false;
        this.updateConnectionState(false, '正在连接设备...');

        self.token = await api.ensureFreshToken(localStorage.getItem('auth_token'));
        var connectResult = await api.connectCloudDevice(self.token, selectedDeviceId);

        if (!connectResult.success) {
            throw new Error(connectResult.message);
        }

        // 2. 使用返回的 device_serial 建立 WebSocket 连接
        this.deviceSerial = connectResult.device_serial;

        // 3. 建立 WebSocket 连接
        var wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        var wsUrl = wsProtocol + '//' + window.location.host + '/api/task-record/' + this.deviceSerial;

        this.websocket = new WebSocket(wsUrl);

        this.websocket.onopen = function() {
            console.log('Device stream opened, sending auth_init');
            self.updateConnectionState(false, '正在建立设备会话...');
            self.websocket.send(JSON.stringify({
                type: 'auth_init',
                access_token: localStorage.getItem('auth_token'),
                workspace_id: api.getWorkspaceId()
            }));
        };

        this.websocket.onmessage = function(event) {
            self.handleWebSocketMessage(JSON.parse(event.data));
        };

        this.websocket.onclose = function(event) {
            console.log('Device stream disconnected');
            self.isConnected = false;
            self.deviceSerial = null;
            self.deviceSessionId = null;
            self.lastPongTime = null;
            self.stopHeartbeat();
            self.resetRecordingRuntimeState();
            self.renderIdleRecordingState('未开始录制', '-');
            self.updateConnectionState(false, '未连接');
            self.handleDisconnection();
        };

        this.websocket.onerror = function(error) {
            console.error('WebSocket error:', error);
            self.showError('连接失败');
        };

    } catch (error) {
        console.error('Failed to connect:', error);
        this.showError('连接失败：' + error.message);
        this.updateConnectionState(false);
    }
};

TaskRecorder.prototype.disconnect = function() {
    this.userDisconnected = true;
    this.stopHeartbeat();
    this.resetRecordingRuntimeState();
    if (this.websocket) {
        this.websocket.close();
        this.websocket = null;
    }
    this.isConnected = false;
    this.deviceSerial = null;
    this.deviceSessionId = null;
    this.lastPongTime = null;
    this.renderIdleRecordingState('未开始录制', '-');
    
    // 清理 swipe preview canvas
    if (this.swipeCanvas) {
        this.swipeCanvas.remove();
        this.swipeCanvas = null;
    }
    
    this.updateConnectionState(false, '未连接');
};

TaskRecorder.prototype.resetWorkspaceState = function() {
    this.currentRecording = null;
    this.selectedRecording = null;
    this.selectedTask = null;
    this.recordingMode = 'new_task';
    this.token = localStorage.getItem('auth_token');

    this.syncRecordingModeControls();
    this.updateSelectionDisplay();
    this.renderIdleRecordingState(
        '未开始录制',
        this.isConnected ? '请选择任务并点击开始录制' : '-'
    );
};

TaskRecorder.prototype.restoreWorkspaceContext = function(bootstrapResult) {
    var currentRecording = bootstrapResult && bootstrapResult.current_recording
        ? bootstrapResult.current_recording
        : null;

    this.token = localStorage.getItem('auth_token');
    this.currentRecording = currentRecording;
    this.selectedTask = null;

    if (currentRecording) {
        this.recordingMode = 'append_data';
        this.selectedRecording = { directory_name: currentRecording };
    } else {
        this.recordingMode = 'new_task';
        this.selectedRecording = null;
    }

    this.syncRecordingModeControls();
    this.updateSelectionDisplay();
};

TaskRecorder.prototype.syncRecordingModeControls = function() {
    if (this.newTaskModeRadio) {
        this.newTaskModeRadio.checked = this.recordingMode !== 'append_data';
    }
    if (this.appendDataModeRadio) {
        this.appendDataModeRadio.checked = this.recordingMode === 'append_data';
    }
};

TaskRecorder.prototype.resetRecordingRuntimeState = function() {
    this.stopRuntimeKeepalive();
    this.isRecording = false;
    this.isPaused = false;
    this.recordedActionsCount = 0;
    this.explorationTaskId = null;
    this.recordingSessionId = null;
    this.recordingStartTime = null;
    this.clearOperationStatus();
    this.setOperationPending(false);
};

TaskRecorder.prototype.renderIdleRecordingState = function(statusText, displayText) {
    if (this.toggleRecordingBtn) {
        this.toggleRecordingBtn.className = 'btn btn-success';
        this.toggleRecordingBtn.innerHTML = '<span class="glyphicon glyphicon-play"></span> 开始录制';
        this.toggleRecordingBtn.disabled = false;
    }
    if (this.recordingIndicator) {
        this.recordingIndicator.className = 'recording-indicator';
    }
    if (this.recordingStatusText) {
        this.recordingStatusText.textContent = statusText || '未开始录制';
        this.recordingStatusText.className = 'recording-status-text';
    }
    if (this.recordingStatusDisplay) {
        this.recordingStatusDisplay.textContent = typeof displayText === 'string'
            ? displayText
            : (this.isConnected ? '请选择任务并点击开始录制' : '-');
    }
    this.setSelectionControlsDisabled(false);
    if (this.newTaskModeRadio) {
        this.newTaskModeRadio.disabled = false;
    }
    if (this.appendDataModeRadio) {
        this.appendDataModeRadio.disabled = false;
    }
    this.updatePauseButtonState();
    this.updateSelectionDisplay();
};

TaskRecorder.prototype.handleWebSocketMessage = function(message) {
    switch (message.type) {
        case 'connected':
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.deviceSessionId = message.device_session_id || null;
            this.updateConnectionState(true);
            this.startHeartbeat();
            this.updateDeviceInfo(message);
            break;

        case 'screen_frame':
            this.updateScreenFrame(message);
            break;

        case 'error':
            this.showError(message.message);
            break;

        case 'recording_ready':
            this.handleRecordingReady(message);
            break;

        case 'recording_stopped':
            this.handleRecordingStopped(message);
            break;

        case 'recording_error':
            this.handleRecordingError(message);
            break;

        case 'recording_paused':
            this.handleRecordingPaused(message);
            break;

        case 'recording_resumed':
            this.handleRecordingResumed(message);
            break;

        case 'operation_feedback':
            this.handleOperationFeedbackMessage(message);
            break;

        case 'session_event':
            this.handleSessionEvent(message);
            break;

        case 'ping':
            // 服务端发来 ping，回应 pong 保持连接
            if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                this.websocket.send(JSON.stringify({
                    type: 'pong',
                    timestamp: message.timestamp
                }));
            }
            break;

        case 'pong':
            this.handlePong(message);
            break;

        default:
            console.log('Unknown message type:', message.type);
    }
};

TaskRecorder.prototype.handleOperationFeedbackMessage = function(message) {
    this.handleOperationFeedback(
        message.operation_type,
        message.success,
        message.error_message,
        message.data,
        message.recorded,
        message.recording_state
    );
};

// Heartbeat methods
TaskRecorder.prototype.startHeartbeat = function() {
    var self = this;

    // 清除已有的心跳定时器
    this.stopHeartbeat();

    console.debug('💓 Starting heartbeat mechanism');

    // 定期发送 ping
    this.heartbeatInterval = setInterval(function() {
        if (self.websocket && self.websocket.readyState === WebSocket.OPEN) {
            var pingTime = Date.now();
            self.websocket.send(JSON.stringify({
                type: 'ping',
                timestamp: pingTime
            }));
            console.debug('💓 Ping sent at', new Date(pingTime).toISOString());

            // 设置超时检测
            self.heartbeatTimeout = setTimeout(function() {
                console.warn('💔 Heartbeat timeout - no pong received');
                // 超时未收到 pong，可能连接已断开
                if (self.isConnected) {
                    self.updateConnectionState(true, '连接不稳定');
                }
            }, self.heartbeatTimeoutMs);
        }
    }, self.heartbeatIntervalMs);
};

TaskRecorder.prototype.stopHeartbeat = function() {
    if (this.heartbeatInterval) {
        clearInterval(this.heartbeatInterval);
        this.heartbeatInterval = null;
    }
    if (this.heartbeatTimeout) {
        clearTimeout(this.heartbeatTimeout);
        this.heartbeatTimeout = null;
    }
    console.debug('💓 Heartbeat stopped');
};

TaskRecorder.prototype.startRuntimeKeepalive = function() {
    var self = this;
    this.stopRuntimeKeepalive();
    this.runtimeKeepaliveTimer = setInterval(function() {
        if (!self.isRecording || !self.recordingSessionId || !self.websocket || self.websocket.readyState !== WebSocket.OPEN) {
            return;
        }
        self.websocket.send(JSON.stringify({
            type: 'runtime_keepalive',
            session_id: self.recordingSessionId
        }));
    }, 30000);
};

TaskRecorder.prototype.stopRuntimeKeepalive = function() {
    if (this.runtimeKeepaliveTimer) {
        clearInterval(this.runtimeKeepaliveTimer);
        this.runtimeKeepaliveTimer = null;
    }
};

TaskRecorder.prototype.handlePong = function(message) {
    // 清除超时定时器
    if (this.heartbeatTimeout) {
        clearTimeout(this.heartbeatTimeout);
        this.heartbeatTimeout = null;
    }

    this.lastPongTime = Date.now();
    var latency = this.lastPongTime - (message.timestamp * 1000 || this.lastPongTime);

    console.debug('💓 Pong received, latency:', latency.toFixed(0), 'ms');

    // 如果之前显示连接不稳定，恢复正常状态
    if (this.isConnected && this.statusIndicator && this.statusIndicator.textContent === '连接不稳定') {
        this.updateConnectionState(true);
    }
};

TaskRecorder.prototype.handleSessionEvent = function(message) {
    var scope = message.scope;
    var detail = message.message || '会话已失效';

    if (scope === 'auth') {
        this.userDisconnected = true;
        api.handleAuthExpired();
        return;
    }

    if (scope === 'workspace') {
        this.userDisconnected = true;
        if (window.app && typeof window.app.handleWorkspaceExpired === 'function') {
            window.app.handleWorkspaceExpired({ detail: detail, code: message.code });
        }
        return;
    }

    if (scope === 'device') {
        this.userDisconnected = true;
        this.showError('设备连接已过期：' + detail);
        this.disconnect();
        return;
    }

    if (scope === 'runtime') {
        this.showError('录制会话已失效：' + detail);
        this.resetRecordingRuntimeState();
        this.renderIdleRecordingState('录制会话已失效', '请重新开始录制');
    }
};

TaskRecorder.prototype.updateScreenFrame = function(message) {
    if (this.screenImage) {
        this.screenImage.src = message.image;
        this.screenImage.style.display = 'block';
        this.frameCount++;
        
        // 隐藏占位符文本
        if (this.screenPlaceholder) {
            this.screenPlaceholder.style.display = 'none';
        }
        
        // 更新设备信息
        this.updateDeviceInfo({
            width: message.width,
            height: message.height,
            orientation: message.orientation,
            timestamp: message.timestamp
        });
        
        // 更新帧计数
        if (this.frameCounter) {
            this.frameCounter.textContent = 'Frames: ' + this.frameCount;
        }
    }
};

TaskRecorder.prototype.updateDeviceInfo = function(info) {
    if (this.deviceInfo) {
        var infoText = 'Device: ' + this.deviceSerial;
        if (info.width && info.height) {
            infoText += ' | ' + info.width + 'x' + info.height;
        }
        if (info.orientation !== undefined) {
            infoText += ' | ' + info.orientation + '°';
        }
        this.deviceInfo.textContent = infoText;
    }
};

TaskRecorder.prototype.handleScreenClick = function(event) {
    if (!this.isConnected || this.isSwipeMode || this.operationPending) return;
    
    var coords = this.getRelativeCoordinates(event);
    
    // 触摸命令将发送到后端，如果正在录制，后端会自动处理录制
    this.sendTouchCommand(coords.x, coords.y);
};

TaskRecorder.prototype.handleMouseDown = function(event) {
    if (!this.isConnected || !this.isSwipeMode || this.operationPending) return;
    
    // 阻止默认行为，防止图片拖拽
    event.preventDefault();
    event.stopPropagation();
    
    var coords = this.getRelativeCoordinates(event);
    this.swipeStartCoordinates = coords;
};

TaskRecorder.prototype.handleMouseMove = function(event) {
    if (!this.isConnected || !this.isSwipeMode || !this.swipeStartCoordinates || this.operationPending) return;
    
    // 可以在这里显示滑动预览
    var coords = this.getRelativeCoordinates(event);
    this.showSwipePreview(this.swipeStartCoordinates, coords);
};

TaskRecorder.prototype.handleMouseUp = function(event) {
    if (!this.isConnected || !this.isSwipeMode || !this.swipeStartCoordinates || this.operationPending) return;
    
    var coords = this.getRelativeCoordinates(event);
    this.sendSwipeCommand(this.swipeStartCoordinates.x, this.swipeStartCoordinates.y, coords.x, coords.y);
    this.swipeStartCoordinates = null;
    this.hideSwipePreview();
};

TaskRecorder.prototype.getRelativeCoordinates = function(event) {
    var rect = this.screenImage.getBoundingClientRect();
    var x = Math.round((event.clientX - rect.left) / rect.width * 1000);
    var y = Math.round((event.clientY - rect.top) / rect.height * 1000);
    return { x: x, y: y };
};

TaskRecorder.prototype.sendTouchCommand = function(x, y) {
    if (this.websocket && this.isConnected && !this.operationPending && this.isRecording) {
        this.setOperationPending(true);
        this.operationStartTime = Date.now();
        this.updateOperationStatusWithTiming('Touch(x=' + x + ', y=' + y + ')', 'touch');

        this.websocket.send(JSON.stringify({
            type: 'touch',
            x: x,
            y: y
        }));
        console.log('Sent touch: (' + x + ', ' + y + ')');

        if (!this.isPaused) {
            this.recordedActionsCount++;
        }
    } else if (!this.isRecording && this.isConnected) {
        this.showError('请先开始录制再进行操作');
    }
};

TaskRecorder.prototype.sendSwipeCommand = function(startX, startY, endX, endY) {
    if (this.websocket && this.isConnected && !this.operationPending && this.isRecording) {
        this.setOperationPending(true);
        this.operationStartTime = Date.now();
        this.updateOperationStatusWithTiming('Swipe(start_x=' + startX + ', start_y=' + startY + ', end_x=' + endX + ', end_y=' + endY + ')', 'swipe');

        this.websocket.send(JSON.stringify({
            type: 'swipe',
            start_x: startX,
            start_y: startY,
            end_x: endX,
            end_y: endY
        }));
        console.log('Sent swipe: (' + startX + ', ' + startY + ') -> (' + endX + ', ' + endY + ')');

        if (!this.isPaused) {
            this.recordedActionsCount++;
        }
    } else if (!this.isRecording && this.isConnected) {
        this.showError('请先开始录制再进行操作');
    }
};

TaskRecorder.prototype.sendKey = function(keyCode) {
    if (this.websocket && this.isConnected && !this.operationPending && this.isRecording) {
        this.setOperationPending(true);
        this.operationStartTime = Date.now();
        this.updateOperationStatusWithTiming('Key(key_code=' + keyCode + ')', 'key');

        this.websocket.send(JSON.stringify({
            type: 'key',
            key_code: keyCode
        }));
        console.log('Sent key: ' + keyCode);

        if (!this.isPaused) {
            this.recordedActionsCount++;
        }
    } else if (!this.isRecording && this.isConnected) {
        this.showError('请先开始录制再进行操作');
    }
};

TaskRecorder.prototype.sendText = function() {
    var text = this.textInput ? this.textInput.value : '';
    if (text && this.websocket && this.isConnected && !this.operationPending && this.isRecording) {
        this.setOperationPending(true);
        this.operationStartTime = Date.now();
        this.updateOperationStatusWithTiming('Text(text="' + text + '")', 'text');

        this.websocket.send(JSON.stringify({
            type: 'text',
            text: text
        }));

        console.log('Sent text: ' + text);

        if (!this.isPaused) {
            this.recordedActionsCount++;
        }

        if (this.textInput) {
            this.textInput.value = '';
        }
    } else if (!this.isRecording && this.isConnected && text) {
        this.showError('请先开始录制再进行操作');
    }
};

TaskRecorder.prototype.setTouchMode = function() {
    this.isSwipeMode = false;
    if (this.touchModeBtn) {
        this.touchModeBtn.classList.add('active');
    }
    if (this.swipeModeBtn) {
        this.swipeModeBtn.classList.remove('active');
    }
    if (this.screenImage) {
        this.screenImage.style.cursor = 'pointer';
        // Touch Mode 下也禁用拖拽，避免干扰触摸操作
        this.screenImage.draggable = false;
        this.screenImage.style.userSelect = 'none';
        this.screenImage.style.webkitUserSelect = 'none';
        this.screenImage.style.mozUserSelect = 'none';
        this.screenImage.style.msUserSelect = 'none';
    }
};

TaskRecorder.prototype.setSwipeMode = function() {
    this.isSwipeMode = true;
    if (this.swipeModeBtn) {
        this.swipeModeBtn.classList.add('active');
    }
    if (this.touchModeBtn) {
        this.touchModeBtn.classList.remove('active');
    }
    if (this.screenImage) {
        this.screenImage.style.cursor = 'grab';
        // 禁用图片拖拽以防止与滑动操作冲突
        this.screenImage.draggable = false;
        this.screenImage.style.userSelect = 'none';
        this.screenImage.style.webkitUserSelect = 'none';
        this.screenImage.style.mozUserSelect = 'none';
        this.screenImage.style.msUserSelect = 'none';
    }
};

TaskRecorder.prototype.updateConnectionState = function(connected, message) {
    this.isConnected = connected;
    message = message || '';
    
    if (this.statusIndicator) {
        this.statusIndicator.className = connected ? 'screen-status status-connected' : 'screen-status status-disconnected';
        this.statusIndicator.textContent = message || (connected ? '已连接' : '未连接');
    }
    
    if (this.toggleConnectionBtn) {
        this.toggleConnectionBtn.textContent = connected ? '断开连接' : '连接';
        this.toggleConnectionBtn.className = connected ? 'btn btn-secondary' : 'btn btn-primary';
        this.toggleConnectionBtn.disabled = false;
    }
    
    if (this.controlPanel) {
        this.controlPanel.style.display = connected ? 'block' : 'none';
    }
    
    // 控制设备选择器状态
    if (this.deviceSelect) {
        this.deviceSelect.disabled = connected;
    }
    
    // 控制任务/录制数据选择器状态
    this.setSelectionControlsDisabled(this.isRecording);
    this.updateSelectionDisplay();

    // 录制时禁用单选按钮，不能切换模式
    if (this.newTaskModeRadio) {
        this.newTaskModeRadio.disabled = this.isRecording;
    }
    if (this.appendDataModeRadio) {
        this.appendDataModeRadio.disabled = this.isRecording;
    }
    
    // 更新状态显示区域
    if (this.recordingStatusDisplay) {
        if (connected) {
            if (this.isRecording) {
                var currentTask = this.getCurrentTaskText();
                if (this.isPaused) {
                    this.recordingStatusDisplay.textContent = '当前任务（已暂停）: ' + currentTask;
                } else {
                    this.recordingStatusDisplay.textContent = '当前任务: ' + currentTask;
                }
            } else {
                // 连接成功但未录制时提示选择任务
                this.recordingStatusDisplay.textContent = '请选择任务并点击开始录制';
            }
        } else {
            // 未连接时显示 "-"
            this.recordingStatusDisplay.textContent = '-';
        }
    }
    
    if (this.operationStatusDisplay) {
        if (!connected) {
            this.operationStatusDisplay.textContent = '-';
        }
    }

    this.updatePauseButtonState();
    
    // 控制屏幕显示和占位符的可见性
    if (!connected) {
        // 断开连接时显示占位符，隐藏屏幕图像
        if (this.screenImage) {
            this.screenImage.style.display = 'none';
        }
        if (this.screenPlaceholder) {
            this.screenPlaceholder.style.display = 'block';
        }
        // 重置帧计数
        this.frameCount = 0;
        if (this.frameCounter) {
            this.frameCounter.textContent = '';
        }
    }
};

TaskRecorder.prototype.handleDisconnection = function() {
    var self = this;
    
    // Don't reconnect if user manually disconnected
    if (this.userDisconnected) {
        console.log('User manually disconnected - not attempting reconnection');
        return;
    }
    
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        this.updateConnectionState(false, '正在重连（' + this.reconnectAttempts + '/' + this.maxReconnectAttempts + '）...');
        
        setTimeout(function() {
            if (!self.isConnected) {
                self.connect();
            }
        }, this.reconnectDelay);
    } else {
        this.updateConnectionState(false, '连接已断开');
    }
};

TaskRecorder.prototype.showSwipePreview = function(start, end) {
    // 创建或更新 Canvas 覆盖层来显示滑动路径
    var canvas = this.swipeCanvas;
    if (!canvas) {
        canvas = document.createElement('canvas');
        canvas.id = 'swipe-preview-canvas';
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.pointerEvents = 'none';
        canvas.style.zIndex = '10';
        
        // 查找正确的容器：screen-display-container
        var container = document.querySelector('.screen-display-container');
        if (!container && this.screenImage) {
            container = this.screenImage.parentElement;
        }
        if (container) {
            container.style.position = 'relative';
            container.appendChild(canvas);
        }
        this.swipeCanvas = canvas;
    }
    
    // 设置 Canvas 尺寸和位置与屏幕图片完全一致
    var rect = this.screenImage.getBoundingClientRect();
    var containerRect = canvas.parentElement.getBoundingClientRect();
    
    canvas.width = rect.width;
    canvas.height = rect.height;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    canvas.style.left = (rect.left - containerRect.left) + 'px';
    canvas.style.top = (rect.top - containerRect.top) + 'px';
    
    // 绘制滑动预览线条
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // 转换相对坐标到 Canvas 像素坐标
    var startPixelX = (start.x / 1000) * canvas.width;
    var startPixelY = (start.y / 1000) * canvas.height;
    var endPixelX = (end.x / 1000) * canvas.width;
    var endPixelY = (end.y / 1000) * canvas.height;
    
    // 绘制滑动路径
    ctx.strokeStyle = '#4CAF50';
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    ctx.setLineDash([5, 5]);
    
    ctx.beginPath();
    ctx.moveTo(startPixelX, startPixelY);
    ctx.lineTo(endPixelX, endPixelY);
    ctx.stroke();
    
    // 绘制起始点
    ctx.fillStyle = '#4CAF50';
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(startPixelX, startPixelY, 8, 0, 2 * Math.PI);
    ctx.fill();
    
    // 绘制箭头表示方向
    var angle = Math.atan2(endPixelY - startPixelY, endPixelX - startPixelX);
    var arrowLength = 15;
    var arrowAngle = Math.PI / 6;
    
    ctx.strokeStyle = '#4CAF50';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(endPixelX, endPixelY);
    ctx.lineTo(
        endPixelX - arrowLength * Math.cos(angle - arrowAngle),
        endPixelY - arrowLength * Math.sin(angle - arrowAngle)
    );
    ctx.moveTo(endPixelX, endPixelY);
    ctx.lineTo(
        endPixelX - arrowLength * Math.cos(angle + arrowAngle),
        endPixelY - arrowLength * Math.sin(angle + arrowAngle)
    );
    ctx.stroke();
};

TaskRecorder.prototype.hideSwipePreview = function() {
    // 隐藏滑动预览 Canvas
    if (this.swipeCanvas) {
        var ctx = this.swipeCanvas.getContext('2d');
        ctx.clearRect(0, 0, this.swipeCanvas.width, this.swipeCanvas.height);
    }
};

TaskRecorder.prototype.showError = function(message) {
    console.error('Task Recorder Error:', message);
    if (window.showError) {
        window.showError(message);
    } else {
        alert('任务录制错误：' + message);
    }
};

// Enhanced operation status methods with timing
TaskRecorder.prototype.updateOperationStatusWithTiming = function(operation, operationType) {
    if (this.operationStatusDisplay) {
        this.currentOperation = {
            text: operation,
            type: operationType,
            startTime: this.operationStartTime || Date.now()
        };
        
        this.updateOperationStatusDisplay();
        this.startOperationTimer();
    }
};

TaskRecorder.prototype.updateOperationStatusDisplay = function() {
    if (this.operationStatusDisplay && this.currentOperation) {
        var elapsed = ((Date.now() - this.currentOperation.startTime) / 1000).toFixed(1);
        this.operationStatusDisplay.textContent = this.currentOperation.text + '...' + elapsed + '秒';
    }
};

TaskRecorder.prototype.startOperationTimer = function() {
    var self = this;
    
    // Clear any existing timer
    if (this.operationStatusTimer) {
        clearInterval(this.operationStatusTimer);
    }
    
    // Update timer every 100ms to show elapsed time
    this.operationStatusTimer = setInterval(function() {
        if (self.currentOperation && self.operationStatusDisplay) {
            self.updateOperationStatusDisplay();
        } else {
            clearInterval(self.operationStatusTimer);
            self.operationStatusTimer = null;
        }
    }, 100);
};

TaskRecorder.prototype.handleOperationFeedback = function(operationType, success, errorMessage, responseData, recorded, recordingState) {
    // Clear the pending state first
    this.setOperationPending(false);

    if (recordingState === 'paused') {
        this.isPaused = true;
        this.updatePauseButtonState();
    }
    
    if (this.operationStatusDisplay) {
        // Clear the timer
        if (this.operationStatusTimer) {
            clearInterval(this.operationStatusTimer);
            this.operationStatusTimer = null;
        }
        
        if (this.currentOperation) {
            var elapsed = ((Date.now() - this.currentOperation.startTime) / 1000).toFixed(1);
            
            if (success) {
                var successText = this.formatOperationText(operationType, responseData);
                if (recorded === false) {
                    this.operationStatusDisplay.textContent = successText + '已执行（未记录）,耗时' + elapsed + '秒';
                } else {
                    this.operationStatusDisplay.textContent = successText + '成功,耗时' + elapsed + '秒';
                }
            } else {
                var failureText = this.formatOperationText(operationType, responseData);
                this.operationStatusDisplay.textContent = failureText + '失败,' + errorMessage;
            }
            
            this.currentOperation = null;
        }
    }
    
    // 新增：如果操作成功且正在录制，刷新 UTG 显示
    if (success && recorded !== false && this.isRecording && this.currentRecording) {
        // 直接调用 UTGViewer 的 loadUTG 方法刷新图形
        if (window.app && window.app.utgViewer && typeof window.app.utgViewer.loadUTG === 'function') {
            window.app.utgViewer.loadUTG();
        }
    }
};

TaskRecorder.prototype.formatOperationText = function(operationType, data) {
    switch (operationType) {
        case 'touch':
            return '点击(x=' + (data && data.x || 0) + ', y=' + (data && data.y || 0) + ')';
        case 'swipe':
            return '滑动(start_x=' + (data && data.start_x || 0) + ', start_y=' + (data && data.start_y || 0) +
                   ', end_x=' + (data && data.end_x || 0) + ', end_y=' + (data && data.end_y || 0) + ')';
        case 'key':
            return '按键(key_code=' + (data && data.key_code || '未知') + ')';
        case 'text':
            return '文本(text="' + (data && data.text || '') + '")';
        default:
            return operationType;
    }
};

TaskRecorder.prototype.getPausedHintText = function() {
    return '已暂停，可继续操作，但不会记录';
};

TaskRecorder.prototype.updatePauseButtonState = function() {
    if (!this.pauseRecordingBtn) {
        return;
    }

    this.pauseRecordingBtn.disabled = !this.isConnected || !this.isRecording || this.operationPending;
    if (this.isPaused) {
        this.pauseRecordingBtn.innerHTML = '<span class="glyphicon glyphicon-play"></span> 继续录制';
    } else {
        this.pauseRecordingBtn.innerHTML = '<span class="glyphicon glyphicon-pause"></span> 暂停录制';
    }
};

TaskRecorder.prototype.clearOperationStatus = function() {
    if (this.operationStatusTimer) {
        clearInterval(this.operationStatusTimer);
        this.operationStatusTimer = null;
    }
    
    this.currentOperation = null;
    this.operationStartTime = null;
    
    if (this.operationStatusDisplay && this.isConnected) {
        if (this.isRecording) {
            this.operationStatusDisplay.textContent = this.isPaused ? this.getPausedHintText() : '等待操作';
        } else {
            this.operationStatusDisplay.textContent = '请先开始录制';
        }
    } else if (this.operationStatusDisplay) {
        this.operationStatusDisplay.textContent = '-';
    }
};

// Operation pending state management
TaskRecorder.prototype.setOperationPending = function(pending) {
    this.operationPending = pending;
    this.updateControlsState();
    this.updatePauseButtonState();
};

TaskRecorder.prototype.updateControlsState = function() {
    // Disable/enable screen interaction
    if (this.screenImage) {
        if (this.operationPending) {
            this.screenImage.style.pointerEvents = 'none';
            this.screenImage.style.opacity = '0.7';
        } else {
            this.screenImage.style.pointerEvents = 'auto';
            this.screenImage.style.opacity = '1.0';
        }
    }
    
    // Disable/enable HOME and BACK buttons
    if (this.homeBtn) {
        this.homeBtn.disabled = this.operationPending;
    }
    if (this.backBtn) {
        this.backBtn.disabled = this.operationPending;
    }
    
    // Disable/enable PutText button (but keep text input enabled)
    if (this.sendTextBtn) {
        this.sendTextBtn.disabled = this.operationPending;
    }
};

TaskRecorder.prototype.getCurrentTaskText = function() {
    if (this.recordingMode === 'append_data') {
        if (this.selectedRecording) {
            return this.formatRecordingLabel(this.selectedRecording);
        }
        if (this.currentRecording) {
            return this.currentRecording;
        }
        return '未选择录制数据';
    } else {
        if (this.selectedTask) {
            return this.formatTaskLabel(this.selectedTask);
        }
        return '未选择任务';
    }
};

// Recording message handlers
TaskRecorder.prototype.handleRecordingReady = async function(message) {
    console.log('Recording ready:', message);

    this.isRecording = true;
    this.isPaused = false;
    this.recordedActionsCount = 0;
    this.explorationTaskId = message.task_id;
    this.recordingSessionId = message.session_id || null;
    this.currentRecording = message.dataset; // 保存当前录制的数据
    this.startRuntimeKeepalive();

    // Clear recording start timing and show waiting status
    this.clearOperationStatus();

    // Update UI state
    if (this.toggleRecordingBtn) {
        this.toggleRecordingBtn.className = 'btn btn-danger';
        this.toggleRecordingBtn.innerHTML = '<span class="glyphicon glyphicon-stop"></span> 停止录制';
        this.toggleRecordingBtn.disabled = false;
    }
    if (this.recordingIndicator) {
        this.recordingIndicator.className = 'recording-indicator recording';
    }
    if (this.recordingStatusText) {
        this.recordingStatusText.textContent = '录制中...';
        this.recordingStatusText.className = 'recording-status-text recording';
    }

    this.updatePauseButtonState();

    // 更新状态显示区域
    if (this.recordingStatusDisplay) {
        var currentTask = this.getCurrentTaskText();
        this.recordingStatusDisplay.textContent = '当前任务: ' + currentTask;
    }

    // Set operation status to waiting
    if (this.operationStatusDisplay) {
        this.operationStatusDisplay.textContent = '等待操作';
    }

    // 禁用任务/录制数据选择器
    this.setSelectionControlsDisabled(true);

    // 录制开始时，切换到当前录制数据并加载 Task Info 和 UTG
    if (this.currentRecording && window.app && window.app.utgViewer) {
        if (typeof window.app.utgViewer.switchToRecording === 'function') {
            window.app.utgViewer.switchToRecording(this.currentRecording);
        }
    }
};

TaskRecorder.prototype.handleRecordingStopped = function(message) {
    console.log('Recording stopped:', message);

    this.isRecording = false;
    this.isPaused = false;
    this.recordingSessionId = null;
    this.stopRuntimeKeepalive();

    // Clear any ongoing operation status and reset to "-"
    this.clearOperationStatus();

    // Update UI state
    if (this.toggleRecordingBtn) {
        this.toggleRecordingBtn.className = 'btn btn-success';
        this.toggleRecordingBtn.innerHTML = '<span class="glyphicon glyphicon-play"></span> 开始录制';
        this.toggleRecordingBtn.disabled = false;  // 重新启用按钮
    }

    var actionCount = message.action_count || this.recordedActionsCount;
    if (this.recordingIndicator) {
        this.recordingIndicator.className = 'recording-indicator';
    }
    if (this.recordingStatusText) {
        this.recordingStatusText.textContent = '已停止（已记录 ' + actionCount + ' 个操作）';
        this.recordingStatusText.className = 'recording-status-text';
    }

    this.updatePauseButtonState();

    // 更新状态显示区域
    if (this.recordingStatusDisplay) {
        this.recordingStatusDisplay.textContent = '请选择任务并点击开始录制';
    }

    // 重新启用任务/录制数据选择器
    this.setSelectionControlsDisabled(false);
    this.updateSelectionDisplay();

    // 重新启用录制模式选择器
    if (this.newTaskModeRadio) {
        this.newTaskModeRadio.disabled = false;
    }
    if (this.appendDataModeRadio) {
        this.appendDataModeRadio.disabled = false;
    }

    // 录制结束后刷新录制数据展示（新增录制会在弹窗中加载）
    this.loadDatasets();

    // 录制结束，刷新 UTG 显示
    if (this.currentRecording) {
        // 直接调用 UTGViewer 的 loadUTG 方法刷新图形
        if (window.app && window.app.utgViewer && typeof window.app.utgViewer.loadUTG === 'function') {
            window.app.utgViewer.loadUTG();
        }
    }
};

TaskRecorder.prototype.handleRecordingError = function(message) {
    console.error('Recording error:', message);

    this.showError('录制错误：' + message.message);

    // Reset recording state and clear operation status
    this.isRecording = false;
    this.isPaused = false;
    this.recordingSessionId = null;
    this.stopRuntimeKeepalive();
    this.clearOperationStatus();

    if (this.toggleRecordingBtn) {
        this.toggleRecordingBtn.className = 'btn btn-success';
        this.toggleRecordingBtn.innerHTML = '<span class="glyphicon glyphicon-play"></span> 开始录制';
        this.toggleRecordingBtn.disabled = false;  // 重新启用按钮
    }
    if (this.recordingIndicator) {
        this.recordingIndicator.className = 'recording-indicator';
    }
    if (this.recordingStatusText) {
        this.recordingStatusText.textContent = '错误';
        this.recordingStatusText.className = 'recording-status-text';
    }

    this.updatePauseButtonState();

    // 更新状态显示区域
    if (this.recordingStatusDisplay) {
        this.recordingStatusDisplay.textContent = '请选择任务并点击开始录制';
    }

    // 重新启用任务/录制数据选择器
    this.setSelectionControlsDisabled(false);
    this.updateSelectionDisplay();

    // 重新启用录制模式选择器
    if (this.newTaskModeRadio) {
        this.newTaskModeRadio.disabled = false;
    }
    if (this.appendDataModeRadio) {
        this.appendDataModeRadio.disabled = false;
    }
};

TaskRecorder.prototype.handleRecordingPaused = function(message) {
    console.log('Recording paused:', message);

    this.isPaused = true;
    this.clearOperationStatus();
    this.stopRuntimeKeepalive();
    this.updatePauseButtonState();

    if (this.recordingStatusText) {
        this.recordingStatusText.textContent = this.getPausedHintText();
        this.recordingStatusText.className = 'recording-status-text recording';
    }
    if (this.recordingStatusDisplay) {
        this.recordingStatusDisplay.textContent = '当前任务（已暂停）: ' + this.getCurrentTaskText();
    }
};

TaskRecorder.prototype.handleRecordingResumed = function(message) {
    console.log('Recording resumed:', message);

    this.isPaused = false;
    this.clearOperationStatus();
    this.startRuntimeKeepalive();
    this.updatePauseButtonState();

    if (this.recordingStatusText) {
        this.recordingStatusText.textContent = '录制中...';
        this.recordingStatusText.className = 'recording-status-text recording';
    }
    if (this.recordingStatusDisplay) {
        this.recordingStatusDisplay.textContent = '当前任务: ' + this.getCurrentTaskText();
    }
};

// Recording methods
TaskRecorder.prototype.toggleRecording = function() {
    if (this.isRecording) {
        this.stopRecording();
    } else {
        this.startRecording();
    }
};

TaskRecorder.prototype.startRecording = async function() {

    if (!this.isConnected) {
        this.showError('开始录制前请先连接设备');
        return;
    }

    if (!this.websocket) {
        this.showError('WebSocket 连接不可用');
        return;
    }

    var selectedValue = this.taskSelect ? this.taskSelect.value : null;
    if (!selectedValue) {
        var errorMsg = this.recordingMode === 'new_task'
            ? '开始录制前请先选择任务'
            : '开始录制前请先选择录制数据';
        this.showError(errorMsg);
        return;
    }

    // Get checkbox states
    var useImageState = this.useImageStateCheckbox ? this.useImageStateCheckbox.checked : false;

    // Get mode from radio buttons ：str
    var viewModeRadios = document.getElementsByName('view-mode');
    var views_mode = "xml_mode"; // 默认值
    for (var i = 0; i < viewModeRadios.length; i++) {
        if (viewModeRadios[i].checked) {
            views_mode = viewModeRadios[i].value; // yolo_mode / cv_mode / xml_mode
            break;
        }
    }

    // Start recording timing
    this.isPaused = false;
    this.recordingSessionId = null;
    this.recordingStartTime = Date.now();
    this.updateOperationStatusWithTiming('正在启动录制', 'starting_recording');

    // Send start recording command via WebSocket
    try {
        await api.ensureFreshToken(localStorage.getItem('auth_token'));
        // 根据录制模式构建不同的消息
        var message = {
            type: 'start_recording',
            device_serial: this.deviceSerial,
            views_mode: views_mode,
            use_image_state: useImageState,
            recording_mode: this.recordingMode
        };

        if (this.recordingMode === 'new_task') {
            message.task_id = selectedValue;
            message.auth_token = localStorage.getItem('auth_token');
        } else if (this.recordingMode === 'append_data') {
            message.dataset = selectedValue;
        }

        this.websocket.send(JSON.stringify(message));

        console.log('Sent start recording command');

        // Update UI immediately to show that we're trying to start recording
        if (this.toggleRecordingBtn) {
            this.toggleRecordingBtn.disabled = true;
        }
        this.updatePauseButtonState();
        if (this.recordingIndicator) {
            this.recordingIndicator.className = 'recording-indicator';
        }
        if (this.recordingStatusText) {
            this.recordingStatusText.textContent = '启动中...';
            this.recordingStatusText.className = 'recording-status-text';
        }

        // 立即禁用任务/录制数据选择器和录制模式选择器
        this.setSelectionControlsDisabled(true);
        if (this.newTaskModeRadio) {
            this.newTaskModeRadio.disabled = true;
        }
        if (this.appendDataModeRadio) {
            this.appendDataModeRadio.disabled = true;
        }

    } catch (error) {
        console.error('Error sending start recording command:', error);
        this.showError('发送开始录制指令失败：' + error.message);

        // Reset operation status on error
        this.clearOperationStatus();

        // Reset button state on error
        if (this.toggleRecordingBtn) {
            this.toggleRecordingBtn.disabled = false;
        }

        // 出错时也要重新启用任务选择器和模式选择器
        this.setSelectionControlsDisabled(false);
        if (this.newTaskModeRadio) {
            this.newTaskModeRadio.disabled = false;
        }
        if (this.appendDataModeRadio) {
            this.appendDataModeRadio.disabled = false;
        }
        this.updatePauseButtonState();
    }
};

TaskRecorder.prototype.stopRecording = function() {

    if (!this.isRecording) {
        return;
    }

    if (!this.websocket) {
        this.showError('WebSocket 连接不可用');
        return;
    }

    // Start stop recording timing
    this.operationStartTime = Date.now();
    this.updateOperationStatusWithTiming('正在结束录制', 'stopping_recording');

    // Send stop recording command via WebSocket
    try {
        this.websocket.send(JSON.stringify({
            type: 'stop_recording',
            device_serial: this.deviceSerial,
            session_id: this.recordingSessionId
        }));
        this.stopRuntimeKeepalive();

        console.log('Sent stop recording command');
        if (this.recordingIndicator) {
            this.recordingIndicator.className = 'recording-indicator';
        }
        if (this.recordingStatusText) {
            this.recordingStatusText.textContent = '停止中...';
            this.recordingStatusText.className = 'recording-status-text';
        }
        if (this.pauseRecordingBtn) {
            this.pauseRecordingBtn.disabled = true;
        }

        // 注意：不在这里修改 isRecording 状态，等待服务器确认
        // isRecording 将在 handleRecordingStopped 或 handleRecordingError 中设置为 false

    } catch (error) {
        console.error('Error sending stop recording command:', error);
        this.showError('发送停止录制指令失败：' + error.message);

        // Reset operation status on error
        this.clearOperationStatus();

        // 如果发送命令本身就失败了（客户端错误），则立即重置状态
        if (this.toggleRecordingBtn) {
            this.toggleRecordingBtn.className = 'btn btn-success';
            this.toggleRecordingBtn.innerHTML = '<span class="glyphicon glyphicon-play"></span> 开始录制';
            this.toggleRecordingBtn.disabled = false;
        }
        this.isRecording = false;

        // 重新启用录制模式选择器
        if (this.newTaskModeRadio) {
            this.newTaskModeRadio.disabled = false;
        }
        if (this.appendDataModeRadio) {
            this.appendDataModeRadio.disabled = false;
        }
        this.updatePauseButtonState();
    }
};

TaskRecorder.prototype.pauseRecording = function() {
    if (!this.isRecording || this.isPaused) {
        return;
    }

    if (!this.websocket) {
        this.showError('WebSocket 连接不可用');
        return;
    }

    try {
        this.websocket.send(JSON.stringify({
            type: 'pause_recording',
            device_serial: this.deviceSerial,
            session_id: this.recordingSessionId
        }));
        this.stopRuntimeKeepalive();

        if (this.pauseRecordingBtn) {
            this.pauseRecordingBtn.disabled = true;
        }
        if (this.operationStatusDisplay) {
            this.operationStatusDisplay.textContent = '正在暂停录制...';
        }
    } catch (error) {
        console.error('Error sending pause recording command:', error);
        this.showError('发送暂停录制指令失败：' + error.message);
        this.updatePauseButtonState();
    }
};

TaskRecorder.prototype.resumeRecording = function() {
    if (!this.isRecording || !this.isPaused) {
        return;
    }

    if (!this.websocket) {
        this.showError('WebSocket 连接不可用');
        return;
    }

    try {
        this.websocket.send(JSON.stringify({
            type: 'resume_recording',
            device_serial: this.deviceSerial,
            session_id: this.recordingSessionId
        }));

        if (this.pauseRecordingBtn) {
            this.pauseRecordingBtn.disabled = true;
        }
        if (this.operationStatusDisplay) {
            this.operationStatusDisplay.textContent = '正在继续录制...';
        }
    } catch (error) {
        console.error('Error sending resume recording command:', error);
        this.showError('发送继续录制指令失败：' + error.message);
        this.updatePauseButtonState();
    }
};


// 公共方法
TaskRecorder.prototype.initialize = function() {
    this.loadDevices();
    this.setTouchMode(); // 默认触摸模式
};

// Export TaskRecorder class to global scope
window.TaskRecorder = TaskRecorder;
