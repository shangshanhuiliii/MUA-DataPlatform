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

function loadTaskRecorderContext() {
  const filePath = path.resolve(__dirname, '../../../../../web/static/js/components/task-recorder.js');
  const source = fs.readFileSync(filePath, 'utf8') + '\nthis.ExportedTaskRecorder = TaskRecorder;';
  const context = {
    console,
    localStorage: createStorage({ auth_token: 'token-a' }),
    window: {},
    document: {
      getElementById() {
        return null;
      },
    },
    api: {},
    setTimeout,
    clearTimeout,
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  return context;
}

function createRecorder(TaskRecorder) {
  const recorder = Object.create(TaskRecorder.prototype);
  recorder.recordingMode = 'new_task';
  recorder.currentRecording = null;
  recorder.selectedRecording = null;
  recorder.selectedTask = { id: 123 };
  recorder.isRecording = false;
  recorder.taskSelectionDisplay = { value: '', title: '' };
  recorder.taskSelectionHint = { textContent: '' };
  recorder.openTaskSelectionBtn = { textContent: '' };
  recorder.taskSelect = { value: '' };
  recorder.clearTaskSelectionBtn = { disabled: false };
  recorder.newTaskModeRadio = { checked: true };
  recorder.appendDataModeRadio = { checked: false };
  return recorder;
}

test('restoreWorkspaceContext switches recorder into append_data mode for restored recording', () => {
  const context = loadTaskRecorderContext();
  const TaskRecorder = context.ExportedTaskRecorder;
  const recorder = createRecorder(TaskRecorder);

  recorder.restoreWorkspaceContext({
    workspace_id: 'workspace-1',
    current_recording: 'record/task_a',
  });

  assert.equal(recorder.token, 'token-a');
  assert.equal(recorder.recordingMode, 'append_data');
  assert.equal(recorder.currentRecording, 'record/task_a');
  assert.ok(recorder.selectedRecording);
  assert.equal(recorder.selectedRecording.directory_name, 'record/task_a');
  assert.equal(recorder.selectedTask, null);
  assert.equal(recorder.appendDataModeRadio.checked, true);
  assert.equal(recorder.newTaskModeRadio.checked, false);
  assert.equal(recorder.taskSelect.value, 'record/task_a');
  assert.equal(recorder.taskSelectionDisplay.value, 'record/task_a');
});

test('restoreWorkspaceContext clears stale recording state when bootstrap has no current recording', () => {
  const context = loadTaskRecorderContext();
  const TaskRecorder = context.ExportedTaskRecorder;
  const recorder = createRecorder(TaskRecorder);
  recorder.recordingMode = 'append_data';
  recorder.currentRecording = 'record/task_old';
  recorder.selectedRecording = { directory_name: 'record/task_old' };

  recorder.restoreWorkspaceContext({
    workspace_id: 'workspace-2',
    current_recording: null,
  });

  assert.equal(recorder.recordingMode, 'new_task');
  assert.equal(recorder.currentRecording, null);
  assert.equal(recorder.selectedRecording, null);
  assert.equal(recorder.appendDataModeRadio.checked, false);
  assert.equal(recorder.newTaskModeRadio.checked, true);
  assert.equal(recorder.taskSelect.value, '');
  assert.match(recorder.taskSelectionDisplay.value, /请选择待录制的任务/);
});

test('applyRecordingSelection in append mode shows structured lock conflict message', async () => {
  const context = loadTaskRecorderContext();
  const TaskRecorder = context.ExportedTaskRecorder;
  const recorder = createRecorder(TaskRecorder);
  const messages = [];

  recorder.recordingMode = 'append_data';
  recorder.currentRecording = 'record/task_old';
  recorder.selectedRecording = null;
  recorder.updateSelectionDisplay = function() {};
  recorder.setSelectionControlsDisabled = function() {};
  recorder.taskSelect = { value: '' };
  context.window.showError = function(message) {
    messages.push(message);
  };
  context.api.setCurrentRecording = async function() {
    const error = new Error('Recording is currently used by another workspace');
    error.code = 'RECORDING_LOCK_CONFLICT';
    throw error;
  };
  context.api.formatRecordingLockConflict = function(error) {
    assert.equal(error.code, 'RECORDING_LOCK_CONFLICT');
    return '当前数据正被 alice 在任务录制使用。终端：10.12.*.* / C9K1。浏览器：Chrome 136.0.0.0。系统：Windows 10。预计于 2026-04-07 15:30:20 释放。';
  };

  const result = await recorder.applyRecordingSelection('record/task_new', null);

  assert.equal(result, false);
  assert.deepEqual(messages, [
    '切换录制数据失败：当前数据正被 alice 在任务录制使用。终端：10.12.*.* / C9K1。浏览器：Chrome 136.0.0.0。系统：Windows 10。预计于 2026-04-07 15:30:20 释放。',
  ]);
  assert.equal(recorder.selectedRecording.directory_name, 'record/task_old');
});
