class DataEditor {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.isVisible = false;

        // Recording management properties
        this.currentRecording = null;
        this.availableRecordings = [];
        this.isLoading = false;
        this.token = localStorage.getItem('auth_token');
    }

    resetWorkspaceState() {
        this.currentRecording = null;
        this.availableRecordings = [];
        this.isLoading = false;
        this.hideRecordingInfo();
        this.renderEmptyRecordingSelector();
    }

    async show() {
        if (!this.container) return;

        this.isVisible = true;
        try {
            const dataEditorHTML = await this.getDataEditorInterface();
            this.container.innerHTML = dataEditorHTML;

            // Initialize components after DOM insertion
            setTimeout(() => {
                this.initializeComponents();
            }, 100);

        } catch (error) {
            console.error('Failed to show data editor interface:', error);
            this.container.innerHTML = '<hr /><h2>错误</h2><p>加载数据编辑界面失败。</p>';
        }
    }

    hide() {
        this.isVisible = false;
    }

    async getDataEditorInterface() {
        try {
            // Load recordings using integrated recording management
            await this.loadRecordings();

            let recordingOptions = '<option value="">选择一条录制数据...</option>';
            if (this.availableRecordings && this.availableRecordings.length > 0) {
                this.availableRecordings.forEach(rec => {
                    const selected = (this.currentRecording === rec.directory_name) ? 'selected' : '';
                    const label = rec.task_description
                        ? `${rec.directory_name} (${rec.task_description})`
                        : rec.directory_name;
                    recordingOptions += `<option value="${rec.directory_name}" ${selected}>${label}</option>`;
                });
            }

            return `
                <hr />
                <h2>数据编辑</h2>
                <div class="form-group">
                    <label for="data-editor-dataset-select">选择录制数据：</label>
                    <select id="data-editor-dataset-select" class="form-control" onchange="window.dataEditor.switchRecording()">
                        ${recordingOptions}
                    </select>
                </div>

                <!-- Recording Information Display -->
                <div id="dataset-info-panel" style="display: none;">
                    <div id="dataset-details">
                        <!-- Recording details will be populated here -->
                    </div>
                </div>
            `;
        } catch (error) {
            console.error('Failed to generate data editor interface:', error);
            return '<hr /><h2>错误</h2><p>加载数据编辑界面失败。</p>';
        }
    }

    initializeComponents() {
        // Load and display current recording information
        if (this.currentRecording) {
            this.loadRecordingInfo(this.currentRecording);
        } else {
            this.hideRecordingInfo();
        }
    }

    async switchRecording() {
        const select = document.getElementById('data-editor-dataset-select');
        const selectedRecording = select ? select.value : null;

        if (!selectedRecording || selectedRecording === this.currentRecording) {
            return;
        }

        try {
            this.setLoading(true);

            // Call UTGViewer's switchToRecording method
            if (window.app && window.app.utgViewer && typeof window.app.utgViewer.switchToRecording === 'function') {
                await window.app.utgViewer.switchToRecording(selectedRecording);
            }

            // Update local state
            this.currentRecording = selectedRecording;

            if (window.showSuccess) {
                window.showSuccess(`已切换到录制数据：${selectedRecording}`);
            }

            // Load and display recording information
            await this.loadRecordingInfo(selectedRecording);

        } catch (error) {
            console.error('Failed to switch recording:', error);
            if (window.showError) {
                const errorMessage = (api && typeof api.formatRecordingLockConflict === 'function')
                    ? api.formatRecordingLockConflict(error)
                    : error.message;
                window.showError('切换录制数据失败：' + errorMessage);
            }

            // Revert selector to previous value
            if (select) {
                select.value = this.currentRecording || '';
            }
        } finally {
            this.setLoading(false);
        }
    }

    // Integrated recording management methods
    async loadRecordings() {
        try {
            this.token = localStorage.getItem('auth_token');

            if (!this.token) {
                this.resetWorkspaceState();
                this.clearWorkspaceVisualState();
                return;
            }

            // Get current recording from workspace
            const currentResponse = await api.getCurrentRecording();
            this.currentRecording = currentResponse.current || null;

            try {
                const recordingsResponse = await api.getRecordings(this.token, { page_size: 100 });
                this.availableRecordings = recordingsResponse.recordings || [];
            } catch (authError) {
                console.warn('Failed to load recordings from database (auth required):', authError.message);
                this.availableRecordings = [];
            }

            // If a current recording exists, automatically load its UTG and task info
            if (this.currentRecording && window.app && window.app.utgViewer) {
                console.log(`DataEditor: Auto-loading recording: ${this.currentRecording}`);
                if (typeof window.app.restoreWorkspaceVisualState === 'function') {
                    await window.app.restoreWorkspaceVisualState({
                        current_recording: this.currentRecording
                    });
                } else if (typeof window.app.utgViewer.restoreWorkspaceRecording === 'function') {
                    await window.app.utgViewer.restoreWorkspaceRecording(this.currentRecording);
                }
            } else if (!this.currentRecording) {
                console.log('DataEditor: No current recording selected, skipping UTG load');
                this.hideRecordingInfo();
                this.renderEmptyRecordingSelector();
                this.clearWorkspaceVisualState();
            }
        } catch (error) {
            console.error('Failed to load recordings:', error);
            this.resetWorkspaceState();
            this.clearWorkspaceVisualState();
            throw error;
        }
    }

    getCurrentRecording() {
        return this.currentRecording;
    }

    setLoading(isLoading) {
        this.isLoading = isLoading;
        const select = document.getElementById('data-editor-dataset-select');

        if (select) {
            if (isLoading) {
                select.disabled = true;
                select.style.opacity = '0.6';
            } else {
                select.disabled = false;
                select.style.opacity = '1';
            }
        }
    }

    refresh() {
        if (this.isVisible) {
            this.show(); // Reload the interface
        } else {
            this.loadRecordings(); // Just refresh the data
        }
    }

    async loadRecordingInfo(directoryName) {
        if (!directoryName) {
            this.hideRecordingInfo();
            return;
        }

        try {
            // Get UTG data
            const utgResponse = await api.getUTG();

            if (!utgResponse) {
                this.hideRecordingInfo();
                return;
            }

            const utg = utgResponse;

            let appInfo = {
                package: utg.app_package || '暂无',
                sha256: utg.app_sha256 || '暂无',
                mainActivity: utg.app_main_activity || '暂无',
                activities: utg.app_num_total_activities || 0
            };

            let deviceInfo = {
                serial: utg.device_serial || '暂无',
                model: utg.device_model_number || '暂无',
                sdkVersion: utg.device_sdk_version || '暂无'
            };

            let testResults = {
                testDate: utg.test_date || '暂无',
                timeSpent: utg.time_spent || 0,
                inputEvents: utg.num_input_events || 0,
                utgStates: utg.num_nodes || 0,
                utgEdges: utg.num_edges || 0
            };

            this.displayRecordingInfo({
                directoryName,
                appInfo,
                deviceInfo,
                testResults
            });

        } catch (error) {
            console.error('Failed to load recording info:', error);
            this.hideRecordingInfo();
        }
    }

    displayRecordingInfo(info) {
        const detailsDiv = document.getElementById('dataset-details');
        const panelDiv = document.getElementById('dataset-info-panel');

        if (!detailsDiv || !panelDiv) return;

        const { directoryName, appInfo, deviceInfo, testResults } = info;

        let overallInfo = "<table class=\"table\">\n";

        overallInfo += "<tr class=\"active\"><th colspan=\"2\"><h4>应用信息</h4></th></tr>\n";
        overallInfo += `<tr><th class="col-md-1">包名</th><td class="col-md-4">${appInfo.package}</td></tr>\n`;
        overallInfo += `<tr><th class="col-md-1">SHA-256</th><td class="col-md-4">${appInfo.sha256}</td></tr>\n`;
        overallInfo += `<tr><th class="col-md-1">主 Activity</th><td class="col-md-4">${appInfo.mainActivity}</td></tr>\n`;
        overallInfo += `<tr><th class="col-md-1">Activity 数量</th><td class="col-md-4">${appInfo.activities}</td></tr>\n`;

        overallInfo += "<tr class=\"active\"><th colspan=\"2\"><h4>设备信息</h4></th></tr>\n";
        overallInfo += `<tr><th class="col-md-1">设备序列号</th><td class="col-md-4">${deviceInfo.serial}</td></tr>\n`;
        overallInfo += `<tr><th class="col-md-1">型号</th><td class="col-md-4">${deviceInfo.model}</td></tr>\n`;
        overallInfo += `<tr><th class="col-md-1">SDK 版本</th><td class="col-md-4">${deviceInfo.sdkVersion}</td></tr>\n`;

        overallInfo += "<tr class=\"active\"><th colspan=\"2\"><h4>DroidBot 结果</h4></th></tr>\n";
        overallInfo += `<tr><th class="col-md-1">测试日期</th><td class="col-md-4">${testResults.testDate}</td></tr>\n`;
        overallInfo += `<tr><th class="col-md-1">耗时（秒）</th><td class="col-md-4">${testResults.timeSpent}</td></tr>\n`;
        overallInfo += `<tr><th class="col-md-1">输入事件数</th><td class="col-md-4">${testResults.inputEvents}</td></tr>\n`;
        overallInfo += `<tr><th class="col-md-1">UTG 状态数</th><td class="col-md-4">${testResults.utgStates}</td></tr>\n`;
        overallInfo += `<tr><th class="col-md-1">UTG 边数</th><td class="col-md-4">${testResults.utgEdges}</td></tr>\n`;

        overallInfo += "</table>";

        detailsDiv.innerHTML = overallInfo;
        panelDiv.style.display = 'block';
    }

    hideRecordingInfo() {
        const panelDiv = document.getElementById('dataset-info-panel');
        if (panelDiv) {
            panelDiv.style.display = 'none';
        }
    }

    renderEmptyRecordingSelector() {
        const select = document.getElementById('data-editor-dataset-select');
        if (!select) {
            return;
        }
        select.innerHTML = '<option value="">选择一条录制数据...</option>';
        select.value = '';
        select.disabled = false;
        select.style.opacity = '1';
    }

    clearWorkspaceVisualState() {
        if (window.app && window.app.utgViewer && typeof window.app.utgViewer.resetWorkspaceState === 'function') {
            window.app.utgViewer.resetWorkspaceState();
        }
    }

    showError(message) {
        if (this.container) {
            this.container.innerHTML = `<hr /><h2>错误</h2><p>${message}</p>`;
        }
    }
}
