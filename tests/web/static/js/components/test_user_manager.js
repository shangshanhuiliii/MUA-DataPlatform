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

function loadUserManagerContext() {
  const filePath = path.resolve(__dirname, '../../../../../web/static/js/components/user-manager.js');
  const source = fs.readFileSync(filePath, 'utf8') + '\nthis.ExportedUserManager = UserManager;';
  const localStorage = createStorage({ auth_token: 'token-a' });
  const context = {
    console,
    localStorage,
    document: {
      getElementById() {
        return {
          addEventListener() {},
          style: {},
          innerHTML: '',
          textContent: '',
          disabled: false,
          value: '',
          checked: false,
        };
      },
    },
    window: {
      app: {
        resetArgs: null,
        appliedBootstrapState: null,
        restoredVisualState: null,
        restoredTaskRecorderState: null,
        currentView: 'user-manager',
        suspendedWorkspaceView: null,
        resetWorkspaceScopedState(options) {
          this.resetArgs = options;
        },
        applyBootstrapWorkspaceState(state) {
          this.appliedBootstrapState = state;
        },
        async restoreWorkspaceVisualState(state) {
          this.restoredVisualState = state;
        },
        async restoreTaskRecorderWorkspaceView(state) {
          this.restoredTaskRecorderState = state;
        },
      },
    },
    api: {
      logoutCalls: [],
      bootstrapCalls: [],
      workspaceId: 'workspace-a',
      async logout(token) {
        this.logoutCalls.push(token);
      },
      async login() {
        return { access_token: 'token-b' };
      },
      async bootstrapWorkspace(workspaceId, currentView) {
        this.bootstrapCalls.push({ workspaceId, currentView });
        this.workspaceId = workspaceId || this.workspaceId;
        return {
          workspace_id: workspaceId || 'workspace-a',
          current_view: currentView,
          current_recording: 'record/task_a',
        };
      },
      getWorkspaceId() {
        return this.workspaceId;
      },
      setWorkspaceId(value) {
        this.workspaceId = value;
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  return context;
}

test('logout clears workspace-scoped state before returning to login view', async () => {
  const context = loadUserManagerContext();
  let showUserManagerCalls = 0;
  context.window.showUserManager = async function() {
    showUserManagerCalls += 1;
  };

  const UserManager = context.ExportedUserManager;
  const manager = Object.create(UserManager.prototype);
  let renderCalls = 0;
  manager.token = 'token-a';
  manager.currentUser = { username: 'alice' };
  manager.render = function() {
    renderCalls += 1;
  };

  await manager.logout();

  assert.deepEqual(context.api.logoutCalls, ['token-a']);
  assert.equal(context.window.app.resetArgs.disconnectTaskRecorder, true);
  assert.equal(manager.token, null);
  assert.equal(manager.currentUser, null);
  assert.equal(context.localStorage.getItem('auth_token'), null);
  assert.equal(context.api.workspaceId, null);
  assert.equal(renderCalls, 1);
  assert.equal(showUserManagerCalls, 1);
});

test('login reuses suspended workspace id before falling back to navigation target', async () => {
  const context = loadUserManagerContext();
  let showDataEditorCalls = 0;
  context.window.showDataEditor = async function() {
    showDataEditorCalls += 1;
  };

  const loginUsername = { value: 'alice' };
  const loginPassword = { value: 'secret' };
  context.document.getElementById = function(id) {
    if (id === 'login-username') return loginUsername;
    if (id === 'login-password') return loginPassword;
    return {
      addEventListener() {},
      style: {},
      innerHTML: '',
      textContent: '',
      disabled: false,
      value: '',
      checked: false,
    };
  };

  context.window.app.currentView = 'user-manager';
  context.window.app.suspendedWorkspaceView = 'data-editor';
  context.api.workspaceId = 'workspace-suspended';

  const UserManager = context.ExportedUserManager;
  const manager = Object.create(UserManager.prototype);
  manager.loadCurrentUser = async function() {};
  manager.render = function() {};
  manager.loadUsers = function() {};

  await manager.login();

  assert.equal(context.localStorage.getItem('auth_token'), 'token-b');
  assert.equal(context.api.bootstrapCalls.length, 1);
  assert.equal(context.api.bootstrapCalls[0].workspaceId, 'workspace-suspended');
  assert.equal(context.api.bootstrapCalls[0].currentView, 'data-editor');
  assert.deepEqual(context.window.app.appliedBootstrapState, {
    workspace_id: 'workspace-suspended',
    current_view: 'data-editor',
    current_recording: 'record/task_a',
  });
  assert.equal(context.window.app.restoredVisualState, null);
  assert.equal(context.window.app.restoredTaskRecorderState, null);
  assert.equal(showDataEditorCalls, 1);
  assert.equal(context.window.app.suspendedWorkspaceView, null);
});

test('login restores task recorder visuals only after navigating back to task-recorder', async () => {
  const context = loadUserManagerContext();
  const sequence = [];
  context.window.showTaskRecorder = async function() {
    sequence.push('showTaskRecorder');
  };
  context.window.app.restoreTaskRecorderWorkspaceView = async function(state) {
    sequence.push('restoreTaskRecorderWorkspaceView');
    this.restoredTaskRecorderState = state;
  };

  const loginUsername = { value: 'alice' };
  const loginPassword = { value: 'secret' };
  context.document.getElementById = function(id) {
    if (id === 'login-username') return loginUsername;
    if (id === 'login-password') return loginPassword;
    return {
      addEventListener() {},
      style: {},
      innerHTML: '',
      textContent: '',
      disabled: false,
      value: '',
      checked: false,
    };
  };

  context.window.app.currentView = 'user-manager';
  context.window.app.suspendedWorkspaceView = 'task-recorder';
  context.api.workspaceId = 'workspace-suspended';

  const UserManager = context.ExportedUserManager;
  const manager = Object.create(UserManager.prototype);
  manager.loadCurrentUser = async function() {};
  manager.render = function() {};
  manager.loadUsers = function() {};

  await manager.login();

  assert.deepEqual(sequence, ['showTaskRecorder', 'restoreTaskRecorderWorkspaceView']);
  assert.deepEqual(context.window.app.restoredTaskRecorderState, {
    workspace_id: 'workspace-suspended',
    current_view: 'task-recorder',
    current_recording: 'record/task_a',
  });
});
