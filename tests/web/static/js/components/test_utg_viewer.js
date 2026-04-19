const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadUTGViewerContext() {
  const filePath = path.resolve(__dirname, '../../../../../web/static/js/components/utg-viewer.js');
  const source = fs.readFileSync(filePath, 'utf8') + '\nthis.ExportedUTGViewer = UTGViewer;';
  const context = {
    console,
    navigator: { userAgent: 'node-test' },
    document: {
      getElementById() {
        return null;
      },
      createElement() {
        return {
          style: {},
          innerHTML: '',
          appendChild() {},
          querySelector() {
            return {
              addEventListener() {},
              classList: {
                contains() { return false; },
                add() {},
                remove() {},
              },
              className: '',
              textContent: '',
            };
          },
          remove() {},
        };
      },
      body: {
        appendChild() {},
      },
    },
    getComputedStyle() {
      return { position: 'relative' };
    },
    setTimeout,
    clearTimeout,
    CodeMirror() {
      return {
        setSize() {},
        setValue() {},
        refresh() {},
        setOption() {},
        focus() {},
      };
    },
    DeletedNodesDialog: function() {},
    api: {
      async setCurrentRecording() {
        throw new Error('setCurrentRecording should not be called');
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  return context;
}

test('restoreWorkspaceRecording loads task info and UTG without rewriting current recording', async () => {
  const context = loadUTGViewerContext();
  const UTGViewer = context.ExportedUTGViewer;
  const viewer = Object.create(UTGViewer.prototype);
  let loadTaskInfoCalls = 0;
  let loadUTGCalls = 0;

  viewer.activeRecordingName = null;
  viewer.utg = null;
  viewer.taskInfoLoaded = false;
  viewer.taskInfoDatasetName = { textContent: '' };
  viewer.isWorkspaceScopedError = () => false;
  viewer.resetWorkspaceState = function() {
    throw new Error('resetWorkspaceState should not be called');
  };
  viewer.loadTaskInfo = async function() {
    loadTaskInfoCalls += 1;
    this.taskInfoLoaded = true;
  };
  viewer.loadUTG = async function() {
    loadUTGCalls += 1;
    this.utg = { nodes: [] };
  };

  await viewer.restoreWorkspaceRecording('record/task_a');

  assert.equal(viewer.activeRecordingName, 'record/task_a');
  assert.equal(viewer.taskInfoDatasetName.textContent, 'record/task_a');
  assert.equal(loadTaskInfoCalls, 1);
  assert.equal(loadUTGCalls, 1);
});

test('fitForRestore redraws and fits the network when container size is available', () => {
  const context = loadUTGViewerContext();
  const UTGViewer = context.ExportedUTGViewer;
  const viewer = Object.create(UTGViewer.prototype);
  let redrawCalls = 0;
  let fitCalls = 0;

  viewer.container = {
    getBoundingClientRect() {
      return { width: 800, height: 600 };
    },
  };
  viewer.network = {
    redraw() {
      redrawCalls += 1;
    },
    fit(options) {
      fitCalls += 1;
      assert.equal(options.animation, false);
    },
  };

  const result = viewer.fitForRestore();

  assert.equal(result, true);
  assert.equal(redrawCalls, 1);
  assert.equal(fitCalls, 1);
});
