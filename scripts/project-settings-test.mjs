import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const ts = require('typescript');
const compile = file => ts.transpileModule(fs.readFileSync(new URL(file, import.meta.url), 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}}).outputText;
function evaluate(file, imports) {
  const module = {exports: {}};
  vm.runInNewContext(compile(file), {module, exports: module.exports, require: name => imports[name] ?? (name.endsWith('.css') ? {} : (() => {throw Error(`Unexpected import ${name}`);})())});
  return module.exports;
}
const {withProjectAccess} = evaluate('../frontend/src/projects/projectPermissions.ts', {});
const original = {work: {role: 'reviewer', scope_ids: ['a', 'b']}, knowledge: {role: 'writer', scope_ids: ['space']}, code: {role: 'reader', scope_ids: ['repo']}};
const plain = value => JSON.parse(JSON.stringify(value));
assert.deepEqual(plain(withProjectAccess(original, 'c', true)), {...original, work: {role: 'reviewer', scope_ids: ['a', 'b', 'c']}});
assert.deepEqual(plain(withProjectAccess(original, 'a', true)), original);
assert.deepEqual(plain(withProjectAccess(original, 'a', false)), {...original, work: {role: 'reviewer', scope_ids: ['b']}});
assert.deepEqual(plain(withProjectAccess({code: original.code}, 'a', true)), {code: original.code, work: {role: 'worker', scope_ids: ['a']}});
assert.deepEqual(plain(withProjectAccess({code: original.code}, 'a', false)), {code: original.code});
assert.deepEqual(original.work.scope_ids, ['a', 'b'], 'input permissions must remain unchanged');

function harness(role = 'admin') {
  const states = [], effects = [], calls = [];
  let cursor = 0, conflict = false;
  const hooks = {useState(initial) {const i = cursor++; if (!(i in states)) states[i] = initial; return [states[i], value => {states[i] = typeof value === 'function' ? value(states[i]) : value;}];}, useEffect: fn => effects.push(fn)};
  const form = {setFieldsValue: values => calls.push(['form', plain(values)])};
  const Form = Object.assign(() => {}, {useForm: () => [form], Item: 'FormItem'});
  const ui = new Proxy({Form, Input: {TextArea: 'TextArea'}, Descriptions: {Item: 'DescriptionItem'}, Modal: {useModal: () => [{confirm: async () => true}, null]}}, {get: (target, key) => target[key] ?? key});
  const project = {id: 'a', key: 'A', name: 'Alpha', description: '', budget_usd: 5};
  const api = {
    async updateProject(id, body) {calls.push(['save', id, plain(body)]); if (conflict) throw Error('stale snapshot'); return {...project, ...body};},
    async get(route) {calls.push(['reload', route]); return {...project, name: 'Remote update'};},
  };
  const {ProjectSettings, ProjectMembers} = (() => {
    const module = {exports: {}};
    const imports = {
      react: hooks, antd: ui, '../api': {api}, '../auth/client': {authApi: {users: async () => {calls.push(['users']); return {users: []};}}},
      '../auth/AuthContext': {useAuth: () => ({session: {user: {role}}})}, '../auth/settingsNavigation': {openOrganizationSettings() {}},
      '../i18n': {useI18n: () => ({t: text => text}), useLocalizedForm() {}},
      '../shared/useNavigationState': {useNavigationState: () => ['general', () => {}]}, './projectPermissions': {withProjectAccess},
      'react/jsx-runtime': {jsx: (type, props) => ({type, props}), jsxs: (type, props) => ({type, props})},
    };
    vm.runInNewContext(compile('../frontend/src/projects/ProjectSettings.tsx') + '\nexports.ProjectMembers = ProjectMembers;', {module, exports: module.exports, Error, require: name => imports[name] ?? {}});
    return module.exports;
  })();
  const props = {project, participants: [], canManage: role === 'admin', onUpdated: value => calls.push(['updated', value.name]), onParticipantsChanged() {}, onOpenAgents() {}, onCreateCompanions() {}};
  return {calls, Form, render() {cursor = 0; return ProjectSettings(props);}, members() {cursor = 0; return ProjectMembers({projectId: 'a', participants: [], isAdmin: role === 'admin', onChanged() {}, onOpenAgents() {}});}, runEffects: async () => {for (const effect of effects.splice(0)) effect(); await Promise.resolve();}, conflict() {conflict = true;}};
}
function find(tree, type) {
  if (!tree || typeof tree !== 'object') return [];
  if (Array.isArray(tree)) return tree.flatMap(node => find(node, type));
  return [...(tree.type === type ? [tree] : []), ...find(tree.props?.children, type), ...(tree.props?.items ?? []).flatMap(item => find(item.children, type))];
}
const h = harness();
await find(h.render(), h.Form)[0].props.onFinish({name: ' Edited ', description: 'New description', budget_usd: 10});
assert.deepEqual(h.calls.find(row => row[0] === 'save'), ['save', 'a', {name: 'Edited', description: 'New description', budget_usd: 10, expected: {name: 'Alpha', description: '', budget_usd: 5}}]);
await find(h.render(), h.Form)[0].props.onFinish({name: 'Second', description: '', budget_usd: 12});
assert.equal(h.calls.filter(row => row[0] === 'save')[1][2].expected.name, 'Edited', 'subsequent saves use the accepted snapshot');
h.conflict();
await find(h.render(), h.Form)[0].props.onFinish({name: 'Stale', description: '', budget_usd: 15});
assert.equal(h.calls.filter(row => row[0] === 'updated').length, 2, 'a conflict never replaces current project state');
const error = find(h.render(), 'Alert').find(node => node.props.type === 'error');
assert.equal(error.props.message, 'stale snapshot');
await error.props.action.props.onClick();
await new Promise(resolve => setTimeout(resolve, 0));
assert.equal(h.calls.at(-1)[1], 'Remote update');
const member = harness('member');
assert.equal(find(member.render(), member.Form)[0].props.disabled, true);
assert.ok(!find(member.render(), 'Button').some(node => node.props.htmlType === 'submit'));
member.members(); await member.runEffects();
assert.ok(!member.calls.some(row => row[0] === 'users'), 'non-admins must not fetch the organization directory');
console.log('PROJECT_SETTINGS_OK: scoped grants, preserved permissions, immutable inputs, snapshot saves, conflict reload and non-admin restrictions');
