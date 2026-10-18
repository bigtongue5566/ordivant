import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const ts = require('typescript');
const context = vm.createContext({ Headers, Response, AbortSignal, URL, Intl, console, window: { location: { origin: 'http://local.test' } } });
context.frontendEnv = {};
const t = source => source;
const cache = new Map();
const overrides = new Map([
  ['frontend/src/i18n/index.ts', { t, useI18n: () => ({ t }), useLocalizedForm() {}, formatDate: value => value || '—' }],
]);
function load(filename) {
  if (overrides.has(filename)) return overrides.get(filename);
  if (cache.has(filename)) return cache.get(filename);
  const code = ts.transpileModule(fs.readFileSync(path.join(root, filename), 'utf8').replaceAll('import.meta.env', 'globalThis.frontendEnv'), {
    fileName: filename,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const module = { exports: {} };
  const localRequire = name => {
    if (name === 'react') return hooksApi;
    if (name === 'antd') return antd;
    if (!name.startsWith('.')) return require(name);
    const absolute = path.resolve(root, path.dirname(filename), name);
    const candidate = [absolute + '.ts', absolute + '.tsx', path.join(absolute, 'index.ts')].find(fs.existsSync);
    assert.ok(candidate, `Cannot resolve ${name}`);
    return load(path.relative(root, candidate).replaceAll('\\', '/'));
  };
  vm.runInContext(`(function(require,module,exports){${code}\n})`, context, { filename, timeout: 1000 })(localRequire, module, module.exports);
  cache.set(filename, module.exports);
  return module.exports;
}
let hooks = [], hookIndex = 0, effect;
const hooksApi = {
  useState(initial) {
    const index = hookIndex++;
    if (!(index in hooks)) hooks[index] = initial;
    return [hooks[index], value => { hooks[index] = typeof value === 'function' ? value(hooks[index]) : value; }];
  },
  useRef(initial) { return hooks[hookIndex++] ??= { current: initial }; },
  useCallback(callback) { return callback; },
  useEffect(callback) { effect = callback; },
};
const antd = Object.fromEntries(['Alert', 'Button', 'Input', 'Modal', 'Popconfirm', 'Select', 'Space', 'Table', 'Tag'].map(name => [name, name]));
antd.Input = Object.assign(() => {}, { Password: 'Password' });
antd.Form = Object.assign(() => {}, { Item: 'FormItem', useForm: () => [{ resetFields() {} }] });
antd.Typography = { Paragraph: 'Paragraph', Text: 'Text', Title: 'Title' };
let user = { role: 'member', permissions: { work: { role: 'worker', scope_ids: ['project-1'] } } };
overrides.set('frontend/src/auth/AuthContext.tsx', { useAuth: () => ({ session: { user } }) });
const { authApi, setAuthCsrfToken } = load('frontend/src/auth/client.ts');
const { accessTokenExamples } = load('frontend/src/auth/accessTokenExamples.ts');
let calls = [], reply;
context.fetch = async (url, init) => { calls.push({ url, init }); return reply(url, init); };
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
let checks = 0;
async function check(name, callback) { calls = []; await callback(); checks++; console.log(`PASS ${name}`); }
const metadata = { id: 'token-1', name: 'Test tool', prefix: 'ord_pat_prefix', products: ['work'], created_at: '2026-10-01T00:00:00Z', expires_at: '2099-01-01T00:00:00Z', last_used_at: null, revoked_at: null };
await check('management API uses session cookie, CSRF and never sends bearer credentials', async () => {
  setAuthCsrfToken('synthetic-csrf');
  reply = (_url, init) => init.method === 'DELETE' ? new Response(null, { status: 204 }) : json(init.method === 'POST' ? { token: 'synthetic-once', access_token: metadata } : { tokens: [metadata] });
  await authApi.accessTokens();
  await authApi.createAccessToken({ name: 'Test tool', products: ['work'], expires_in_days: 30 });
  await authApi.revokeAccessToken('token/1');
  assert.deepEqual(calls.map(call => call.url), ['/auth-api/access-tokens', '/auth-api/access-tokens', '/auth-api/access-tokens/token%2F1']);
  for (const { init } of calls) {
    assert.equal(init.credentials, 'same-origin');
    assert.equal(init.cache, 'no-store');
    assert.equal(init.headers.has('Authorization'), false);
    if (init.method) assert.equal(init.headers.get('X-CSRF-Token'), 'synthetic-csrf');
  }
  assert.deepEqual(JSON.parse(calls[1].init.body), { name: 'Test tool', products: ['work'], expires_in_days: 30 });
});
await check('three MCP examples select correct module, env and public prefix with placeholders', async () => {
  for (const [product, prefix, env, module] of [
    ['work', '/api', 'ORDIVANT', 'ordivant'],
    ['knowledge', '/knowledge-api', 'ORDIVANT_KNOWLEDGE', 'ordivant_knowledge'],
    ['code', '/code-api', 'ORDIVANT_CODE', 'ordivant_code'],
  ]) {
    const example = accessTokenExamples(product, `http://local.test${prefix}/`);
    const server = JSON.parse(example.mcp).mcpServers[`ordivant-${product}`];
    assert.equal(server.env[`${env}_API_URL`], `http://local.test${prefix}`);
    assert.equal(server.env[`${env}_API_TOKEN`], '<PERSONAL_ACCESS_TOKEN>');
    assert.equal(server.args.at(-1), `${module}.mcp_server`);
    assert.ok(server.args[2].startsWith('<ORDIVANT_REPO>/'));
    assert.ok(example.api.includes(`${prefix}/me`));
    assert.ok(example.api.includes('Bearer <PERSONAL_ACCESS_TOKEN>'));
  }
});
const { AccessTokensPanel } = load('frontend/src/auth/AccessTokensPanel.tsx');
function find(tree, type) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(child => find(child, type));
  return [...(tree.type === type ? [tree] : []), ...find(tree.props?.children, type), ...find(tree.props?.footer, type)];
}
function render(product = 'work') { hookIndex = 0; return AccessTokensPanel({ product }); }
const tick = () => new Promise(resolve => setImmediate(resolve));
await check('panel lists metadata and offers only authorized products', async () => {
  hooks = [];
  reply = () => json({ tokens: [metadata] });
  render(); effect(); await tick();
  const tree = render();
  assert.equal(find(tree, 'Table')[0].props.dataSource[0].id, metadata.id);
  const select = find(tree, 'Select').find(item => item.props.mode === 'multiple');
  assert.equal(select.props.options.length, 1);
  assert.equal(select.props.options[0].value, 'work');
  assert.equal(find(tree, 'Modal')[0].props.open, false);
  assert.equal(find(tree, 'Password').length, 0);
});
await check('duplicate submission creates once; secret disappears on close and never enters examples', async () => {
  let finish;
  reply = () => new Promise(resolve => { finish = () => resolve(json({ token: 'synthetic-once', access_token: metadata }, 201)); });
  const form = find(render(), antd.Form)[0];
  form.props.onFinish({ name: 'Test tool', products: ['work'], expires_in_days: 7 });
  form.props.onFinish({ name: 'Test tool', products: ['work'], expires_in_days: 7 });
  assert.equal(calls.length, 1);
  finish(); await tick();
  let tree = render();
  assert.equal(find(tree, 'Modal')[0].props.open, true);
  assert.equal(find(tree, 'Password')[0].props.value, 'synthetic-once');
  assert.ok(find(tree, 'pre').every(item => !item.props.children.includes('synthetic-once')));
  find(tree, 'Modal')[0].props.onCancel();
  tree = render();
  assert.equal(find(tree, 'Password').length, 0);
  assert.equal(find(tree, 'Modal')[0].props.open, false);
});
await check('revocation refreshes server metadata; API failure stays an error', async () => {
  reply = (_url, init) => init.method === 'DELETE' ? new Response(null, { status: 204 }) : json({ tokens: [{ ...metadata, revoked_at: '2026-10-19T00:00:00Z' }] });
  let tree = render();
  const column = find(tree, 'Table')[0].props.columns.find(item => item.key === 'action');
  await column.render(null, metadata).props.onConfirm();
  tree = render();
  assert.ok(find(tree, 'Table')[0].props.dataSource[0].revoked_at);
  assert.equal(calls[0].init.method, 'DELETE');
  reply = () => json({ detail: { code: 'token_product_forbidden' } }, 403);
  find(tree, antd.Form)[0].props.onFinish({ name: 'Denied', products: ['code'], expires_in_days: 7 });
  await tick();
  tree = render();
  assert.ok(find(tree, 'Alert').some(item => item.props.type === 'error'));
  assert.equal(find(tree, 'Modal')[0].props.open, false);
});
await check('standalone builds show only their own API endpoint and MCP example', async () => {
  user = { role: 'admin', permissions: {} };
  for (const product of ['work', 'knowledge', 'code']) {
    hooks = [];
    context.frontendEnv.MODE = product;
    const tree = render(product);
    const select = find(tree, 'Select').find(item => item.props['aria-label'] === '連線範例的產品');
    assert.equal(select.props.options.length, 1);
    assert.equal(select.props.options[0].value, product);
    assert.ok(find(tree, 'pre')[0].props.children.includes('http://local.test/api/me'));
  }
});
console.log(`ACCESS_TOKENS_OK: ${checks} checks`);
