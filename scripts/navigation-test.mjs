import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const ts = require('typescript');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const translate = source => typeof source === 'string' ? source : source?.key ?? '';
const auth = {session: null};
const form = {resetFields() {}, setFieldsValue() {}, getFieldValue() {}};
const messageApi = {error() {}, success() {}};
const ui = new Proxy({
  Form: Object.assign('Form', {}),
  Typography: {Text: 'Text', Title: 'Title', Paragraph: 'Paragraph'},
  message: {useMessage: () => [messageApi, null]},
}, {get: (target, key) => target[key] ?? key});
ui.Form = Object.assign(() => null, {useForm: () => [form], useWatch: () => undefined, Item: 'Form.Item'});
ui.Input = Object.assign(() => null, {TextArea: 'TextArea', Search: 'Search'});

function harness(href, product = 'work', responses = {}) {
  let url = new URL(href, 'http://localhost');
  const state = [], effects = [], calls = [], cache = new Map();
  let cursor = 0, dirty = true, pending = [], tree, component;
  const window = {
    location: {get href() {return url.href;}, get search() {return url.search;}, get pathname() {return url.pathname;}},
    history: {state: {keep: true}, replaceState(state, _, next) {this.state = state; url = new URL(next, url);}},
    setTimeout: fn => {queueMicrotask(fn); return 1;}, clearTimeout() {},
  };
  const hooks = {
    useState(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = typeof initial === 'function' ? initial() : initial;
      return [state[index], action => {
        const next = typeof action === 'function' ? action(state[index]) : action;
        if (!Object.is(next, state[index])) {state[index] = next; dirty = true;}
      }];
    },
    useRef(initial) {const [ref] = hooks.useState(() => ({current: initial})); return ref;},
    useMemo(fn, deps) {
      const index = cursor++;
      if (!(index in state) || !same(state[index].deps, deps)) state[index] = {deps, value: fn()};
      return state[index].value;
    },
    useCallback(fn, deps) {return hooks.useMemo(() => fn, deps);},
    useEffect(fn, deps) {
      const index = cursor++;
      if (!effects[index] || !same(effects[index].deps, deps)) pending.push(() => {
        effects[index]?.cleanup?.();
        effects[index] = {deps, cleanup: fn()};
      });
    },
  };
  const project1 = {id: 'p1', key: 'ONE', name: 'One'};
  const project2 = {id: 'p2', key: 'TWO', name: 'Two'};
  const principal = {id: 'person', name: 'Synthetic User', role: 'admin', kind: 'human'};
  const api = new Proxy({}, {get: (_, method) => async (...args) => {
    calls.push([method, ...args]);
    if (Object.hasOwn(responses, method)) return responses[method](...args);
    if (method === 'me') return principal;
    if (method === 'projects') return [project1, project2];
    if (method === 'projectContext') return {project: args[0] === 'p2' ? project2 : project1, agents: [], tasks: []};
    if (method === 'overview') return {counts: {total: 0, ready: 0, in_progress: 0, in_review: 0, done: 0}, cost_usd: 0};
    if (method === 'planning') return {stages: [], fields: [], sprints: [], milestones: [], forms: [], rules: []};
    if (method === 'health') return {status: 'ok', gitea_configured: true};
    if (method === 'get') {
      if (args[0] === '/projects') return [project1, project2];
      if (args[0] === '/spaces') return [{id: 's1', key: 'ONE', name: 'One'}, {id: 's2', key: 'TWO', name: 'Two'}];
      if (args[0].startsWith('/repositories?')) return [{id: 'r1', owner: 'test', name: 'One', project_id: 'p2', branches: []}, {id: 'r2', owner: 'test', name: 'Two', project_id: 'p2', branches: []}];
      if (args[0].endsWith('/pulls')) return [{number: 7, title: 'Synthetic pull'}];
      if (args[0].includes('/pulls/')) return {number: 7, title: 'Synthetic pull', source_refs: []};
      if (args[0] === '/api/health') return {status: 'ok', mode: 'production'};
    }
    return [];
  }});
  const imports = {
    react: hooks,
    antd: ui,
    '@ant-design/icons': new Proxy({}, {get: (_, key) => key}),
    i18n: {useI18n: () => ({t: translate, locale: 'en'}), t: translate, useLocalizedForm() {}, formatDate: () => '', formatNumber: String, localized: translate},
    auth: {useAuth: () => auth, AuthProvider: 'AuthProvider'},
    api: {api, createIdempotencyKey: () => 'synthetic'},
    productApi: {createProductApi: () => api, productApiPrefix: () => `/${product}-api`, ProductApiError: Error},
  };
  function load(file, expose = '') {
    if (cache.has(file)) return cache.get(file);
    const source = read(file) + expose;
    const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}}).outputText;
    const module = {exports: {}};
    const localRequire = name => {
      if (name.includes('useNavigationState')) return load('frontend/src/shared/useNavigationState.ts');
      if (name === 'react/jsx-runtime') return {jsx: (type, props) => ({type, props}), jsxs: (type, props) => ({type, props}), Fragment: 'Fragment'};
      if (imports[name]) return imports[name];
      if (name.endsWith('/i18n')) return imports.i18n;
      if (name.endsWith('/AuthContext')) return imports.auth;
      if (name.endsWith('/api')) return imports.api;
      if (name.endsWith('/productApi')) return imports.productApi;
      return new Proxy({}, {get: (_, key) => key});
    };
    vm.runInNewContext(compiled, {module, exports: module.exports, require: localRequire, window, URL, URLSearchParams, console, setTimeout, clearTimeout, Intl}, {filename: file, timeout: 1500});
    cache.set(file, module.exports);
    return module.exports;
  }
  function render() {cursor = 0; dirty = false; tree = component(); const run = pending; pending = []; run.forEach(fn => fn()); return tree;}
  return {
    load, calls, get url() {return url;}, get window() {return window;},
    mount(fn) {component = fn; render();}, render,
    async settle() {
      for (let i = 0; i < 35; i++) {
        await new Promise(resolve => setImmediate(resolve));
        if (!dirty) return tree;
        render();
      }
      throw new Error('Render/effect loop did not settle');
    },
    nodes(type) {
      const found = [];
      function visit(node) {
        if (Array.isArray(node)) return node.forEach(visit);
        if (!node || typeof node !== 'object') return;
        if (node.type === type || node.type?.name === type) found.push(node.props);
        visit(node.props?.children);
        visit(node.props?.headerExtra);
      }
      visit(tree);
      return found;
    },
  };
}
function same(a, b) {return a?.length === b?.length && a.every((value, index) => Object.is(value, b[index]));}
let checks = 0;
async function check(name, fn) {await fn(); console.log(`PASS ${name}`); checks++;}
const definitions = {
  work: ['frontend/src/App.tsx', 'WorkWorkspace', 'project', 'p2', 'agents'],
  knowledge: ['frontend/src/products/knowledge/KnowledgeApp.tsx', 'KnowledgeWorkspace', 'space', 's2', 'decisions'],
  code: ['frontend/src/products/code/CodeApp.tsx', 'CodeWorkspace', 'project', 'p2', 'pulls'],
};
function workspace(product, href, responses) {
  const [file, name] = definitions[product];
  const h = harness(href, product, responses);
  const component = h.load(file, `\nexport { ${name} as NavigationTestWorkspace };`).NavigationTestWorkspace;
  h.mount(component);
  return h;
}
async function login(h) {
  await h.settle(); // Auth provider starts with no session on every hard reload.
  auth.session = {csrf_token: 'synthetic', user: {role: 'admin'}};
  h.render();
  await h.settle();
}

