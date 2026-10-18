import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const ts = require('typescript');
function setup(role = 'admin', href = '/work?section=tools&project=p2&settings=security', locale = 'zh-TW') {
  let url = new URL(href, 'http://local.test');
  const state = [], effects = [], cache = new Map();
  let cursor = 0;
  const messages = [];
  const hooks = {
    useState(initial) {const index = cursor++; if (!(index in state)) state[index] = typeof initial === 'function' ? initial() : initial; return [state[index], action => {state[index] = typeof action === 'function' ? action(state[index]) : action;}];},
    useRef(initial) {const [ref] = hooks.useState(() => ({current: initial})); return ref;},
    useCallback: fn => fn,
    useEffect: fn => effects.push(fn),
  };
  const events = new EventTarget();
  const window = {addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events), dispatchEvent: events.dispatchEvent.bind(events), location: {get search() {return url.search;}, get href() {return url.href;}}, history: {state: null, replaceState(_, __, href) {url = new URL(href, url);}}};
  const form = {resetFields() {}};
  const ui = new Proxy({
    message: {useMessage: () => [{error: value => messages.push(value)}, null]},
    Typography: {Text: 'Text', Paragraph: 'Paragraph'},
    Form: Object.assign(() => {}, {useForm: () => [form], Item: 'FormItem'}),
    Input: {Password: 'Password'}, Descriptions: {Item: 'DescriptionItem'},
  }, {get: (target, key) => target[key] ?? key});
  const user = {role, name: 'Synthetic User', email: 'fixture@example.test', credential_type: 'password'};
  const imports = {
    react: hooks, antd: ui,
    './AuthContext': {useAuth: () => ({session: {user}, logout: async () => {throw new Error('Synthetic logout failure');}})},
    './client': {authApi: {sessions: async () => ({sessions: [{id: 's1', current: true, expires_at: '2026-10-19T04:30:00Z', last_seen_at: '2026-10-19T04:00:00Z'}]})}},
  };
  let catalog = {};
  const t = source => catalog[source] ?? source;
  function load(file, expose = '') {
    if (cache.has(file)) return cache.get(file);
    const source = fs.readFileSync(path.join(root, file), 'utf8') + expose;
    const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}}).outputText;
    const module = {exports: {}};
    const localRequire = name => {
      if (name === 'react/jsx-runtime') return {jsx: (type, props, key) => ({type, props, key}), jsxs: (type, props, key) => ({type, props, key})};
      if (imports[name]) return imports[name];
      if (name.endsWith('/AuthContext')) return imports['./AuthContext'];
      if (name.endsWith('/settingsNavigation')) return load('frontend/src/auth/settingsNavigation.ts');
      if (name.endsWith('/useNavigationState')) return load('frontend/src/shared/useNavigationState.ts');
      if (name === './AccountSettingsLayout') return load('frontend/src/auth/AccountSettingsLayout.tsx');
      if (name.endsWith('/i18n')) return {useI18n: () => ({t}), useLocalizedForm() {}, formatDate: value => value};
      return new Proxy({}, {get: (_, key) => key});
    };
    vm.runInNewContext(compiled, {module, exports: module.exports, require: localRequire, URL, URLSearchParams, window, Event}, {filename: file, timeout: 1000});
    cache.set(file, module.exports);
    return module.exports;
  }
  for (const name of fs.readdirSync(path.join(root, 'frontend/src/i18n/catalogs'))) {
    if (locale === 'en' && name.endsWith('.en.ts')) Object.assign(catalog, load(`frontend/src/i18n/catalogs/${name}`).default);
    if (locale === 'zh-CN' && name.endsWith('.zh-CN.json')) Object.assign(catalog, JSON.parse(fs.readFileSync(path.join(root, 'frontend/src/i18n/catalogs', name), 'utf8')));
  }
  const {AccountControl, SecurityPanel} = load('frontend/src/auth/AccountSettings.tsx', '\nexport { SecurityPanel };');
  function render(options = {}) {cursor = 0; return AccountControl({product: 'work', productLabel: 'Work', displayName: user.name, businessRole: 'manager', ...options});}
  function layout() {const modals = find(render(), 'Modal'); const active = modals.find(node => node.props.open) ?? modals[0]; const node = find(active, 'AccountSettingsLayout')[0]; return node.type(node.props);}
  return {render, layout, load, get url() {return url;}, t, user, messages,
    security: () => {cursor = 0; return SecurityPanel({onLogout: async () => {}});},
    effects, openOrganization: () => { effects.forEach(fn => fn()); load('frontend/src/auth/settingsNavigation.ts').openOrganizationSettings(); },
  };
}
function find(tree, type) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(node => find(node, type));
  return [...(tree.type === type || tree.type?.name === type ? [tree] : []), ...find(tree.props?.children, type)];
}
let checks = 0;
for (const locale of ['zh-TW', 'zh-CN', 'en']) {
  const h = setup('admin', undefined, locale);
  let modals = find(h.render(), 'Modal');
  const modal = modals.find(node => node.props.open);
  assert.equal(modal.props.title, h.t('帳號設定'));
  assert.equal(modal.props.width, 'min(1180px, calc(100vw - 48px))');
  assert.equal(modal.props.maskClosable, false);
  assert.equal(find(h.render(), 'Drawer').length, 0);
  assert.equal(find(h.render(), 'Tabs').length, 0);
  assert.equal(find(h.layout(), 'button').length, 3, 'admins have the same personal settings as members');
  assert.equal(find(h.layout(), 'option').length, 3);
  assert.equal(find(h.layout(), 'h2')[0].props.children, h.t('安全性'));
  h.openOrganization();
  modals = find(h.render(), 'Modal');
  assert.equal(modals.filter(node => node.props.open).length, 1, 'personal and organization dialogs are exclusive');
  assert.equal(modals.find(node => node.props.open).props.title, h.t('組織管理'));
  assert.equal(h.url.searchParams.get('settings'), 'users');
  assert.equal(h.url.searchParams.get('project'), 'p2');
  assert.equal(h.url.searchParams.get('section'), 'tools');
  assert.equal(find(h.layout(), 'button').length, 4);
  assert.equal(find(h.layout(), 'option').length, 4);
  assert.equal(find(h.layout(), 'h2')[0].props.children, h.t('使用者與邀請'));
  const reloaded = setup('admin', h.url.href, locale);
  assert.equal(find(reloaded.layout(), 'h2')[0].props.children, h.t('使用者與邀請'));
  find(h.layout(), 'select')[0].props.onChange({target: {value: 'identity-audit'}});
  assert.equal(h.url.searchParams.get('settings'), 'identity-audit');
  find(h.render(), 'Modal').find(node => node.props.open).props.onCancel();
  assert.ok(find(h.render(), 'Modal').every(node => !node.props.open));
  assert.equal(h.url.searchParams.has('settings'), false);
  assert.equal(h.url.searchParams.get('project'), 'p2');
  checks++;

  for (const product of ['knowledge', 'code']) {
    const props = {product,productLabel: product,principal:{name:'Synthetic',role:'manager'},sectionLabel:'Workspace',navigation:[{key:'documents',label:'Documents',icon:null}],activeSection:'documents',onSectionChange(){},mode:'production',serviceStatus:'ok',title:'Workspace',children:null};
    const shell = h.load('frontend/src/products/shared/ProductShell.tsx').ProductShell(props);
    const nav = find(shell, 'SidebarNavigation')[0];
    assert.ok(nav.props.groups.flatMap(group => group.items).some(item => item.key === 'organization-settings'), `${product}: Identity admin has a separate organization entry`);
    const ordinary = setup('member', '/'+product, locale);
    const memberShell = ordinary.load('frontend/src/products/shared/ProductShell.tsx').ProductShell(props);
    assert.ok(find(memberShell, 'SidebarNavigation')[0].props.groups.flatMap(group => group.items).every(item => item.key !== 'organization-settings'), `${product}: product manager is not an Identity admin`);
  }

  const floating = setup('admin', '/work?settings=security', locale);
  let dismissed = 0;
  const floatingOptions = {variant: 'sidebar', onAction: () => dismissed++, renderControls: controls => ({type: 'floating-controls', props: {children: controls}})};
  const floatingTree = floating.render(floatingOptions);
  assert.equal(find(floatingTree, 'Modal')[0].props.open, true);
  const wrappedControls = find(floatingTree, 'floating-controls')[0];
  assert.equal(find(wrappedControls, 'Modal').length, 0);
  assert.ok(!find(wrappedControls, 'Button').some(node => node.props['aria-label'] === floating.t('組織管理')), 'administration does not live in the personal menu');
  find(wrappedControls, 'Button').find(node => node.props['aria-label'] === floating.t('帳號設定')).props.onClick();
  assert.equal(dismissed, 1);
  assert.equal(floating.url.searchParams.get('settings'), 'profile');
  checks++;

  const member = setup('member', '/knowledge?settings=governance&space=s2', locale);
  assert.ok(find(member.render(), 'Modal').every(node => !node.props.open), 'member deep links cannot open administration');
  member.openOrganization();
  assert.equal(member.url.searchParams.get('settings'), 'governance', 'organization event does not grant access');
  const groups = find(member.render(), 'AccountSettingsLayout').flatMap(node => node.props.groups);
  assert.ok(groups.flatMap(group => group.sections).every(section => ['profile', 'security', 'api-mcp'].includes(section.key)));
  const ordinary = setup('member', '/code?settings=profile', locale);
  assert.equal(find(ordinary.layout(), 'button').length, 3);
  assert.equal(find(ordinary.layout(), 'option').length, 3);
  assert.equal(find(ordinary.layout(), 'h2')[0].props.children, ordinary.t('帳號'));
  checks++;

  const security = setup('member', '/work?settings=security', locale);
  assert.equal(find(security.security(), 'Password').length, 3);
  const table = find(security.security(), 'Table')[0];
  assert.equal(table.props.scroll.x, 570);
  assert.equal(table.props.columns[1].render('synthetic-date').props.className, 'auth-session-date');
  const sso = setup('member', '/work?settings=security', locale);
  sso.user.credential_type = 'sso';
  assert.equal(find(sso.security(), 'Password').length, 0);
  checks++;
}
console.log(`ACCOUNT_SETTINGS_OK: ${checks} personal/admin separation, entry events, permission, reload, responsive-control and security scenarios across 3 locales`);
