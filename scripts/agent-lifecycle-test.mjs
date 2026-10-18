import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const ts = require('typescript');
function load(filename, imports = {}, transform = text => text) {
  const source = transform(fs.readFileSync(path.join(root, filename), 'utf8'));
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}}).outputText;
  const context = {exports: {}, Intl, Error, require: name => Object.hasOwn(imports, name) ? imports[name] : require(name)};
  vm.runInNewContext(code, context, {timeout: 1000});
  return context.exports;
}
const english = {}, simplified = {};
for (const name of fs.readdirSync(path.join(root, 'frontend/src/i18n/catalogs'))) {
  if (name.endsWith('.en.ts')) english[name] = load(`frontend/src/i18n/catalogs/${name}`);
  if (name.endsWith('.zh-CN.json')) simplified[name] = {default: JSON.parse(fs.readFileSync(path.join(root, 'frontend/src/i18n/catalogs', name), 'utf8'))};
}
const i18n = load('frontend/src/i18n/index.ts', {}, text => text
  .replace(/import\.meta\.glob<\{ default: Catalog \}>\('\.\/catalogs\/\*\.en\.ts', \{ eager: true \}\)/, JSON.stringify(english))
  .replace(/import\.meta\.glob<\{ default: Catalog \}>\('\.\/catalogs\/\*\.zh-CN\.json', \{ eager: true \}\)/, JSON.stringify(simplified)));

function setup({canManage = true, status = 'available', component = 'lifecycle'} = {}) {
  const state = [], requests = [], retired = [], messages = [];
  let cursor = 0, serial = 0;
  let respond = async (_kind, agent, status) => ({...agent, status: status ?? 'archived'});
  const agent = {id: 'agent-1', name: 'Synthetic Agent', status};
  const hooks = {
    useState(initial) { const index = cursor++; if (!(index in state)) state[index] = initial; return [state[index], value => {state[index] = typeof value === 'function' ? value(state[index]) : value;}]; },
    useRef(initial) { const index = cursor++; if (!(index in state)) state[index] = {current: initial}; return state[index]; },
  };
  const exported = load(component === 'lifecycle' ? 'frontend/src/agents/AgentLifecycleActions.tsx' : 'frontend/src/agents/AgentAvailabilityAction.tsx', {
    react: hooks,
    '@ant-design/icons': {LockOutlined: 'LockOutlined', UnlockOutlined: 'UnlockOutlined'},
    antd: {Button: 'Button', Modal: 'Modal', Space: 'Space', message: {useMessage: () => [{success: text => messages.push(['success', text]), error: text => messages.push(['error', text])}, null]}},
    '../i18n': {useI18n: () => ({t: i18n.t})},
    '../api': {createIdempotencyKey: () => `operation-${++serial}`, api: {
      archiveAgent: async (id, key) => {requests.push(['archive', id, key]); return respond('archive', agent);},
      deleteAgent: async (id, key) => {requests.push(['delete', id, key]); return respond('delete', agent);},
      setAgentAvailability: async (id, status, key) => {requests.push(['status', id, key, status]); return respond('status', agent, status);},
    }},
  });
  function render() {
    cursor = 0;
    if (component === 'availability') return exported.AgentAvailabilityAction({agent, canManage, onUpdated: value => {Object.assign(agent, value); retired.push({value});}});
    return exported.AgentLifecycleActions({agent, canManage, onRetired: (value, deleted) => retired.push({value, deleted})});
  }
  function nodes(type) {
    const result = [];
    function walk(node) {
      if (!node || typeof node !== 'object') return;
      if (Array.isArray(node)) {node.forEach(walk); return;}
      if (node.type === type) result.push(node.props);
      walk(node.props?.children);
    }
    walk(render());
    return result;
  }
  return {render, nodes, requests, retired, messages, respond: callback => {respond = callback;}};
}

