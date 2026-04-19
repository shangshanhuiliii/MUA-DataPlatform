const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function createStorage(initialValues = {}) {
  const store = new Map(Object.entries(initialValues));
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
  };
}

function loadAppContext() {
  const filePath = path.resolve(__dirname, '../../../../web/static/js/app.js');
  const source = fs.readFileSync(filePath, 'utf8') + '\nthis.ExportedInitApp = initApp;';
  const listeners = {};
  const elements = new Map();
  const intervalCallbacks = [];
  const bodyChildren = [];

  function createDomElement(tagName = 'div') {
    const node = {
      tagName: String(tagName).toUpperCase(),
      className: '',
      style: {},
      innerHTML: '',
      parentNode: null,
      children: [],
      attributes: {},
      _textContent: '',
      addEventListener(event, handler) {
        this[`on${event}`] = handler;
      },
      appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        return child;
      },
      removeChild(child) {
        this.children = this.children.filter((item) => item !== child);
        child.parentNode = null;
        return child;
      },
      remove() {
        if (this.parentNode) {
          this.parentNode.removeChild(this);
        }
      },
      setAttribute(name, value) {
        this.attributes[name] = value;
      },
    };

    Object.defineProperty(node, 'textContent', {
      get() {
        if (this.children.length) {
          return this.children.map((child) => child.textContent || '').join('');
        }
        return this._textContent;
      },
      set(value) {
        this._textContent = String(value);
      },
    });

    return node;
  }

  function getElement(id) {
    if (!elements.has(id)) {
      const element = createDomElement('div');
      element.id = id;
      elements.set(id, element);
    }
    return elements.get(id);
  }

  const context = {
    console,
    localStorage: createStorage({ auth_token: 'expired-token' }),
    sessionStorage: createStorage({ workspace_id: 'workspace-suspended' }),
    setTimeout(fn) {
      return fn ? 1 : 1;
    },
    clearTimeout() {},
    setInterval(fn) {
      intervalCallbacks.push(fn);
      return 1;
    },
    clearInterval() {},
    window: {},
    document: {
      addEventListener(event, handler) {
        listeners[event] = handler;
      },
      getElementById(id) {
        return getElement(id);
      },
      querySelectorAll() {
        return [];
      },
      createElement(tagName) {
        return createDomElement(tagName);
      },
      body: {
        children: bodyChildren,
        appendChild(child) {
          child.parentNode = this;
          this.children.push(child);
          return child;
        },
        removeChild(child) {
          const index = this.children.indexOf(child);
          if (index >= 0) {
            this.children.splice(index, 1);
          }
          child.parentNode = null;
          return child;
        },
      },
      visibilityState: 'visible',
    },
  };

  context.window = context;
  context.window.window = context.window;
  context.window.location = { href: '/' };
  context.window.confirm = () => true;

  function StubUTGViewer() {}

  function StubTaskRecorder() {
    this.isVisible = false;
    this.isConnected = false;
    this.isRecording = false;
    this.showCalls = 0;
    this.restoreCalls = [];
  }
  StubTaskRecorder.prototype.show = async function() {
    this.isVisible = true;
    this.showCalls += 1;
  };
  StubTaskRecorder.prototype.hide = function() {
    this.isVisible = false;
  };
  StubTaskRecorder.prototype.restoreWorkspaceContext = function(state) {
    this.restoreCalls.push(state);
  };
  StubTaskRecorder.prototype.resetWorkspaceState = function() {};

  function StubDataEditor() {
    this.isVisible = false;
    this.loadRecordingsCalls = 0;
  }
  StubDataEditor.prototype.loadRecordings = async function() {
    this.loadRecordingsCalls += 1;
  };
  StubDataEditor.prototype.resetWorkspaceState = function() {};
  StubDataEditor.prototype.hide = function() {
    this.isVisible = false;
  };

  function StubUserManager() {
    this.isVisible = false;
    this.token = context.localStorage.getItem('auth_token');
    this.currentUser = null;
    this.showCalls = 0;
    this.renderCalls = 0;
  }
  StubUserManager.prototype.show = function() {
    this.isVisible = true;
    this.showCalls += 1;
  };
  StubUserManager.prototype.hide = function() {
    this.isVisible = false;
  };
  StubUserManager.prototype.render = function() {
    this.renderCalls += 1;
  };

  function createHiddenManager() {
    return function StubManager() {
      this.isVisible = false;
    };
  }

  const SimpleManager = createHiddenManager();
  SimpleManager.prototype.show = function() {
    this.isVisible = true;
  };
  SimpleManager.prototype.hide = function() {
    this.isVisible = false;
  };

  context.UTGViewer = StubUTGViewer;
  context.TaskRecorder = StubTaskRecorder;
  context.DataEditor = StubDataEditor;
  context.UserManager = StubUserManager;
  context.TaskManager = SimpleManager;
  context.BatchManager = SimpleManager;
  context.CloudDeviceManager = SimpleManager;
  context.RecordingExceptionManager = SimpleManager;

  context.api = {
    reportWorkspaceActivityCalls: [],
    getWorkspaceId() {
      return context.sessionStorage.getItem('workspace_id');
    },
    setWorkspaceId(workspaceId) {
      if (workspaceId) {
        context.sessionStorage.setItem('workspace_id', workspaceId);
      } else {
        context.sessionStorage.removeItem('workspace_id');
      }
    },
    async bootstrapWorkspace() {
      await context.window.app.handleAuthExpired();
      context.localStorage.removeItem('auth_token');
      const error = new Error('Authentication expired');
      error.code = 'AUTH_EXPIRED';
      throw error;
    },
    async reportWorkspaceActivity(currentView) {
      this.reportWorkspaceActivityCalls.push(currentView);
      return {
        workspace_id: context.sessionStorage.getItem('workspace_id'),
        current_view: currentView,
      };
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  return { context, listeners, elements, intervalCallbacks, bodyChildren };
}

test('initApp continues initialization and lands on login view after startup AUTH_EXPIRED', async () => {
  const { context } = loadAppContext();

  await context.ExportedInitApp();

  assert.equal(context.localStorage.getItem('auth_token'), null);
  assert.equal(context.sessionStorage.getItem('workspace_id'), 'workspace-suspended');
  assert.ok(context.window.app.userManager);
  assert.equal(context.window.app.userManager.showCalls, 1);
  assert.equal(context.window.app.currentView, 'user-manager');
  assert.equal(context.window.app.taskRecorder.showCalls, 0);
  assert.equal(context.window.app.dataEditor.loadRecordingsCalls, 1);
});

test('restoreWorkspaceVisualState delegates recording restore without rewriting workspace state', async () => {
  const { context } = loadAppContext();
  const restoreCalls = [];
  let resetCalls = 0;

  context.window.app.utgViewer = {
    async restoreWorkspaceRecording(directoryName) {
      restoreCalls.push(directoryName);
    },
    resetWorkspaceState() {
      resetCalls += 1;
    },
  };

  await context.window.app.restoreWorkspaceVisualState({
    current_recording: 'record/task_a',
  });

  assert.deepEqual(restoreCalls, ['record/task_a']);
  assert.equal(resetCalls, 0);
});

test('restoreTaskRecorderWorkspaceView restores recording and fits after task-recorder is visible', async () => {
  const { context } = loadAppContext();
  const calls = [];

  context.window.app.currentView = 'task-recorder';
  context.window.app.utgViewer = {
    async restoreWorkspaceRecording(directoryName) {
      calls.push(`restore:${directoryName}`);
    },
    fitForRestore() {
      calls.push('fit');
      return true;
    },
  };

  await context.window.app.restoreTaskRecorderWorkspaceView({
    current_recording: 'record/task_a',
  });

  assert.deepEqual(calls, ['restore:record/task_a', 'fit']);
});

test('workspace heartbeat is skipped when auth token is missing even if workspace id is retained', async () => {
  const { context, intervalCallbacks } = loadAppContext();

  await context.ExportedInitApp();

  assert.ok(intervalCallbacks.length > 0);
  context.window.app.workspaceActivityDirty = true;
  context.localStorage.removeItem('auth_token');

  await intervalCallbacks[0]();

  assert.equal(context.sessionStorage.getItem('workspace_id'), 'workspace-suspended');
  assert.deepEqual(context.api.reportWorkspaceActivityCalls, []);
  assert.equal(context.window.app.workspaceActivityDirty, true);
});

test('handleWorkspaceExpired disconnects task recorder before bootstrapping replacement workspace', async () => {
  const { context } = loadAppContext();
  const resetArgs = [];

  context.window.app.taskRecorder = {
    isConnected: true,
    disconnectCalls: 0,
    disconnect() {
      this.disconnectCalls += 1;
    },
    resetWorkspaceState() {},
  };
  context.window.app.dataEditor = { resetWorkspaceState() {} };
  context.window.app.utgViewer = { resetWorkspaceState() {} };
  context.api.bootstrapWorkspace = async function() {
    return {
      workspace_id: 'workspace-replacement',
      current_recording: null,
      current_view: 'task-recorder',
    };
  };

  const originalReset = context.window.app.resetWorkspaceScopedState;
  context.window.app.resetWorkspaceScopedState = function(options) {
    resetArgs.push(options || {});
    return originalReset(options);
  };

  await context.window.app.handleWorkspaceExpired({ detail: 'Workspace expired' });

  assert.equal(resetArgs.length > 0, true);
  assert.equal(resetArgs[0].disconnectTaskRecorder, true);
  assert.equal(context.window.app.taskRecorder.disconnectCalls, 1);
});

test('showError renders notification message as plain text instead of parsing HTML', () => {
  const { context, bodyChildren } = loadAppContext();
  const maliciousMessage = '<img src=x onerror=alert(1)> raw text';

  context.window.showError(maliciousMessage);

  assert.equal(bodyChildren.length, 1);
  const notification = bodyChildren[0];
  assert.equal(notification.innerHTML, '');
  assert.equal(notification.children.length, 2);
  assert.equal(notification.children[1].textContent, maliciousMessage);
  assert.equal(notification.textContent.includes(maliciousMessage), true);
  assert.equal(notification.children.some((child) => child.tagName === 'IMG'), false);
});
