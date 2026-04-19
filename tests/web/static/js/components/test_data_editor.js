const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function createElement() {
  return {
    innerHTML: '',
    style: {},
    value: '',
    disabled: false,
  };
}

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

function loadDataEditorContext({ authToken = null } = {}) {
  const filePath = path.resolve(__dirname, '../../../../../web/static/js/components/data-editor.js');
  const source = fs.readFileSync(filePath, 'utf8') + '\nthis.ExportedDataEditor = DataEditor;';
  const elements = new Map([
    ['data-editor-dataset-select', createElement()],
    ['dataset-info-panel', createElement()],
    ['dataset-details', createElement()],
  ]);
  const context = {
    console,
    localStorage: createStorage(authToken ? { auth_token: authToken } : {}),
    document: {
      getElementById(id) {
        return elements.get(id) || null;
      },
    },
    window: {
      app: {
        utgViewer: {
          resetWorkspaceStateCalls: 0,
          resetWorkspaceState() {
            this.resetWorkspaceStateCalls += 1;
          },
        },
        restoreWorkspaceVisualStateCalls: [],
        async restoreWorkspaceVisualState(state) {
          this.restoreWorkspaceVisualStateCalls.push(state);
        },
      },
    },
    setTimeout(fn) {
      fn();
      return 1;
    },
    clearTimeout() {},
    api: {
      async getCurrentRecording() {
        return { current: null };
      },
      async getRecordings() {
        return { recordings: [] };
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  return { context, elements };
}

test('loadRecordings clears stale workspace visuals when no current recording exists', async () => {
  const { context, elements } = loadDataEditorContext({ authToken: 'token-a' });
  const DataEditor = context.ExportedDataEditor;
  const editor = new DataEditor('missing-container');
  editor.currentRecording = 'record/task_a';
  editor.availableRecordings = [{ directory_name: 'record/task_a' }];

  await editor.loadRecordings();

  assert.equal(editor.currentRecording, null);
  assert.equal(editor.availableRecordings.length, 0);
  assert.equal(elements.get('dataset-info-panel').style.display, 'none');
  assert.match(elements.get('data-editor-dataset-select').innerHTML, /选择一条录制数据/);
  assert.equal(context.window.app.utgViewer.resetWorkspaceStateCalls, 1);
});

test('loadRecordings restores workspace visuals without rewriting current recording', async () => {
  const { context } = loadDataEditorContext({ authToken: 'token-a' });
  const DataEditor = context.ExportedDataEditor;
  const editor = new DataEditor('missing-container');
  let setCurrentRecordingCalls = 0;

  context.api.getCurrentRecording = async function() {
    return { current: 'record/task_a' };
  };
  context.api.getRecordings = async function() {
    return { recordings: [{ directory_name: 'record/task_a' }] };
  };
  context.api.setCurrentRecording = async function() {
    setCurrentRecordingCalls += 1;
  };

  await editor.loadRecordings();

  assert.equal(editor.currentRecording, 'record/task_a');
  assert.equal(setCurrentRecordingCalls, 0);
  assert.equal(context.window.app.restoreWorkspaceVisualStateCalls.length, 1);
  assert.equal(
    context.window.app.restoreWorkspaceVisualStateCalls[0].current_recording,
    'record/task_a'
  );
});

test('switchRecording shows structured lock conflict message when available', async () => {
  const { context, elements } = loadDataEditorContext({ authToken: 'token-a' });
  const DataEditor = context.ExportedDataEditor;
  const editor = new DataEditor('missing-container');
  const messages = [];

  editor.currentRecording = 'record/task_old';
  elements.get('data-editor-dataset-select').value = 'record/task_new';
  context.window.app.utgViewer.switchToRecording = async function() {
    const error = new Error('Recording is currently used by another workspace');
    error.code = 'RECORDING_LOCK_CONFLICT';
    throw error;
  };
  context.api.formatRecordingLockConflict = function(error) {
    assert.equal(error.code, 'RECORDING_LOCK_CONFLICT');
    return '当前数据正被 alice 在数据编辑使用。终端：10.23.*.* / A7F2。浏览器：Edge 136.0.0.0。系统：Windows 10。预计于 2026-04-07 15:30:20 释放。';
  };
  context.window.showError = function(message) {
    messages.push(message);
  };

  await editor.switchRecording();

  assert.deepEqual(messages, [
    '切换录制数据失败：当前数据正被 alice 在数据编辑使用。终端：10.23.*.* / A7F2。浏览器：Edge 136.0.0.0。系统：Windows 10。预计于 2026-04-07 15:30:20 释放。',
  ]);
  assert.equal(elements.get('data-editor-dataset-select').value, 'record/task_old');
});