const settle = () => new Promise(resolve => setImmediate(resolve));
let checks = 0;
for (const locale of ['zh-TW', 'zh-CN', 'en']) {
  i18n.setLocale(locale);
  const control = setup();
  assert.equal(control.nodes('Button')[0].children, i18n.t('封存 Agent'));
  control.nodes('Button')[0].onClick();
  assert.equal(control.requests.length, 0, 'opening confirmation must not mutate');
  control.nodes('Modal')[0].onCancel();
  assert.equal(control.nodes('Modal')[0].open, false);
  assert.equal(control.requests.length, 0, 'cancel must not mutate');
  checks++;

  let resolveRequest;
  control.respond(() => new Promise(resolve => {resolveRequest = resolve;}));
  control.nodes('Button')[0].onClick();
  const modal = control.nodes('Modal')[0];
  modal.onOk();
  modal.onOk();
  modal.onCancel();
  assert.equal(control.requests.length, 1, 'duplicate confirm must be fenced');
  assert.equal(control.nodes('Modal')[0].confirmLoading, true);
  assert.equal(control.nodes('Modal')[0].open, true, 'pending request must not be dismissed');
  resolveRequest({id: 'agent-1', name: 'Synthetic Agent', status: 'archived'});
  await settle();
  assert.equal(control.retired[0].deleted, false);
  assert.equal(control.retired[0].value.status, 'archived');
  assert.equal(control.nodes('Modal')[0].open, false);
  checks++;

  const deletion = setup();
  deletion.respond(async () => {throw new Error('Network result unknown');});
  deletion.nodes('Button')[1].onClick();
  assert.equal(deletion.nodes('Modal')[0].okButtonProps.danger, true);
  deletion.nodes('Modal')[0].onOk();
  await settle();
  assert.equal(deletion.retired.length, 0, 'failed operation must not remove a directory row');
  assert.equal(deletion.nodes('Modal')[0].open, true);
  assert.equal(deletion.messages[0][0], 'error');
  deletion.respond(async () => ({id: 'agent-1', deleted: true}));
  deletion.nodes('Modal')[0].onOk();
  await settle();
  assert.equal(deletion.requests[0][2], deletion.requests[1][2], 'uncertain retry must reuse its idempotency key');
  assert.equal(deletion.retired[0].deleted, true);
  assert.equal(deletion.nodes('Modal')[0].open, false);
  checks++;

  assert.equal(setup({canManage: false}).render(), null);
  assert.equal(setup({status: 'archived'}).nodes('Button')[0].disabled, true);
  checks++;

  const availability = setup({status: 'disabled', component: 'availability'});
  assert.equal(availability.nodes('Button')[0].children, i18n.t('重新啟用'));
  assert.equal(availability.nodes('Button')[0].disabled, false, 'disabled Agents must offer re-enable');
  availability.nodes('Button')[0].onClick();
  await settle();
  assert.equal(availability.requests[0][3], 'available');
  assert.equal(availability.retired[0].value.status, 'available');
  assert.equal(availability.nodes('Button')[0].children, i18n.t('停用'));
  availability.nodes('Button')[0].onClick();
  await settle();
  assert.equal(availability.requests[1][3], 'disabled');
  assert.notEqual(availability.requests[0][2], availability.requests[1][2], 'opposite transitions need different keys');
  assert.equal(availability.nodes('Button')[0].children, i18n.t('重新啟用'));
  checks++;

  const retry = setup({status: 'disabled', component: 'availability'});
  let rejectUpdate;
  retry.respond(() => new Promise((_resolve, reject) => {rejectUpdate = reject;}));
  retry.nodes('Button')[0].onClick();
  retry.nodes('Button')[0].onClick();
  assert.equal(retry.requests.length, 1);
  assert.equal(retry.nodes('Button')[0].loading, true);
  rejectUpdate(Error('Network result unknown'));
  await settle();
  assert.equal(retry.retired.length, 0, 'failed re-enable must not mark an Agent available');
  assert.equal(retry.nodes('Button')[0].children, i18n.t('重新啟用'));
  assert.equal(retry.nodes('Button')[0].disabled, false);
  retry.respond(async (_kind, agent, status) => ({...agent, status}));
  retry.nodes('Button')[0].onClick();
  await settle();
  assert.equal(retry.requests[0][2], retry.requests[1][2], 'status retry must reuse its key');
  assert.equal(retry.retired[0].value.status, 'available');
  checks++;

  for (const config of [{canManage: false, status: 'disabled'}, {status: 'archived'}]) {
    const guarded = setup({...config, component: 'availability'});
    assert.equal(guarded.nodes('Button')[0].disabled, true);
    guarded.nodes('Button')[0].onClick();
    await settle();
    assert.equal(guarded.requests.length, 0);
  }
  checks++;
}
console.log(`AGENT_LIFECYCLE_OK: ${checks} retirement, re-enable, permission, concurrent-click and retry scenarios across 3 locales`);
