// Global application state
window.app = {
    utgViewer: null,
    taskRecorder: null,
    dataEditor: null, // Now handles dataset management
    userManager: null,
    taskManager: null,
    batchManager: null,
    cloudDeviceManager: null,
    recordingExceptionManager: null,
    currentView: 'task-recorder',
    suspendedWorkspaceView: null,
    lastBootstrapState: null,
    workspaceActivityDirty: false,
    workspaceActivityTimer: null,
    workspaceListenersBound: false
};

window.app.applyBootstrapWorkspaceState = function(result) {
    window.app.lastBootstrapState = result || null;

    var currentRecording = result && result.current_recording ? result.current_recording : null;

    if (window.app.dataEditor) {
        window.app.dataEditor.currentRecording = currentRecording;
    }

    if (window.app.taskRecorder && typeof window.app.taskRecorder.restoreWorkspaceContext === 'function') {
        window.app.taskRecorder.restoreWorkspaceContext(result);
    }
};

window.app.restoreWorkspaceVisualState = async function(result) {
    var bootstrapState = typeof result === 'undefined' ? window.app.lastBootstrapState : result;
    var currentRecording = bootstrapState && bootstrapState.current_recording ? bootstrapState.current_recording : null;

    if (!window.app.utgViewer) {
        return;
    }

    if (currentRecording) {
        if (typeof window.app.utgViewer.restoreWorkspaceRecording === 'function') {
            await window.app.utgViewer.restoreWorkspaceRecording(currentRecording);
        }
        return;
    }

    if (typeof window.app.utgViewer.resetWorkspaceState === 'function') {
        window.app.utgViewer.resetWorkspaceState();
    }
};

window.app.restoreTaskRecorderWorkspaceView = async function(result) {
    var bootstrapState = typeof result === 'undefined' ? window.app.lastBootstrapState : result;
    var currentRecording = bootstrapState && bootstrapState.current_recording ? bootstrapState.current_recording : null;

    if (window.app.currentView !== 'task-recorder' || !currentRecording || !window.app.utgViewer) {
        return;
    }

    await window.app.restoreWorkspaceVisualState(bootstrapState);

    if (typeof window.app.utgViewer.fitForRestore !== 'function') {
        return;
    }

    for (var attempt = 0; attempt < 3; attempt += 1) {
        if (window.app.utgViewer.fitForRestore()) {
            return;
        }
        await new Promise(function(resolve) {
            setTimeout(resolve, 50);
        });
    }
};

async function bootstrapWorkspace(currentView = 'task-recorder') {
    const storedWorkspaceId = api.getWorkspaceId();
    const result = await api.bootstrapWorkspace(storedWorkspaceId, currentView);
    if (result && result.workspace_id) {
        api.setWorkspaceId(result.workspace_id);
    }
    return result;
}

function markWorkspaceActivity() {
    window.app.workspaceActivityDirty = true;
}

function setupWorkspaceActivityTracking() {
    if (window.app.workspaceListenersBound) {
        return;
    }

    window.app.workspaceListenersBound = true;
    ['mousemove', 'keydown', 'click', 'touchstart'].forEach(function(eventName) {
        document.addEventListener(eventName, markWorkspaceActivity, true);
    });
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            markWorkspaceActivity();
        }
    });

    window.app.workspaceActivityTimer = setInterval(async function() {
        if (!window.app.workspaceActivityDirty) {
            return;
        }
        if (document.visibilityState !== 'visible') {
            return;
        }
        if (!api.getWorkspaceId()) {
            return;
        }
        if (!localStorage.getItem('auth_token')) {
            return;
        }

        try {
            await api.reportWorkspaceActivity(window.app.currentView);
            window.app.workspaceActivityDirty = false;
        } catch (error) {
            if (error && error.code !== 'WORKSPACE_EXPIRED') {
                console.warn('Workspace activity heartbeat failed', error);
            }
        }
    }, 30000);
}

function leaveTaskRecorderIfNeeded(targetViewName) {
    if (!window.app.taskRecorder || !window.app.taskRecorder.isVisible) {
        return true;
    }

    if (window.app.taskRecorder.isRecording) {
        var confirmed = window.confirm(
            '当前正在录制。切换到“' + targetViewName + '”将停止录制并断开设备连接，是否继续？'
        );
        if (!confirmed) {
            return false;
        }
    }

    window.app.taskRecorder.hide();
    return true;
}

