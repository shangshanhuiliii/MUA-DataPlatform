const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadRecordingExceptionManager() {
  const filePath = path.resolve(__dirname, '../../../../../web/static/js/components/recording-exception-manager.js');
  const source = fs.readFileSync(filePath, 'utf8') + '\nthis.ExportedRecordingExceptionManager = RecordingExceptionManager;';
  const context = {
    console,
    window: {},
    document: {},
    alert() {},
    $() {
      return { modal() {} };
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return context.ExportedRecordingExceptionManager;
}

test('repair action html uses data attribute instead of inline onclick', () => {
  const RecordingExceptionManager = loadRecordingExceptionManager();
  const manager = Object.create(RecordingExceptionManager.prototype);
  manager.escapeAttribute = RecordingExceptionManager.prototype.escapeAttribute;
  manager.escapeHtml = RecordingExceptionManager.prototype.escapeHtml;

  const html = manager.buildRepairActionHtml({
    directory_name: "record/task_1490_it's_demo",
  });

  assert.match(html, /data-directory-name=/);
  assert.doesNotMatch(html, /onclick=/);
  assert.match(html, /recording-exception-repair-btn/);
});

test('repair button click forwards quoted directory name safely', () => {
  const RecordingExceptionManager = loadRecordingExceptionManager();
  const manager = Object.create(RecordingExceptionManager.prototype);
  let receivedDirectoryName = null;
  manager.openRepairModal = function(directoryName) {
    receivedDirectoryName = directoryName;
  };

  manager.handleRepairButtonClick({
    currentTarget: {
      getAttribute(name) {
        if (name === 'data-directory-name') {
          return "record/task_1490_it's_demo";
        }
        return null;
      },
    },
  });

  assert.equal(receivedDirectoryName, "record/task_1490_it's_demo");
});
