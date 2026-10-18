import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const load = (filename, imports, transform = source => source) => {
  const source = transform(fs.readFileSync(path.join(root, filename), 'utf8'));
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const context = { exports: {}, require: name => Object.hasOwn(imports, name) ? imports[name] : require(name), Intl };
  vm.runInNewContext(code, context, { timeout: 1000 });
  return context.exports;
};
const catalogs = {};
const simplified = {};
for (const name of fs.readdirSync(path.join(root, 'frontend/src/i18n/catalogs'))) {
  if (name.endsWith('.en.ts')) catalogs[name] = load(`frontend/src/i18n/catalogs/${name}`, {});
  if (name.endsWith('.zh-CN.json')) simplified[name] = { default: JSON.parse(fs.readFileSync(path.join(root, 'frontend/src/i18n/catalogs', name), 'utf8')) };
}
// Keep the real translator: passing an undefined label must fail this regression.
const i18n = load('frontend/src/i18n/index.ts', {}, source => source
  .replace(/import\.meta\.glob<\{ default: Catalog \}>\('\.\/catalogs\/\*\.en\.ts', \{ eager: true \}\)/, JSON.stringify(catalogs))
  .replace(/import\.meta\.glob<\{ default: Catalog \}>\('\.\/catalogs\/\*\.zh-CN\.json', \{ eager: true \}\)/, JSON.stringify(simplified)));
let store;
let controls;
const container = ({ children }) => React.createElement('div', null, children);
const control = name => props => { (controls[name] ??= []).push(props); return container(props); };
const Form = {
  Item: ({ label, children }) => React.createElement('div', null, label, children),
  useWatch: name => store.getFieldValue(name),
};
const antd = Object.fromEntries(['Alert', 'Button', 'Input', 'InputNumber', 'Space', 'Spin', 'Switch', 'Tag'].map(name => [name, container]));
Object.assign(antd, { Form, Typography: { Text: container }, Segmented: control('Segmented'), Select: control('Select') });
const { AgentModelConfigFields } = load('frontend/src/models/ModelSettings.tsx', {
  antd, '@ant-design/icons': {}, '../api': {}, '../i18n': i18n, './model-settings.css': {},
});
const selection = { provider_id: 'one', model_id: 'model-a', reasoning_effort: 'medium', max_output_tokens: 2048 };
const catalog = {
  default: null,
  providers: ['one', 'two'].map(id => ({ id, name: id, models: [{
    id: 'model-a', name: 'Model A', context_window: 32000, max_output_tokens: 8192, reasoning_efforts: ['low', 'medium'],
  }] })),
};
const setup = (modelMode, model_config, activeCatalog = catalog, agent = null, runtime = 'pi') => {
  const values = { runtime, modelMode, model_config };
  store = {
    getFieldValue: name => (Array.isArray(name) ? name : [name]).reduce((value, key) => value?.[key], values),
    setFieldValue: (name, value) => { values[name] = value; },
  };
  return () => {
    controls = {};
    return renderToStaticMarkup(React.createElement(AgentModelConfigFields, {
      form: store, catalog: activeCatalog, catalogLoading: false, catalogError: '', agent, onRetry() {},
    }));
  };
};
let checks = 0;
for (const locale of ['zh-TW', 'zh-CN', 'en']) {
  i18n.setLocale(locale);
  for (const draft of [{}, undefined, { provider_id: 'one' }, { provider_id: 'one', model_id: 'model-a' },
    { ...selection, reasoning_effort: undefined }, { ...selection, reasoning_effort: 'unknown' },
    { ...selection, max_output_tokens: undefined }, { ...selection, max_output_tokens: 0 }]) {
    const markup = setup('override', draft)();
    assert.ok(markup.includes(i18n.t('請完成此 Agent 的模型設定')));
    assert.ok(!markup.includes('NaN'));
    checks++;
  }
  assert.ok(setup('override', selection)().includes('Model A'));
  assert.ok(setup('inherit', undefined, { ...catalog, default: selection })().includes('Model A'));
  assert.ok(setup('inherit', undefined, catalog, { effective_model_config: selection })().includes('Model A'));
  assert.ok(setup('inherit', undefined)().includes(i18n.t('尚未設定全域預設')));
  const render = setup('inherit', undefined, { ...catalog, default: selection });
  render();
  controls.Segmented[0].onChange('override');
  store.setFieldValue('modelMode', 'override');
  assert.ok(render().includes('Model A'));
  controls.Select[0].onChange('two');
  assert.equal(store.getFieldValue(['model_config', 'model_id']), undefined);
  assert.ok(render().includes(i18n.t('請完成此 Agent 的模型設定')));
  controls.Select[1].onChange('model-a');
  assert.equal(store.getFieldValue(['model_config', 'max_output_tokens']), 4096);
  assert.equal(store.getFieldValue(['model_config', 'reasoning_effort']), undefined);
  assert.ok(render().includes(i18n.t('請完成此 Agent 的模型設定')));
  store.setFieldValue('model_config', { ...store.getFieldValue('model_config'), reasoning_effort: 'low' });
  assert.ok(render().includes('Model A'));
  // Toggling mode preserves a partially entered override instead of overwriting it.
  store.setFieldValue('model_config', { provider_id: 'two' });
  store.setFieldValue('modelMode', 'inherit');
  render();
  controls.Segmented[0].onChange('override');
  assert.equal(store.getFieldValue(['model_config', 'provider_id']), 'two');
  assert.ok(setup('override', {}, catalog, null, 'external')().includes(i18n.t('外部程式使用的模型（選填）')));
  checks += 10;
}
console.log(`Agent model fields: ${checks} render and interaction checks passed across three locales.`);