window.app.resetWorkspaceScopedState = function(options) {
    var settings = options || {};
    var disconnectTaskRecorder = !!settings.disconnectTaskRecorder;

    if (window.app.taskRecorder) {
        if (disconnectTaskRecorder && window.app.taskRecorder.isConnected) {
            window.app.taskRecorder.disconnect();
        }
        if (typeof window.app.taskRecorder.resetWorkspaceState === 'function') {
            window.app.taskRecorder.resetWorkspaceState();
        }
    }

    if (window.app.dataEditor && typeof window.app.dataEditor.resetWorkspaceState === 'function') {
        window.app.dataEditor.resetWorkspaceState();
    }

    if (window.app.utgViewer && typeof window.app.utgViewer.resetWorkspaceState === 'function') {
        window.app.utgViewer.resetWorkspaceState();
    }

    window.app.workspaceActivityDirty = false;
    window.app.lastBootstrapState = null;
};

window.app.handleAuthExpired = async function() {
    if (window.app.currentView && window.app.currentView !== 'user-manager') {
        window.app.suspendedWorkspaceView = window.app.currentView;
    }
    window.app.resetWorkspaceScopedState({ disconnectTaskRecorder: true });
    if (window.app.userManager) {
        window.app.userManager.token = null;
        window.app.userManager.currentUser = null;
        window.app.userManager.render();
    }
    showError('登录状态已过期，请重新登录。');
    if (window.app.userManager) {
        await showUserManager();
    }
};

window.app.handleWorkspaceExpired = async function(errorData) {
    window.app.resetWorkspaceScopedState({ disconnectTaskRecorder: true });
    try {
        var replacementWorkspace = await bootstrapWorkspace(window.app.currentView);
        window.app.applyBootstrapWorkspaceState(replacementWorkspace);
        await window.app.restoreWorkspaceVisualState(replacementWorkspace);
    } catch (error) {
        console.warn('Failed to bootstrap a replacement workspace', error);
    }
    showError((errorData && errorData.detail) || '当前工作区已过期，请重新选择录制数据。');
};

// Initialize the application
async function initApp() {
    try {
        console.log('Initializing GUIAgent Data Labeling Platform...');

        let bootstrapResult = null;
        const initialToken = localStorage.getItem('auth_token');
        if (initialToken) {
            try {
                bootstrapResult = await bootstrapWorkspace(window.app.currentView);
            } catch (error) {
                if (error && error.code === 'AUTH_EXPIRED') {
                    console.warn('Startup bootstrap suspended until re-login', error);
                } else {
                    throw error;
                }
            }
        }

        // Initialize components
        window.app.utgViewer = new UTGViewer('utg_main', null);
        window.app.taskRecorder = new TaskRecorder('control_panel');
        window.app.dataEditor = new DataEditor('control_panel');
        window.app.userManager = new UserManager('user-management-container');
        window.app.taskManager = new TaskManager('task-management-container');
        window.app.batchManager = new BatchManager('batch-manager-container');
        window.app.cloudDeviceManager = new CloudDeviceManager('cloud-device-container');
        window.app.recordingExceptionManager = new RecordingExceptionManager('recording-exception-container');

        // Make components globally accessible for backward compatibility
        window.utgViewer = window.app.utgViewer;
        window.dataEditor = window.app.dataEditor;
        // For backward compatibility, point datasetSelector to dataEditor
        window.datasetSelector = window.app.dataEditor;

        window.app.applyBootstrapWorkspaceState(bootstrapResult);

        // Load initial data
        // DataEditor will automatically call utgViewer.switchToRecording() if currentRecording exists
        await window.app.dataEditor.loadRecordings();

        // Set up navigation
        setupNavigation();
        setupWorkspaceActivityTracking();
        markWorkspaceActivity();

        // Check if user is logged in
        const activeToken = localStorage.getItem('auth_token');
        if (!activeToken) {
            // If not logged in, show User Management login page
            await showUserManager();
        } else {
            // If logged in, show Task Record by default
            await showTaskRecorder();
            await window.app.restoreTaskRecorderWorkspaceView(bootstrapResult);
        }
        
        console.log('GUIAgent Data Labeling Platform initialized successfully');

    } catch (error) {
        console.error('Failed to initialize application:', error);
        showError('Failed to initialize application. Please refresh the page.');
    }
}

