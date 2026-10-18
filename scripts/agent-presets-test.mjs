import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const ts = require('typescript');
function load(filename, imports = {}, transform = source => source) {
  const source = transform(fs.readFileSync(path.join(root, filename), 'utf8'));
  const code = ts.transpileModule(source, { fileName: filename, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const context = { exports: {}, require: name => Object.hasOwn(imports, name) ? imports[name] : require(name), Intl };
  vm.runInNewContext(code, context, { timeout: 1000 });
  return context.exports;
}
const english = {}, simplified = {};
for (const name of fs.readdirSync(path.join(root, 'frontend/src/i18n/catalogs'))) {
  if (name.endsWith('.en.ts')) english[name] = load(`frontend/src/i18n/catalogs/${name}`);
  if (name.endsWith('.zh-CN.json')) simplified[name] = { default: JSON.parse(fs.readFileSync(path.join(root, 'frontend/src/i18n/catalogs', name), 'utf8')) };
}
const i18n = load('frontend/src/i18n/index.ts', {}, source => source
  .replace(/import\.meta\.glob<\{ default: Catalog \}>\('\.\/catalogs\/\*\.en\.ts', \{ eager: true \}\)/, JSON.stringify(english))
  .replace(/import\.meta\.glob<\{ default: Catalog \}>\('\.\/catalogs\/\*\.zh-CN\.json', \{ eager: true \}\)/, JSON.stringify(simplified)));
const helpers = load('frontend/src/agents/templatePresets.ts', { '../i18n': i18n });
const preset = key => ({ id: `preset-${key}`, key: `builtin-${key}`, builtin_key: key, name: 'Canonical name', description: 'Canonical description', version: 1,
  definition: { role: key === 'reviewer' ? 'reviewer' : 'worker', capabilities: [key], instructions: 'Canonical instructions', model_config: null, tool_connection_ids: [], sandbox_profile_id: null, limits: { max_turns: 20, timeout_seconds: 600 } } });
let checks = 0;
for (const locale of ['zh-TW', 'zh-CN', 'en']) {
  i18n.setLocale(locale);
  for (const key of ['pm', 'pg', 'sa', 'sd', 'qa', 'reviewer']) {
    const template = preset(key), original = JSON.stringify(template);
    const localized = helpers.localizeAgentTemplate(template);
    assert.ok(localized.name !== template.name);
    assert.ok(localized.description !== template.description);
    assert.ok(localized.definition.instructions.includes(locale === 'en' ? 'Deliverables:' : '交付：'));
    assert.ok(localized.definition.instructions.includes(locale === 'en' ? 'Rules:' : '規則：') || locale === 'zh-CN' && localized.definition.instructions.includes('规则：'));
    assert.equal(/[\u3400-\u9fff]/u.test(localized.definition.instructions), locale !== 'en');
    const values = helpers.agentTemplateFormValues(template);
    assert.equal(values.template_id, template.id);
    assert.equal(values.modelMode, 'inherit');
    assert.equal(values.role, key === 'reviewer' ? 'reviewer' : 'worker');
    values.capabilities.push('user-edit');
    values.execution_config.limits.max_turns = 31;
    values.execution_config.instructions = 'Custom instruction';
    assert.equal(JSON.stringify(template), original, 'Applying/editing a template must not change its immutable definition');
    checks++;
  }
  for (const builtin_key of [null, undefined, 'future-preset']) {
    const custom = { ...preset('pm'), builtin_key, name: '使用者自訂 PM', definition: { ...preset('pm').definition, instructions: 'User-authored instruction 保留原文' } };
    assert.equal(helpers.localizeAgentTemplate(custom), custom);
    assert.equal(helpers.agentTemplateFormValues(custom).execution_config.instructions, custom.definition.instructions);
    checks++;
  }
}

// Run the actual form handler with a controlled form, including name protection.
const source = fs.readFileSync(path.join(root, 'frontend/src/App.tsx'), 'utf8');
const tree = ts.createSourceFile('App.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let handler;
function visit(node) { if (ts.isFunctionDeclaration(node) && node.name?.text === 'applyTemplateToAgentForm') handler = node.getText(tree); ts.forEachChild(node, visit); }
visit(tree);
assert.ok(handler);
const fields = {};
const context = vm.createContext({ ...helpers, editingAgent: null, agentTemplateName: { current: '' }, agentForm: {
  getFieldValue: name => fields[name], setFieldValue: (name, value) => { fields[name] = value; }, setFieldsValue: values => Object.assign(fields, values),
} });
vm.runInContext(ts.transpileModule(handler, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context);
i18n.setLocale('zh-TW');
context.applyTemplateToAgentForm(preset('pm'));
assert.equal(fields.name, 'PM · 專案經理');
context.applyTemplateToAgentForm(preset('pg'));
assert.equal(fields.name, 'PG · 程式開發');
assert.equal(fields.template_id, 'preset-pg');
fields.name = 'My specialist';
context.applyTemplateToAgentForm(preset('sa'));
assert.equal(fields.name, 'My specialist', 'Never overwrite a manually entered name');
fields.execution_config.instructions = 'Manually edited draft';
i18n.setLocale('en');
assert.equal(fields.execution_config.instructions, 'Manually edited draft', 'Changing locale must not replace a draft');
context.editingAgent = { runtime: 'external' };
context.applyTemplateToAgentForm(preset('sd'));
assert.equal(fields.runtime, 'external', 'Applying to an existing agent must preserve its runtime');
assert.equal(fields.name, 'My specialist');
checks++;
console.log(`AGENT_PRESETS_OK: ${checks} localization, immutable-definition, and form scenarios`);
