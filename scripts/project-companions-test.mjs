import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const ts = require('typescript');
const t = (source, values = {}) => {
  assert.equal(typeof source, 'string');
  return source.replace(/\{\{(\w+)\}\}/g, (_, key) => values[key] ?? key);
};
const context = vm.createContext({ Headers, Response, AbortSignal, Intl, console });
const cache = new Map();
const overrides = new Map([['frontend/src/i18n/index.ts', { t, useI18n: () => ({ t }) }]]);
function evaluate(source, filename) {
  const code = ts.transpileModule(source.replaceAll('import.meta.env', '({ MODE: "suite" })'), {
    fileName: filename,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const module = { exports: {} };
  const localRequire = name => {
    if (!name.startsWith('.')) return require(name);
    const absolute = path.resolve(path.dirname(path.join(root, filename)), name);
    const candidate = [absolute + '.ts', absolute + '.tsx', path.join(absolute, 'index.ts')].find(fs.existsSync);
    assert.ok(candidate, `Cannot resolve ${name} from ${filename}`);
    return load(path.relative(root, candidate).replaceAll('\\', '/'));
  };
  vm.runInContext(`(function(require,module,exports){${code}\n})`, context, { filename, timeout: 1000 })(localRequire, module, module.exports);
  return module.exports;
}
function load(filename) {
  if (overrides.has(filename)) return overrides.get(filename);
  if (!cache.has(filename)) cache.set(filename, evaluate(fs.readFileSync(path.join(root, filename), 'utf8'), filename));
  return cache.get(filename);
}
const { createProjectCompanions, companionKey } = load('frontend/src/products/shared/projectCompanions.ts');
const { setAuthCsrfToken } = load('frontend/src/auth/client.ts');
const { createProductApi } = load('frontend/src/products/shared/productApi.ts');
const project = { id: 'work-123', key: 'ORD_AI', name: 'User project', description: 'User-authored description' };
const original = JSON.stringify(project);
let calls = [];
let respond;
context.fetch = async (url, options) => {
  const call = { url, options, body: JSON.parse(options.body), key: options.headers.get('Idempotency-Key') };
  calls.push(call);
  return respond(call);
};
const json = (body, status = 201) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const success = call => json({ id: call.url + '-id', ...call.body });
let checks = 0;
async function check(name, callback) {
  calls = [];
  respond = success;
  await callback();
  assert.equal(JSON.stringify(project), original, 'Work project must not be changed');
  checks++;
  console.log(`PASS ${name}`);
}
await check('skip performs no product request', async () => {
  assert.equal(Object.keys(await createProjectCompanions(project, [], {})).length, 0);
  assert.equal(calls.length, 0);
});
await check('each choice targets its own API, preserving cookie/CSRF authentication', async () => {
  setAuthCsrfToken('test-csrf');
  for (const product of ['knowledge', 'code']) {
    calls = [];
    const results = await createProjectCompanions(project, [product], {});
    assert.equal(calls.length, 1);
    const call = calls[0];
    assert.equal(call.url, product === 'knowledge' ? '/knowledge-api/spaces' : '/code-api/projects');
    assert.equal(call.options.credentials, 'same-origin');
    assert.equal(call.options.headers.get('X-CSRF-Token'), 'test-csrf');
    assert.ok(call.options.signal instanceof AbortSignal);
    assert.equal(call.body.name, project.name);
    assert.equal(call.body.description, project.description);
    assert.equal(call.body.key, product === 'knowledge' ? 'ORD_AI' : 'ord-ai');
    assert.ok(results[product].resource.id);
  }
  assert.equal(companionKey({ key: 'A__B-2' }, 'code'), 'a--b-2');
});
await check('partial failure preserves success; retry skips completed product and reuses key', async () => {
  respond = call => call.url.startsWith('/code-api') ? json({ detail: { message: 'Service unavailable' } }, 503) : success(call);
  const first = await createProjectCompanions(project, ['knowledge', 'code'], {});
  assert.ok(first.knowledge.resource);
  assert.ok(first.code.error);
  const failedKey = calls.find(call => call.url.startsWith('/code-api')).key;
  calls = [];
  respond = success;
  const retried = await createProjectCompanions(project, ['knowledge', 'code'], first);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].key, failedKey);
  assert.equal(retried.knowledge.resource.id, first.knowledge.resource.id);
  assert.ok(retried.code.resource);
  assert.ok(first.code.error, 'previous state must stay immutable');
});
await check('lost response retries the same operation without duplicate resources', async () => {
  const server = new Map();
  respond = call => {
    server.set(call.key, { id: 'persisted-once', ...call.body });
    throw Error('connection lost after commit');
  };
  const first = await createProjectCompanions(project, ['knowledge'], {});
  assert.ok(first.knowledge.error);
  const initial = calls[0];
  respond = call => {
    assert.equal(call.key, initial.key);
    assert.deepEqual(call.body, initial.body);
    return json(server.get(call.key));
  };
  const retried = await createProjectCompanions(project, ['knowledge'], first);
  assert.equal(retried.knowledge.resource.id, 'persisted-once');
  assert.equal(server.size, 1);
});
await check('permission and duplicate-key failures never become a success', async () => {
  for (const status of [403, 409, 422]) {
    respond = () => json({ detail: { message: 'Rejected by service' } }, status);
    const results = await createProjectCompanions(project, ['code'], {});
    assert.ok(results.code.error);
    assert.equal(results.code.resource, undefined);
  }
});
await check('HTML proxy response is rejected and new Work projects get separate operation keys', async () => {
  respond = () => new Response('<html>SPA fallback</html>', { headers: { 'Content-Type': 'text/html' } });
  assert.ok((await createProjectCompanions(project, ['code'], {})).code.error);
  const firstKey = calls[0].key;
  respond = success;
  await createProjectCompanions({ ...project, id: 'another-work-project' }, ['code'], {});
  assert.notEqual(calls[1].key, firstKey);
});
await check('shared product client retains default keys and explicit retry keys', async () => {
  const api = createProductApi('/code-api');
  await api.post('/projects', { key: 'one' });
  await api.post('/projects', { key: 'two' });
  await api.post('/projects', { key: 'one' }, { idempotencyKey: 'explicit-operation' });
  assert.ok(calls[0].key);
  assert.notEqual(calls[0].key, calls[1].key);
  assert.equal(calls[2].key, 'explicit-operation');
});