// Navigation setup
function setupNavigation() {
    // Add click handlers for navigation items
    const navItems = document.querySelectorAll('.navbar-nav a[onclick]');
    navItems.forEach(item => {
        const onclickAttr = item.getAttribute('onclick');
        if (onclickAttr) {
            item.addEventListener('click', function(e) {
                e.preventDefault();
                eval(onclickAttr);
            });
        }
    });
}

// Navigation functions

async function showTaskRecorder() {
    window.app.currentView = 'task-recorder';
    markWorkspaceActivity();

    // Show main content row, hide user manager and task manager
    document.getElementById('main-content-row').style.display = 'flex';
    if (window.app.userManager && window.app.userManager.isVisible) {
        window.app.userManager.hide();
    }
    if (window.app.taskManager && window.app.taskManager.isVisible) {
        window.app.taskManager.hide();
    }

    // Hide other panels if visible
    if (window.app.dataEditor && window.app.dataEditor.isVisible) {
        window.app.dataEditor.hide();
    }

    // Hide batch managers if visible
    if (window.app.batchManager && window.app.batchManager.isVisible) {
        window.app.batchManager.hide();
    }

    if (window.app.recordingExceptionManager && window.app.recordingExceptionManager.isVisible) {
        window.app.recordingExceptionManager.hide();
    }

    // Show task record using consistent pattern
    await window.app.taskRecorder.show();
}

async function showDataEditor() {
    if (!leaveTaskRecorderIfNeeded('数据编辑')) {
        return;
    }
    window.app.currentView = 'data-editor';
    markWorkspaceActivity();

    // Show main content row, hide user manager and task manager
    document.getElementById('main-content-row').style.display = 'flex';
    if (window.app.userManager && window.app.userManager.isVisible) {
        window.app.userManager.hide();
    }
    if (window.app.taskManager && window.app.taskManager.isVisible) {
        window.app.taskManager.hide();
    }

    // Hide batch managers if visible
    if (window.app.batchManager && window.app.batchManager.isVisible) {
        window.app.batchManager.hide();
    }

    if (window.app.recordingExceptionManager && window.app.recordingExceptionManager.isVisible) {
        window.app.recordingExceptionManager.hide();
    }

    // Show data editor
    await window.app.dataEditor.show();
}

async function showUserManager() {
    if (!leaveTaskRecorderIfNeeded('用户管理')) {
        return;
    }
    window.app.currentView = 'user-manager';
    markWorkspaceActivity();

    // Hide main content row
    document.getElementById('main-content-row').style.display = 'none';

    // Hide task manager if visible
    if (window.app.taskManager && window.app.taskManager.isVisible) {
        window.app.taskManager.hide();
    }

    // Hide cloud device manager if visible
    if (window.app.cloudDeviceManager && window.app.cloudDeviceManager.isVisible) {
        window.app.cloudDeviceManager.hide();
    }

    if (window.app.recordingExceptionManager && window.app.recordingExceptionManager.isVisible) {
        window.app.recordingExceptionManager.hide();
    }

    // Hide batch managers if visible
    if (window.app.batchManager && window.app.batchManager.isVisible) {
        window.app.batchManager.hide();
    }

    // Show user manager
    window.app.userManager.show();
}

async function showTaskManager() {
    if (!leaveTaskRecorderIfNeeded('任务管理')) {
        return;
    }
    window.app.currentView = 'task-manager';
    markWorkspaceActivity();

    // Hide main content row
    document.getElementById('main-content-row').style.display = 'none';

    // Hide user manager if visible
    if (window.app.userManager && window.app.userManager.isVisible) {
        window.app.userManager.hide();
    }

    // Hide cloud device manager if visible
    if (window.app.cloudDeviceManager && window.app.cloudDeviceManager.isVisible) {
        window.app.cloudDeviceManager.hide();
    }

    if (window.app.recordingExceptionManager && window.app.recordingExceptionManager.isVisible) {
        window.app.recordingExceptionManager.hide();
    }

    // Hide batch managers if visible
    if (window.app.batchManager && window.app.batchManager.isVisible) {
        window.app.batchManager.hide();
    }

    // 通过导航进入时，始终重置批次模式，回到批次列表
    if (window.app.taskManager && window.app.taskManager.batchMode) {
        window.app.taskManager.batchMode = false;
        window.app.taskManager.currentBatchId = null;
        window.app.taskManager.currentBatch = null;
        var batchInfoSection = document.getElementById('batch-info-section');
        var batchBreadcrumb = document.getElementById('batch-breadcrumb');
        var taskManagerTitle = document.getElementById('task-manager-title');
        var batchMoveBtn = document.getElementById('batch-move-btn');
        if (batchInfoSection) batchInfoSection.style.display = 'none';
        if (batchBreadcrumb) batchBreadcrumb.style.display = 'none';
        if (taskManagerTitle) taskManagerTitle.style.display = 'block';
        if (batchMoveBtn) batchMoveBtn.style.display = 'none';
    }

    // Show task manager
    window.app.taskManager.show();
}