await check('URL state survives remount; independent writes preserve other keys and hash', () => {
  const h = harness('/work?section=agents&project=p2&resource=task-1#anchor');
  const {useNavigationState} = h.load('frontend/src/shared/useNavigationState.ts');
  let section, scope;
  h.mount(() => {section = useNavigationState('section', 'tasks', ['tasks', 'agents']); scope = useNavigationState('project', '');});
  assert.equal(section[0], 'agents'); assert.equal(scope[0], 'p2');
  section[1]('tasks'); scope[1](old => `${old} & 中文`);
  assert.equal(h.url.searchParams.get('section'), 'tasks');
  assert.equal(h.url.searchParams.get('project'), 'p2 & 中文');
  assert.equal(h.url.searchParams.get('resource'), 'task-1');
  assert.equal(h.url.hash, '#anchor'); assert.equal(h.window.history.state.keep, true);
  const reload = harness(h.url.href);
  const hook = reload.load('frontend/src/shared/useNavigationState.ts').useNavigationState;
  reload.mount(() => {assert.equal(hook('project', '')[0], 'p2 & 中文');});
});

for (const product of ['work', 'knowledge', 'code']) {
  const [, , scope, selected, section] = definitions[product];
  await check(`${product}: actual authentication bootstrap and authorized list preserve requested page/scope`, async () => {
    auth.session = null;
    const h = workspace(product, `/${product}?section=${section}&${scope}=${selected}&repository=r2`);
    await login(h);
    assert.equal(h.url.searchParams.get(scope), selected);
    assert.equal(h.url.searchParams.get('section'), section);
    if (product === 'work') assert.equal(h.nodes('WorkNavigation')[0].active, 'agents');
    else assert.equal(h.nodes('ProductShell')[0].activeSection, section);
    if (product === 'code') assert.equal(h.url.searchParams.get('repository'), 'r2');
  });
  await check(`${product}: stale scope falls back to authorized list while retaining section`, async () => {
    auth.session = null;
    const h = workspace(product, `/${product}?section=${section}&${scope}=removed`);
    await login(h);
    assert.equal(h.url.searchParams.get(scope), product === 'knowledge' ? 's1' : 'p1');
    assert.equal(h.url.searchParams.get('section'), section);
  });
  await check(`${product}: user navigation is encoded and restored by a new workspace instance`, async () => {
    auth.session = null;
    const h = workspace(product, `/${product}?${scope}=${selected}`);
    await login(h);
    if (product === 'work') h.nodes('WorkNavigation')[0].onChange('agents');
    else h.nodes('ProductShell')[0].onSectionChange(section);
    await h.settle();
    assert.equal(h.url.searchParams.get('section'), section);
    auth.session = null;
    const reloaded = workspace(product, h.url.href);
    await login(reloaded);
    assert.equal(reloaded.url.searchParams.get('section'), section);
    assert.equal(reloaded.url.searchParams.get(scope), selected);
  });
}