// Exercise the component's real handlers with controlled hook state, without a browser.
let hookIndex = 0;
let hooks = [];
const hooksApi = {
  useState(initial) {
    const index = hookIndex++;
    if (!(index in hooks)) hooks[index] = initial;
    return [hooks[index], value => { hooks[index] = typeof value === 'function' ? value(hooks[index]) : value; }];
  },
  useRef(initial) { const index = hookIndex++; return hooks[index] ??= { current: initial }; },
};
const componentSource = fs.readFileSync(path.join(root, 'frontend/src/components/ProjectCompanionsModal.tsx'), 'utf8');
// Only replace visual Ant Design components; all application handlers and API code run unchanged.
context.componentReact = hooksApi;
context.componentAntd = Object.fromEntries(['Alert', 'Button', 'Checkbox', 'Modal', 'Space'].map(name => [name, name]));
context.componentAntd.Typography = { Paragraph: 'Paragraph', Text: 'Text' };
const { ProjectCompanionsModal } = evaluate(componentSource
  .replace("import { useRef, useState } from 'react';", 'const { useRef, useState } = (globalThis as any).componentReact;')
  .replace("import { Alert, Button, Checkbox, Modal, Space, Typography } from 'antd';", 'const { Alert, Button, Checkbox, Modal, Space, Typography } = (globalThis as any).componentAntd;'), 'frontend/src/components/ProjectCompanionsModal.tsx');
