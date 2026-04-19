const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function createStorage() {
  const store = new Map();
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

function loadClientContext() {
  const filePath = path.resolve(__dirname, '../../../../../web/static/js/api/client.js');
  const source = fs.readFileSync(filePath, 'utf8') + '\nthis.ExportedDroidBotAPI = DroidBotAPI;';
  const context = {
    console,
    localStorage: createStorage(),
    sessionStorage: createStorage(),
    fetch() {
      throw new Error('fetch should not be called in unit tests');
    },
    window: {},
    atob(value) {
      return Buffer.from(value, 'base64').toString('binary');
    },
    Date,
    Buffer,
  };

  vm.createContext(context);
  vm.runInContext(source, context);
  return context;
}

test('formatRecordingLockConflict renders structured holder information', () => {
  const context = loadClientContext();
  const DroidBotAPI = context.ExportedDroidBotAPI;
  const api = new DroidBotAPI();
  const expiresAt = 1775547020;
  const message = api.formatRecordingLockConflict({
    code: 'RECORDING_LOCK_CONFLICT',
    message: 'Recording is currently used by another workspace',
    data: {
      holder_username: 'alice',
      holder_view: 'data-editor',
      holder_client_shortcode: 'A7F2',
      holder_ip_full: '10.23.45.67',
      holder_browser_name: 'Edge',
      holder_browser_version: '136.0.0.0',
      holder_os_name: 'Windows',
      holder_os_version: '10',
      expires_at: expiresAt,
    },
  });

  assert.equal(
    message,
    `当前数据正被 alice 在数据编辑使用。终端：10.23.45.67 / A7F2。浏览器：Edge 136.0.0.0。系统：Windows 10。预计于 ${api.formatRecordingLockTime(expiresAt)} 释放。`
  );
});

test('formatRecordingLockConflict includes raw user agent only when backend returns admin-visible data', () => {
  const context = loadClientContext();
  const DroidBotAPI = context.ExportedDroidBotAPI;
  const api = new DroidBotAPI();
  const expiresAt = 1775547020;
  const userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0';
  const message = api.formatRecordingLockConflict({
    code: 'RECORDING_LOCK_CONFLICT',
    message: 'Recording is currently used by another workspace',
    data: {
      holder_username: 'alice',
      holder_view: 'data-editor',
      holder_client_shortcode: 'A7F2',
      holder_ip_full: '10.23.45.67',
      holder_browser_name: 'Edge',
      holder_browser_version: '136.0.0.0',
      holder_os_name: 'Windows',
      holder_os_version: '10',
      holder_user_agent: userAgent,
      expires_at: expiresAt,
    },
  });

  assert.equal(
    message,
    `当前数据正被 alice 在数据编辑使用。终端：10.23.45.67 / A7F2。浏览器：Edge 136.0.0.0。系统：Windows 10。User-Agent：${userAgent}。预计于 ${api.formatRecordingLockTime(expiresAt)} 释放。`
  );
});

test('formatRecordingLockConflict explains why holder information is missing', () => {
  const context = loadClientContext();
  const DroidBotAPI = context.ExportedDroidBotAPI;
  const api = new DroidBotAPI();
  const message = api.formatRecordingLockConflict({
    code: 'RECORDING_LOCK_CONFLICT',
    message: 'Recording is currently used by another workspace',
    data: {
      holder_username: null,
      holder_view: null,
      holder_client_shortcode: null,
      holder_ip_masked: null,
      holder_username_reason: 'anonymous_workspace',
      holder_view_reason: 'view_not_reported',
      holder_client_shortcode_reason: 'client_shortcode_not_sent',
      holder_ip_reason: 'client_ip_unavailable',
      holder_user_agent_reason: 'user_agent_not_captured',
      diagnostic_reason_summary: 'legacy_client_or_incomplete_session_metadata',
      lock_diagnostic_level: 'suspicious',
    },
  });

  assert.equal(
    message,
    '当前数据处于占用状态，但占用者用户名、页面和终端信息均缺失。占用者用户名缺失：该工作区以匿名方式创建，没有绑定登录用户。占用页面缺失：当前会话未上报所在页面。终端短码缺失：前端未上传终端短码，可能为旧前端版本或本地存储异常。IP 信息缺失：服务端未获取到客户端地址。User-Agent 缺失：会话元数据采集链路未记录 User-Agent。原因：会话元数据未完整采集，可能为旧版本会话遗留。这条锁状态可疑，可能需要进一步排查是否为 bug。'
  );
});

test('formatRecordingLockConflict explains policy-hidden ip while keeping masked terminal info', () => {
  const context = loadClientContext();
  const DroidBotAPI = context.ExportedDroidBotAPI;
  const api = new DroidBotAPI();
  const expiresAt = 1775547020;
  const message = api.formatRecordingLockConflict({
    code: 'RECORDING_LOCK_CONFLICT',
    message: 'Recording is currently used by another workspace',
    data: {
      holder_username: 'alice',
      holder_view: 'data-editor',
      holder_client_shortcode: 'A7F2',
      holder_ip_masked: '10.23.*.*',
      holder_browser_name: 'Edge',
      holder_browser_version: '136.0.0.0',
      holder_os_name: 'Windows',
      holder_os_version: '10',
      holder_ip_reason: 'ip_hidden_by_policy',
      diagnostic_reason_summary: 'role_limited_visibility',
      lock_diagnostic_level: 'normal',
      expires_at: expiresAt,
    },
  });

  assert.equal(
    message,
    `当前数据正被 alice 在数据编辑使用。终端：10.23.*.* / A7F2。浏览器：Edge 136.0.0.0。系统：Windows 10。IP 完整信息不可见：当前角色无权查看完整 IP。原因：当前角色的可见范围受限。预计于 ${api.formatRecordingLockTime(expiresAt)} 释放。`
  );
});

test('formatRecordingLockConflict explains missing user agent while keeping browser information', () => {
  const context = loadClientContext();
  const DroidBotAPI = context.ExportedDroidBotAPI;
  const api = new DroidBotAPI();
  const expiresAt = 1775547020;
  const message = api.formatRecordingLockConflict({
    code: 'RECORDING_LOCK_CONFLICT',
    message: 'Recording is currently used by another workspace',
    data: {
      holder_username: 'alice',
      holder_view: 'data-editor',
      holder_client_shortcode: 'A7F2',
      holder_ip_masked: '10.23.*.*',
      holder_browser_name: 'Edge',
      holder_browser_version: '136.0.0.0',
      holder_os_name: 'Windows',
      holder_os_version: '10',
      holder_user_agent_reason: 'user_agent_unavailable',
      expires_at: expiresAt,
    },
  });

  assert.equal(
    message,
    `当前数据正被 alice 在数据编辑使用。终端：10.23.*.* / A7F2。浏览器：Edge 136.0.0.0。系统：Windows 10。User-Agent 缺失：服务端未收到 User-Agent。预计于 ${api.formatRecordingLockTime(expiresAt)} 释放。`
  );
});

test('prepareRequestOptions adds a stable client shortcode header', async () => {
  const context = loadClientContext();
  const DroidBotAPI = context.ExportedDroidBotAPI;
  const api = new DroidBotAPI();

  const firstOptions = await api.prepareRequestOptions({ method: 'GET' });
  const secondOptions = await api.prepareRequestOptions({ method: 'POST' });

  assert.match(firstOptions.headers['X-Client-Shortcode'], /^[A-Z0-9]{4}$/);
  assert.equal(secondOptions.headers['X-Client-Shortcode'], firstOptions.headers['X-Client-Shortcode']);
  assert.equal(
    context.localStorage.getItem('client_shortcode'),
    firstOptions.headers['X-Client-Shortcode']
  );
});