for (const [file, name, key, initial, next, control] of [
  ['frontend/src/Automation.tsx', 'Automation', 'automation-tab', 'history', 'workflows', 'Segmented'],
  ['frontend/src/ToolSettings.tsx', 'ToolSettings', 'tools-tab', 'sandbox', 'connections', 'Segmented'],
  ['frontend/src/components/planning/PlanningWorkspace.tsx', 'PlanningWorkspace', 'planning-tab', 'settings', 'intake', 'Tabs'],
  ['frontend/src/components/planning/PlanningWorkspace.tsx', 'PlanningSettings', 'planning-settings-tab', 'milestone', 'rule', 'Tabs'],
]) {
  await check(`${name}: actual controlled subtab restores and survives switching/reload`, async () => {
    const props = {projectId: 'p2', agents: [], participants: [], metadata: {stages: [], fields: [], sprints: [], milestones: [], forms: [], rules: []}};
    const mount = href => {
      const h = harness(href);
      const component = h.load(file, name === 'PlanningSettings' ? '\nexport { PlanningSettings };' : '')[name];
      h.mount(() => component(props));
      return h;
    };
    const h = mount(`/work?section=planning&project=p2&${key}=${initial}`);
    await h.settle();
    assert.equal(h.nodes(control)[0][control === 'Tabs' ? 'activeKey' : 'value'], initial);
    h.nodes(control)[0].onChange(next);
    await h.settle();
    assert.equal(h.url.searchParams.get(key), next);
    const reloaded = mount(h.url.href);
    await reloaded.settle();
    assert.equal(reloaded.nodes(control)[0][control === 'Tabs' ? 'activeKey' : 'value'], next);
  });
}

