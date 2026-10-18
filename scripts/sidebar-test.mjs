import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const ts = require('typescript');
function harness(locale) {
  const cache = new Map();
  let catalog = {}, state = false;
  const t = source => catalog[source] ?? source;
  function load(file) {
    if (cache.has(file)) return cache.get(file);
    const module = {exports: {}};
    const code = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
      compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX},
    }).outputText;
    const localRequire = name => {
      if (name === 'react/jsx-runtime') return {jsx: (type, props, key) => ({type, props, key}), jsxs: (type, props, key) => ({type, props, key})};
      if (name === 'react') return {useEffect() {}, useRef: () => ({current: null}), useId: () => 'fixture-tools', useState: () => [state, next => {state = typeof next === 'function' ? next(state) : next;}]};
      if (name.endsWith('/i18n')) return {useI18n: () => ({t})};
      if (name.endsWith('/settingsNavigation')) return {openOrganizationSettings: () => {}};
      if (name.endsWith('/SidebarNavigation')) return load('frontend/src/products/shared/SidebarNavigation.tsx');
      return new Proxy({}, {get: (_, key) => key});
    };
    vm.runInNewContext(code, {exports: module.exports, module, require: localRequire}, {filename: file});
    cache.set(file, module.exports);
    return module.exports;
  }
  for (const name of fs.readdirSync(path.join(root, 'frontend/src/i18n/catalogs'))) {
    if (locale === 'en' && name.endsWith('.en.ts')) Object.assign(catalog, load(`frontend/src/i18n/catalogs/${name}`).default);
    if (locale === 'zh-CN' && name.endsWith('.zh-CN.json')) Object.assign(catalog, JSON.parse(fs.readFileSync(path.join(root, 'frontend/src/i18n/catalogs', name), 'utf8')));
  }
  return {load, t};
}
function find(tree, type) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(node => find(node, type));
  return [...(tree.type === type || tree.type?.name === type ? [tree] : []), ...find(tree.props?.children, type)];
}
for (const locale of ['zh-TW', 'zh-CN', 'en']) {
  const h = harness(locale);
  const {WorkNavigation} = h.load('frontend/src/navigation/WorkNavigation.tsx');
  let selected = 'tools';
  function render(isAdmin) {
    const component = WorkNavigation({active: selected, isAdmin, unreadCount: 123, onChange: key => {selected = key;}});
    return component.type(component.props);
  }
  const admin = render(true);
  const buttons = find(admin, 'button');
  const options = find(admin, 'option');
  assert.equal(buttons.length, 12);
  assert.equal(options.length, 12);
  assert.equal(find(admin, 'optgroup').length, 4);
  assert.equal(buttons.filter(node => node.props['aria-current'] === 'page').length, 1);
  assert.equal(find(admin, 'span').find(node => node.props.className === 'nav-count').props.children, '99+');
  const selector = find(admin, 'select')[0];
  selector.props.onChange({target: {value: 'agents'}});
  assert.equal(selected, 'agents', 'mobile navigation selects the same section as desktop');
  buttons[0].props.onClick();
  assert.equal(selected, 'overview');
  buttons.find(node => find(node, 'span').some(child => child.props.children === h.t('組織管理'))).props.onClick();
  assert.equal(selected, 'overview', 'organization entry preserves the current product section');
  const member = render(false);
  assert.equal(find(member, 'button').length, 10);
  assert.ok(find(member, 'option').every(node => !['model-settings', 'organization-settings'].includes(node.props.value)));

  const {WorkspaceAccount} = h.load('frontend/src/products/shared/WorkspaceAccount.tsx');
  const name = 'Synthetic user with a long display name';
  const props = {product: 'work', productLabel: 'Work', name, role: 'manager', roleLabel: 'Manager', serviceStatus: 'ok'};
  const account = WorkspaceAccount(props);
  const control = find(account, 'AccountControl')[0];
  assert.equal(control.props.variant, 'sidebar');
  let popup = control.props.renderControls({type: 'fixture-controls', props: {}});
  assert.equal(popup.props.open, false, 'account controls do not occupy sidebar space until opened');
  assert.equal(find(popup.props.content, 'LanguageSelect').length, 1);
  assert.equal(popup.props.content.props.role, 'dialog');
  assert.ok(find(popup, 'strong').every(node => node.props.children === name));
  const toggle = find(popup, 'button')[0];
  assert.equal(toggle.props['aria-expanded'], false);
  assert.equal(toggle.props['aria-haspopup'], 'dialog');
  assert.equal(find(popup, 'span').find(node => node.props.role === 'status').props['aria-label'], h.t('{{product}} API 已連線'));
  popup.props.onOpenChange(true);
  popup = find(WorkspaceAccount(props), 'AccountControl')[0].props.renderControls(null);
  assert.equal(find(popup, 'button')[0].props['aria-expanded'], true);
  assert.equal(find(popup, 'button')[0].props['aria-controls'], popup.props.content.props.id);
  control.props.onAction();
  assert.equal(find(WorkspaceAccount(props), 'AccountControl')[0].props.renderControls(null).props.open, false, 'opening a destination dismisses the account popup');
}
console.log('SIDEBAR_OK: grouped desktop/mobile navigation, section changes, role filtering, unread counts and account disclosure across 3 locales');