async function showCloudDeviceManager() {
    if (!leaveTaskRecorderIfNeeded('设备管理')) {
        return;
    }
    window.app.currentView = 'cloud-device-manager';
    markWorkspaceActivity();

    // Hide main content row
    document.getElementById('main-content-row').style.display = 'none';

    // Hide user manager if visible
    if (window.app.userManager && window.app.userManager.isVisible) {
        window.app.userManager.hide();
    }

    // Hide task manager if visible
    if (window.app.taskManager && window.app.taskManager.isVisible) {
        window.app.taskManager.hide();
    }

    if (window.app.recordingExceptionManager && window.app.recordingExceptionManager.isVisible) {
        window.app.recordingExceptionManager.hide();
    }

    // Hide batch managers if visible
    if (window.app.batchManager && window.app.batchManager.isVisible) {
        window.app.batchManager.hide();
    }

    // Show cloud device manager
    window.app.cloudDeviceManager.show();
}

async function showRecordingExceptionManager() {
    if (!leaveTaskRecorderIfNeeded('录制异常')) {
        return;
    }
    window.app.currentView = 'recording-exception-manager';
    markWorkspaceActivity();

    document.getElementById('main-content-row').style.display = 'none';

    if (window.app.userManager && window.app.userManager.isVisible) {
        window.app.userManager.hide();
    }
    if (window.app.taskManager && window.app.taskManager.isVisible) {
        window.app.taskManager.hide();
    }
    if (window.app.cloudDeviceManager && window.app.cloudDeviceManager.isVisible) {
        window.app.cloudDeviceManager.hide();
    }
    if (window.app.batchManager && window.app.batchManager.isVisible) {
        window.app.batchManager.hide();
    }

    window.app.recordingExceptionManager.show();
}


// Utility functions
function showSuccess(message) {
    showNotification(message, 'success');
}

function showError(message) {
    showNotification(message, 'error');
}

function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} app-notification`;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 1050;
        max-width: 400px;
        opacity: 0;
        transition: opacity 0.3s ease;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    `;
    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'close';

    const closeIcon = document.createElement('span');
    closeIcon.textContent = '\u00d7';
    closeButton.appendChild(closeIcon);

    closeButton.addEventListener('click', () => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    });

    const messageNode = document.createElement('span');
    messageNode.className = 'app-notification-message';
    messageNode.textContent = message;

    notification.appendChild(closeButton);
    notification.appendChild(messageNode);

    document.body.appendChild(notification);

    // Fade in
    setTimeout(() => {
        notification.style.opacity = '1';
    }, 10);

    // Auto remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.style.opacity = '0';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }
    }, 5000);
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on the main page (has the required elements)
    if (document.getElementById('utg_div') && document.getElementById('control_panel')) {
        initApp();
    }
});


// Make functions globally available for backward compatibility - moved to bottom of file

// Export functions to global scope for HTML onclick handlers
function exportGlobalFunctions() {
    'use strict';

    // Make functions globally available for backward compatibility
    window.showTaskRecorder = showTaskRecorder;
    window.showDataEditor = showDataEditor;
    window.showUserManager = showUserManager;
    window.showTaskManager = showTaskManager;
    window.showCloudDeviceManager = showCloudDeviceManager;
    window.showRecordingExceptionManager = showRecordingExceptionManager;
    window.showSuccess = showSuccess;
    window.showError = showError;

    console.log('Global functions exported successfully');
}

// Export functions immediately and also after DOM is ready
exportGlobalFunctions();

// Also export when DOM is ready as a backup
document.addEventListener('DOMContentLoaded', function() {
    exportGlobalFunctions();
});
