import assert from 'node:assert/strict';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
process.chdir(frontendRoot);

function check(condition, message) {
  assert.ok(condition, message);
}

function decodeHtmlText(value) {
  return value.replace(/&(?:#x([\da-f]+)|#(\d+)|lt|gt|amp|quot|#39);/gi, (entity, hex, decimal) => {
    if (hex) return String.fromCodePoint(Number.parseInt(hex, 16));
    if (decimal) return String.fromCodePoint(Number.parseInt(decimal, 10));
    return { '&lt;': '<', '&gt;': '>', '&amp;': '&', '&quot;': '"', '&#39;': "'" }[entity.toLowerCase()] ?? entity;
  });
}

let server;
try {
  server = await createServer({
    configLoader: 'runner',
    configFile: resolve(frontendRoot, 'vite.config.ts'),
    root: frontendRoot,
    server: { middlewareMode: true, hmr: false, watch: null },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true, include: [] },
    logLevel: 'error',
  });

  const [{ MarkdownContent, MarkdownPreview }, i18n] = await Promise.all([
    server.ssrLoadModule('/src/shared/MarkdownContent.tsx'),
    server.ssrLoadModule('/src/i18n/index.ts'),
  ]);
  check(typeof MarkdownContent === 'function', 'MarkdownContent must be a named component export.');

  const render = (content) => renderToStaticMarkup(createElement(MarkdownContent, { content }));
  const codeSource = 'const marker = "<script>alert(1)</script> & remains";';
  const document = [
    '# Release notes',
    '',
    '## Highlights',
    '',
    '**safe bold** and *clear emphasis*',
    '',
    '| Area | State |',
    '| --- | --- |',
    '| Work | Ready |',
    '',
    '- [ ] Review result',
    '- [x] Publish notes',
    '',
    '```text',
    codeSource,
    '```',
    '',
    '<script>globalThis.markdownExecuted = true</script>',
    '<img src="x" onerror="globalThis.markdownExecuted = true">',
    '',
    '[external](https://example.com/docs)',
    '[internal](#release-notes)',
    '[javascript](javascript:alert%281%29)',
    '[data](data:text/html,blocked)',
  ].join('\n');

  i18n.setLocale('zh-TW');
  const markup = render(document);
  check(markup.includes('<h1>Release notes</h1>'), 'Top-level heading must render as an h1.');
  check(markup.includes('<h2>Highlights</h2>'), 'Second-level heading must render as an h2.');
  check(markup.includes('<strong>safe bold</strong>'), 'Bold text must render as strong content.');
  check(markup.includes('<em>clear emphasis</em>'), 'Emphasis must render as an em element.');
  check(markup.includes('<table>') && markup.includes('<th>Area</th>') && markup.includes('<td>Work</td>'), 'GFM tables must render as semantic table elements.');

  const checkboxes = [...markup.matchAll(/<input\b[^>]*>/g)].map(([tag]) => tag);
  check(checkboxes.length === 2, 'GFM task lists must render two checkbox inputs.');
  check(checkboxes.every((tag) => /\bdisabled(?:=|>)/.test(tag)), 'Task-list checkboxes must be disabled.');
  check(!/\bchecked(?:=|>)/.test(checkboxes[0]) && /\bchecked(?:=|>)/.test(checkboxes[1]), 'Task-list checkbox states must match the source.');

  const codeBlock = markup.match(/<pre><code(?:\s[^>]*)?>([\s\S]*?)<\/code><\/pre>/);
  check(Boolean(codeBlock), 'Fenced code must render inside pre and code elements.');
  check(codeBlock[1].includes('&lt;script&gt;'), 'Fenced code must escape markup characters.');
  const renderedCode = decodeHtmlText(codeBlock[1]);
  check(renderedCode === `${codeSource}\n`, 'Fenced code must preserve its exact source, including the Markdown code-block line ending.');

  check(!markup.includes('<script>') && !markup.includes('onerror='), 'Raw HTML must not become executable markup.');
  check(!markup.includes('href="javascript:') && !markup.includes('href="data:'), 'Unsafe URL schemes must not become links.');
  const externalLink = markup.match(/<a\b[^>]*href="https:\/\/example\.com\/docs"[^>]*>/)?.[0];
  check(Boolean(externalLink), 'External HTTPS links must render as anchors.');
  check(externalLink.includes('target="_blank"') && externalLink.includes('rel="noopener noreferrer"'), 'External links must open safely in a new tab.');
  const internalLink = markup.match(/<a\b[^>]*href="#release-notes"[^>]*>/)?.[0];
  check(Boolean(internalLink), 'Internal anchors must render as links.');
  check(!internalLink.includes('target="_blank"'), 'Internal anchors must stay in the current tab.');

  const tableMarkdown = '| Key | Value |\n| --- | --- |\n| one | two |';
  const tableLabels = [
    ['zh-TW', '表格內容'],
    ['zh-CN', '表格内容'],
    ['en', 'Table content'],
  ];
  for (const [locale, label] of tableLabels) {
    i18n.setLocale(locale);
    const localizedMarkup = render(tableMarkdown);
    const region = localizedMarkup.match(/<div\b[^>]*class="markdown-table-scroll"[^>]*>/)?.[0];
    check(Boolean(region), `${locale} table wrapper must render.`);
    check(region.includes('role="region"') && region.includes(`aria-label="${label}"`), `${locale} table wrapper must have its localized accessible label.`);
  }

  i18n.setLocale('en');
  const authoredChinese = render('## 專案狀態\n\n**需要審查**');
  check(authoredChinese.includes('<h2>專案狀態</h2>') && authoredChinese.includes('<strong>需要審查</strong>'), 'Changing interface locale must not translate user-authored content.');

  const preview = renderToStaticMarkup(createElement(MarkdownPreview, {
    content: '# Title\n\n## Preview\n\n**Readable summary**\n\n- [ ] Task\n\n[Guide](https://example.com/)\n\n![Diagram](https://example.com/diagram.png)',
  }));
  check(preview.includes('Title') && preview.includes('Preview') && preview.includes('Readable summary') && preview.includes('Guide') && preview.includes('Diagram'), 'Search previews must retain text, link labels, and image descriptions.');
  check(!preview.includes('#') && !preview.includes('**') && !preview.includes('[ ]'), 'Search previews must hide Markdown formatting syntax.');
  check(!/<(?:a|h[1-6]|img|input|p|ul|li)\b/.test(preview), 'Search previews inside buttons must not add interactive controls, images, or block elements.');

  console.log('Markdown SSR regression checks passed.');
} catch (error) {
  console.error(`Markdown SSR regression checks failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
  process.exitCode = 1;
} finally {
  if (server) await server.close();
}