await check('invalid section values use a real default rather than a blank page', async () => {
  auth.session = null;
  const h = workspace('work', '/work?section=unknown&project=p2');
  await login(h);
  assert.equal(h.nodes('WorkNavigation')[0].active, 'tasks');
});

await check('Code PR detail survives reload, and closing removes its deep link', async () => {
  auth.session = null;
  const h = workspace('code', '/code?section=pulls&project=p2&repository=r2&pull=7');
  await h.settle();
  assert.ok(!h.calls.some(call => call[0] === 'get' && call[1].includes('/pulls')), 'no PR data requests before authentication');
  await login(h);
  assert.equal(h.nodes('Drawer')[0].open, true);
  h.nodes('Drawer')[0].onClose();
  await h.settle();
  assert.equal(h.nodes('Drawer')[0].open, false);
  assert.equal(h.url.searchParams.has('pull'), false);
  auth.session = null;
  const reloaded = workspace('code', h.url.href);
  await login(reloaded);
  assert.equal(reloaded.nodes('Drawer')[0].open, false);
});

await check('a task resource does not override an explicitly saved Work section', async () => {
  auth.session = null;
  const h = workspace('work', '/work?section=agents&project=p2&resource=task-1', {
    taskContext: async () => ({task: {id: 'task-1', project_id: 'p2', status: 'backlog', title: 'Synthetic task', labels: [], acceptance_criteria: []}, executions: [], artifacts: [], messages: [], events: [], dependencies: []}),
  });
  await login(h);
  assert.equal(h.url.searchParams.get('section'), 'agents');
  assert.equal(h.nodes('WorkNavigation')[0].active, 'agents');
});

await check('Knowledge document resource preserves the saved decisions section', async () => {
  auth.session = null;
  const h = workspace('knowledge', '/knowledge?section=decisions&space=s2&resource=doc-1', {
    get: async route => {
      if (route === '/spaces') return [{id: 's2', key: 'TWO', name: 'Two'}];
      if (route === '/documents/doc-1') return {document: {id: 'doc-1', space_id: 's2', archived: false}};
      return [];
    },
  });
  await login(h);
  assert.equal(h.nodes('ProductShell')[0].activeSection, 'decisions');
  assert.equal(h.url.searchParams.get('space'), 's2');
});

await check('Code stale project drops nested PR target instead of opening the same number in a different project', async () => {
  auth.session = null;
  const h = workspace('code', '/code?section=pulls&project=removed&repository=old-repo&pull=7');
  await login(h);
  assert.equal(h.url.searchParams.get('project'), 'p1');
  assert.equal(h.url.searchParams.has('pull'), false);
  assert.equal(h.nodes('Drawer')[0].open, false);
});

await check('Code resource links without a section retain their original PR destination', async () => {
  auth.session = null;
  const h = workspace('code', '/code?resource=old-pull&kind=pull', {
    get: async route => {
      if (route === '/projects') return [{id: 'p2', key: 'TWO', name: 'Two'}];
      if (route === '/resources/pull/old-pull') return {project_id: 'p2', repository_id: 'r2', resource_kind: 'pull', pull_number: 7};
      if (route.startsWith('/repositories?')) return [{id: 'r2', name: 'Repo', owner: 'test', project_id: 'p2', branches: []}];
      if (route.endsWith('/pulls')) return [{number: 7}];
      if (route.endsWith('/pulls/7')) return {number: 7, title: 'Synthetic pull'};
      return [];
    },
  });
  await login(h);
  assert.equal(h.url.searchParams.get('section'), 'pulls');
  assert.equal(h.url.searchParams.get('repository'), 'r2');
  assert.equal(h.nodes('Drawer')[0].open, true);
});

console.log(`${checks} navigation regression scenarios passed.`);