function find(tree, type) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(child => find(child, type));
  return [...(tree.type === type ? [tree] : []), ...find(tree.props?.children, type), ...find(tree.props?.footer, type)];
}
let closed;
function render() { hookIndex = 0; return ProjectCompanionsModal({ project, onClose: () => closed++ }); }
await check('modal starts after creation, permits skipping and selecting neither', async () => {
  hooks = []; closed = 0;
  let tree = render();
  assert.equal(calls.length, 0, 'opening the prompt must not create anything');
  assert.ok(find(tree, 'Paragraph')[0].props.children.includes(project.name));
  find(tree, 'Button')[0].props.onClick();
  assert.equal(closed, 1);
  for (const checkbox of find(tree, 'Checkbox')) checkbox.props.onChange({ target: { checked: false } });
  tree = render();
  assert.equal(find(tree, 'Button')[1].props.disabled, true);
  await find(tree, 'Button')[1].props.onClick();
  assert.equal(calls.length, 0);
});
await check('modal prevents duplicate clicks and dismissal during creation, then retains successes', async () => {
  hooks = []; closed = 0;
  const pending = [];
  respond = call => new Promise(resolve => pending.push(() => resolve(success(call))));
  let tree = render();
  find(tree, 'Button')[1].props.onClick();
  find(tree, 'Button')[1].props.onClick();
  assert.equal(calls.length, 2, 'one request per product even on double click');
  tree = render();
  assert.equal(tree.props.closable, false);
  tree.props.onCancel();
  assert.equal(closed, 0);
  pending.forEach(resolve => resolve());
  // Flush the fetch, JSON parsing, Promise.all and component update chain.
  for (let i = 0; i < 20; i++) await new Promise(resolve => setImmediate(resolve));
  tree = render();
  assert.equal(find(tree, 'Alert').filter(alert => alert.props.type === 'success').length, 2);
  assert.ok(find(tree, 'Checkbox').every(checkbox => checkbox.props.disabled));
  assert.equal(find(tree, 'Button')[1].props.disabled, true);
  assert.equal(tree.props.closable, true);
});

// Run the actual Work save handler: failed list refresh must not undo a successful create.
const appSource = fs.readFileSync(path.join(root, 'frontend/src/App.tsx'), 'utf8');
const appTree = ts.createSourceFile('App.tsx', appSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let saveNode;
const visit = node => { if (ts.isFunctionDeclaration(node) && node.name?.text === 'saveProject') saveNode = node; ts.forEachChild(node, visit); };
visit(appTree);
assert.ok(saveNode);
const { saveProject } = evaluate('export ' + saveNode.getText(appTree), 'frontend/src/App.tsx');
await check('Work success opens prompt even when list refresh fails; failed create opens none', async () => {
  let prompted = null;
  let shouldFail = false;
  let reset = 0;
  Object.assign(context, {
    auth: { session: { user: { role: 'admin' } } }, t, errorText: error => error.message,
    api: { post: async () => { if (shouldFail) throw Error('Create failed'); return project; } },
    setProjectSaving() {}, setProjectModalOpen() {}, setProjects() {}, setProjectId() {},
    projectForm: { resetFields() { reset++; } },
    setCompanionProject: value => { prompted = value; },
    messageApi: { error() {}, success() {} }, refreshProjectList: async () => { throw Error('Refresh failed'); },
  });
  await saveProject({ key: project.key, name: project.name });
  assert.equal(prompted, project);
  assert.equal(reset, 1);
  prompted = null; shouldFail = true;
  await saveProject({ key: project.key, name: project.name });
  assert.equal(prompted, null);
  assert.equal(reset, 1);
  context.auth.session.user.role = 'worker';
  await saveProject({ key: project.key, name: project.name });
  assert.equal(prompted, null);
});
console.log(`Project companions: ${checks} API and interaction scenarios passed.`);
