import assert from 'node:assert/strict';
import test from 'node:test';
import { validateCatalog } from './i18n-catalog-validation.mjs';

test('authored translations may rephrase and reorder placeholders without modifying catalogs', () => {
  const source = { '標準作業程序': 'Standard operating procedure', '{{name}} 的 {{count}} 個項目': '{{count}} items for {{name}}', 'API': 'API' };
  const translated = { '標準作業程序': '标准操作流程', '{{name}} 的 {{count}} 個項目': '共 {{count}} 项，负责人：{{name}}', 'API': 'API' };
  const before = JSON.stringify(translated);
  assert.deepEqual(validateCatalog(source, translated, 'zh-CN'), []);
  assert.equal(JSON.stringify(translated), before);
});

test('missing, blank, non-string and obsolete translations fail coverage checks', () => {
  const source = { '缺漏': 'Missing', '空白': 'Blank', '格式': 'Type' };
  const errors = validateCatalog(source, { '空白': '  ', '格式': 7, '舊項目': '旧条目' }, 'zh-CN');
  assert.equal(errors.length, 4);
  for (const reason of ['missing translation', 'empty or non-string', 'obsolete translation key']) {
    assert.ok(errors.some(error => error.includes(reason)));
  }
});

test('lost, renamed, added and repeated interpolation tokens fail validation', () => {
  for (const value of ['欢迎', '欢迎 {{user}}', '{{name}} {{extra}}', '{{name}} {{name}}']) {
    assert.match(validateCatalog({ '歡迎 {{name}}': 'Welcome {{name}}' }, { '歡迎 {{name}}': value }, 'zh-CN')[0], /interpolation mismatch/);
  }
});

test('invalid catalog containers and untranslated English fail validation', () => {
  for (const catalog of [null, undefined, [], 'translation']) assert.match(validateCatalog({}, catalog, 'zh-CN')[0], /expected a translation object/);
  assert.match(validateCatalog({ '登入': 'Login' }, { '登入': '登入' }, 'en', {english: true})[0], /untranslated English/);
});
