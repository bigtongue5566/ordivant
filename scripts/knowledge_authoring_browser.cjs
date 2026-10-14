// Run with: node scripts/knowledge_authoring_browser.cjs
// Uses the isolated synthetic QA session and never connects outside the fixed local host.
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const fsSync = require('node:fs');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(path.resolve('.cache/browser-qa/node_modules/playwright'));

const baseExpected = 'http://127.0.0.1:8096';
const qaDirectory = path.resolve('.cache/p0-p1-qa');
const screenshotsDirectory = path.join(qaDirectory, 'screenshots');
const contextPath = path.resolve('.cache/collaboration-qa/context.json');
const chromeExecutable = [
  path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
  path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe'),
].find(candidate => fsSync.existsSync(candidate));

const locales = [
  {
    key: 'zh-TW', htmlLang: 'zh-Hant', label: '繁體中文',
    newDocument: '新增文件', createDocument: '建立文件', templateField: '文件範本',
    templateName: '產品需求文件 (PRD)', bodyHeading: '產品需求', titleSuffix: '驗收',
    documentTitle: '文件標題', bodyField: '正文（Markdown）', publish: '發佈新版本',
    changeSummary: '變更摘要', compare: '比較版本', diffDialog: '比較不可變版本',
    closeDialog: '關閉比較', restore: '還原版本', restoreConfirm: '建立還原版本',
    parentField: '上層文件', structure: '文件結構', saveStructure: '儲存結構',
    archiveField: '封存狀態', showArchived: '顯示已封存', archived: '已封存',
    addComment: '新增留言', reply: '回覆', sendReply: '送出回覆',
    resolve: '標記已解決', resolved: '已解決', preview: '預覽',
    bold: '粗體', boldSource: '粗體文字', table: '插入表格', tableHeader: '欄位 1',
  },
  {
    key: 'zh-CN', htmlLang: 'zh-Hans', label: '简体中文',
    newDocument: '添加文档', createDocument: '创建文档', templateField: '文档范本',
    templateName: '产品需求文档 (PRD)', bodyHeading: '产品需求', titleSuffix: '验收',
    documentTitle: '文档标题', bodyField: '正文（Markdown）', publish: '发布新版本',
    changeSummary: '变更摘要', compare: '比较版本', diffDialog: '比较不可变版本',
    closeDialog: '关闭比较', restore: '还原版本', restoreConfirm: '创建还原版本',
    parentField: '上层文档', structure: '文档结构', saveStructure: '保存结构',
    archiveField: '封存状态', showArchived: '显示已封存', archived: '已封存',
    addComment: '添加留言', reply: '回复', sendReply: '送出回复',
    resolve: '标记已解决', resolved: '已解决', preview: '预览',
    bold: '粗体', boldSource: '粗体文本', table: '插入表格', tableHeader: '字段 1',
  },
  {
    key: 'en', htmlLang: 'en', label: 'English',
    newDocument: 'Add document', createDocument: 'Create document', templateField: 'Document template',
    templateName: 'Product requirements (PRD)', bodyHeading: 'Product requirements', titleSuffix: 'QA',
    documentTitle: 'Document title', bodyField: 'Body (Markdown)', publish: 'Publish new version',
    changeSummary: 'Change summary', compare: 'Compare versions', diffDialog: 'Compare immutable versions',
    closeDialog: 'Close comparison', restore: 'Restore version', restoreConfirm: 'Create restored version',
    parentField: 'Parent document', structure: 'Document structure', saveStructure: 'Save structure',
    archiveField: 'Archive status', showArchived: 'Show archived', archived: 'Archived',
    addComment: 'Add comment', reply: 'Reply', sendReply: 'Send reply',
    resolve: 'Mark resolved', resolved: 'Resolved', preview: 'Preview',
    bold: 'Bold', boldSource: 'bold text', table: 'Insert table', tableHeader: 'Column 1',
  },
];

const report = { status: 'failed', target: baseExpected, checks: {}, screenshots: [], browserErrors: 0, externalRequestsBlocked: 0 };
const sensitiveValues = [];
const browserErrors = [];
let currentStep = 'initialize';
let externalRequestsBlocked = 0;
let activePage = null;

function isFixedLocalTarget(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return url.hostname === '127.0.0.1' && url.port === '8096' && ['http:', 'ws:'].includes(url.protocol);
  } catch {
    return false;
  }
}

function check(name, condition) {
  currentStep = name;
  report.checks[name] = Boolean(condition);
  assert.ok(condition, name);
}

function safeError(error) {
  let message = error instanceof Error ? error.message : String(error);
  message = message.split('\n')[0]
    .replace(/https?:\/\/[^\s]+/g, '[url]')
    .replace(/(cookie|csrf|token|password|authorization)\s*[:=]\s*[^\s,;]+/gi, '$1=[redacted]')
    .replace(/\b[a-f0-9]{8}-[a-f0-9-]{27,}\b/gi, '[id]')
    .replace(/locator\([^)]*\)/g, 'locator');
  for (const value of sensitiveValues) if (value) message = message.split(value).join('[redacted]');
  return message.slice(0, 320);
}

async function clickVisible(locator, name) {
  currentStep = name;
  await locator.waitFor({ state: 'visible', timeout: 5000 });
  await locator.scrollIntoViewIfNeeded();
  assert.ok(await locator.isEnabled(), `${name}_enabled`);
  await locator.click({ trial: true, timeout: 5000 });
  const box = await locator.boundingBox();
  const viewport = locator.page().viewportSize();
  check(`${name}_in_view`, Boolean(box && viewport && box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1));
  const receivesMouse = await locator.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(hit && (element === hit || element.contains(hit)));
  });
  check(`${name}_receives_mouse`, receivesMouse);
  await locator.click({ timeout: 5000 });
}

async function chooseVisibleOption(page, select, text, name) {
  await clickVisible(select, `${name}_select`);
  const combobox = select.locator('input[role="combobox"]').last();
  const expanded = await combobox.getAttribute('aria-expanded');
  const listboxId = await combobox.getAttribute('aria-controls');
  check(`${name}_combobox_expanded`, expanded === 'true');
  assert.ok(listboxId, `${name}_listbox_id_present`);
  const listbox = page.locator(`[id="${listboxId}"]`);
  const popup = page.locator('.ant-select-dropdown').filter({ has: listbox }).last();
  await popup.waitFor({ state: 'visible' });
  check(`${name}_popup_visible`, await popup.isVisible());
  const option = popup.locator('.ant-select-item-option').filter({ hasText: text }).first();
  await option.waitFor({ state: 'visible' });
  await option.click({ trial: true, timeout: 5000 });
  const box = await option.boundingBox();
  const viewport = page.viewportSize();
  check(`${name}_option_in_view`, Boolean(box && viewport && box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1));
  const receivesMouse = await option.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(hit && (element === hit || element.contains(hit)));
  });
  check(`${name}_option_receives_mouse`, receivesMouse);
  await option.click({ timeout: 5000 });
  await popup.waitFor({ state: 'hidden' });
}

async function changeLanguage(page, locale) {
  await chooseVisibleOption(page, page.locator('.language-control .ant-select'), locale.label, `language_${locale.key}`);
  await page.waitForFunction(expected => document.documentElement.lang === expected, locale.htmlLang);
  check(`language_${locale.key}_applied`, true);
}

async function waitForSelectionAgreement(page, title, name) {
  currentStep = name;
  await page.waitForFunction(expected => {
    const activeTitle = document.querySelector('.knowledge-document-item.knowledge-document-active .document-item-top strong')?.textContent?.trim();
    const readerTitle = document.querySelector('.knowledge-reader .reader-document-head h3')?.textContent?.trim();
    return activeTitle === expected && readerTitle === expected;
  }, title, { timeout: 20000 });
  check(`${name}_sidebar_and_reader_match`, true);
}

async function waitForTransientMessages(page, name) {
  currentStep = name;
  await page.waitForFunction(() => !document.querySelector('.ant-message-notice'), null, { timeout: 10000 });
  check(name, true);
}

async function checkDocumentListBounds(page, name) {
  const bounds = await page.evaluate(() => {
    const panel = document.querySelector('.knowledge-document-list');
    if (!panel) return { rowCount: 0, rowsFit: false, longTitleCount: 0, longTitlesFit: false };
    const panelRect = panel.getBoundingClientRect();
    const rows = Array.from(panel.querySelectorAll('.knowledge-document-item'));
    const rectWithin = (inner, outer) => inner.left >= outer.left - 1 && inner.right <= outer.right + 1;
    const longTitles = rows.map(row => ({ row, title: row.querySelector('.document-item-top > strong') }))
      .filter(item => item.title && (item.title.textContent || '').trim().length >= 32);
    return {
      rowCount: rows.length,
      rowsFit: rows.every(row => rectWithin(row.getBoundingClientRect(), panelRect)),
      longTitleCount: longTitles.length,
      longTitlesFit: longTitles.every(({ row, title }) => {
        const rect = title.getBoundingClientRect();
        const rowRect = row.getBoundingClientRect();
        const style = getComputedStyle(title);
        return rectWithin(rect, rowRect) && rectWithin(rect, panelRect) && style.minWidth === '0px'
          && style.overflowX === 'hidden' && style.textOverflow === 'ellipsis';
      }),
    };
  });
  check(`${name}_rows_within_list_panel`, bounds.rowCount > 0 && bounds.rowsFit);
  check(`${name}_long_titles_clipped_within_list_panel`, bounds.longTitleCount > 0 && bounds.longTitlesFit);
}

async function readJson(page, route) {
  const result = await page.evaluate(async url => {
    try {
      const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) return { ok: false };
      return { ok: true, value: await response.json() };
    } catch {
      return { ok: false };
    }
  }, route);
  assert.ok(result?.ok, 'synthetic scoped Knowledge metadata unavailable');
  return result.value;
}

function formItem(container, label) {
  return container.locator('.ant-form-item').filter({ hasText: label }).first();
}

async function openModal(page, buttonText, step) {
  const button = page.locator('button:visible').filter({ hasText: buttonText }).last();
  check(`${step}_visible_action_text_matches`, (await button.innerText().catch(() => '')).trim() === buttonText);
  await clickVisible(button, step);
  const modal = page.locator('.ant-modal:visible').last();
  await modal.waitFor({ state: 'visible' });
  return modal;
}

async function capture(page, locale) {
  const filename = `knowledge-authoring-${locale.key}.png`;
  await page.screenshot({ path: path.join(screenshotsDirectory, filename), fullPage: false });
  const relativePath = `screenshots/${filename}`;
  if (!report.screenshots.includes(relativePath)) report.screenshots.push(relativePath);
}

async function runLocale(page, locale, qaContext, index) {
  if (await page.locator('html').getAttribute('lang') !== locale.htmlLang) await changeLanguage(page, locale);
  const space = (await readJson(page, '/knowledge-api/spaces')).find(item => item.id === qaContext.knowledge.space_id);
  assert.ok(space?.key, 'synthetic Knowledge space fixture unavailable');
  await chooseVisibleOption(page, page.locator('.product-scope-select'), space.key, `knowledge_space_${locale.key}`);

  const fixtureDocuments = await readJson(page, `/knowledge-api/documents?space_id=${encodeURIComponent(space.id)}`);
  const fixture = fixtureDocuments.find(item => item.id === qaContext.knowledge.document_id);
  assert.ok(fixture?.title, 'synthetic parent document fixture unavailable');
  const parentDocument = fixtureDocuments.find(item => item.id !== fixture.id && !item.archived);
  assert.ok(parentDocument?.title, 'synthetic active parent document unavailable');

  const marker = randomUUID().slice(0, 8);
  const title = `${locale.templateName} ${locale.titleSuffix} ${marker}`;
  const createModal = await openModal(page, locale.newDocument, `open_create_${locale.key}`);
  const templateItem = formItem(createModal, locale.templateField);
  await chooseVisibleOption(page, templateItem.locator('.ant-select'), locale.templateName, `builtin_template_${locale.key}`);
  const titleInput = formItem(createModal, locale.documentTitle).locator('input').first();
  const bodyInput = formItem(createModal, locale.bodyField).locator('textarea').first();
  const selectedBody = await bodyInput.inputValue();
  check(`builtin_template_${locale.key}_localized_name_and_body`, selectedBody.includes(locale.bodyHeading) && (locale.key === 'en' ? !/[\u3400-\u9fff]/u.test(selectedBody) : /[\u3400-\u9fff]/u.test(title)));
  await titleInput.fill(title);
  check(`document_title_${locale.key}_uses_localized_template`, (await titleInput.inputValue()).startsWith(locale.templateName));
  const [createResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/knowledge-api/documents', { timeout: 15000 }),
    clickVisible(createModal.getByRole('button', { name: locale.createDocument, exact: true }), `submit_create_${locale.key}`),
  ]);
  check(`document_create_${locale.key}_succeeded`, createResponse.status() === 201);
  const createdDocumentId = (await createResponse.json()).document.id;
  await createModal.waitFor({ state: 'hidden' });

  const documentItem = page.locator('.knowledge-document-item').filter({ hasText: title }).first();
  await documentItem.waitFor({ state: 'visible', timeout: 15000 });
  await clickVisible(documentItem, `open_created_document_${locale.key}`);
  await waitForSelectionAgreement(page, title, `initial_selection_${locale.key}`);
  await checkDocumentListBounds(page, `document_list_${locale.key}`);
  const editor = page.locator('.knowledge-reader .collab-codemirror .cm-content');
  await editor.waitFor({ state: 'visible', timeout: 15000 });
  await page.locator('.knowledge-reader .collab-connection-live').waitFor({ state: 'visible', timeout: 20000 });
  await page.locator('.knowledge-reader .collab-save-ok').waitFor({ state: 'visible', timeout: 20000 });

  await clickVisible(editor, `focus_markdown_${locale.key}`);
  await page.keyboard.press('Control+End');
  await clickVisible(page.locator('.knowledge-markdown-tools').getByRole('button', { name: locale.bold, exact: true }), `insert_bold_${locale.key}`);
  await page.waitForFunction(expected => document.querySelector('.knowledge-reader .collab-codemirror .cm-content')?.innerText.includes(expected), `**${locale.boldSource}**`);
  await clickVisible(page.locator('.knowledge-markdown-tools').getByRole('button', { name: locale.table, exact: true }), `insert_table_${locale.key}`);
  const tableMarkdown = locale.key === 'en' ? '| Column 1 |' : locale.key === 'zh-CN' ? '| 字段 1 |' : '| 欄位 1 |';
  await page.waitForFunction(expected => document.querySelector('.knowledge-reader .collab-codemirror .cm-content')?.innerText.includes(expected), tableMarkdown);
  const canonicalMarkdown = await editor.innerText();
  check(`canonical_markdown_${locale.key}_retains_source_syntax`, canonicalMarkdown.includes(`**${locale.boldSource}**`) && canonicalMarkdown.includes(tableMarkdown));
  await page.locator('.knowledge-reader .collab-save-ok').waitFor({ state: 'visible', timeout: 30000 });

  const previewToggle = page.locator('.knowledge-reader .collab-toolbar .ant-segmented-item').filter({ hasText: locale.preview }).first();
  await clickVisible(previewToggle, `switch_preview_${locale.key}`);
  const preview = page.locator('.knowledge-reader .collab-preview');
  await preview.waitFor({ state: 'visible' });
  const boldPreview = preview.locator('strong').filter({ hasText: locale.boldSource }).first();
  const tablePreview = preview.locator('table th').filter({ hasText: locale.tableHeader }).first();
  await boldPreview.waitFor({ state: 'visible' });
  await tablePreview.waitFor({ state: 'visible' });
  check(`markdown_preview_${locale.key}_renders_bold`, await boldPreview.isVisible());
  check(`markdown_preview_${locale.key}_renders_table`, await tablePreview.isVisible());
  await clickVisible(page.locator('.knowledge-reader .collab-toolbar .ant-segmented-item').filter({ hasText: locale.key === 'en' ? 'Edit' : locale.key === 'zh-CN' ? '编辑' : '編輯' }).first(), `return_to_edit_${locale.key}`);

  const commentMarker = `Browser QA comment ${marker}`;
  const composer = page.locator('.knowledge-comment-composer');
  await composer.locator('textarea').fill(commentMarker);
  const [commentResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'POST' && /\/knowledge-api\/documents\/[^/]+\/comments$/.test(new URL(response.url()).pathname), { timeout: 12000 }),
    clickVisible(composer.getByRole('button', { name: locale.addComment, exact: true }), `add_comment_${locale.key}`),
  ]);
  check(`comment_${locale.key}_created`, commentResponse.status() === 201);
  const thread = page.locator('.knowledge-comment-thread').filter({ hasText: commentMarker }).first();
  await thread.waitFor({ state: 'visible' });
  await clickVisible(thread.getByRole('button', { name: locale.reply, exact: true }), `reply_to_comment_${locale.key}`);
  const replyMarker = `Browser QA reply ${marker}`;
  await composer.locator('textarea').fill(replyMarker);
  const [replyResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'POST' && /\/knowledge-api\/documents\/[^/]+\/comments$/.test(new URL(response.url()).pathname), { timeout: 12000 }),
    clickVisible(composer.getByRole('button', { name: locale.sendReply, exact: true }), `submit_reply_${locale.key}`),
  ]);
  check(`reply_${locale.key}_created`, replyResponse.status() === 201);
  await thread.getByText(replyMarker, { exact: true }).waitFor({ state: 'visible' });
  const [resolveResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'PATCH' && /\/knowledge-api\/document-comments\/[^/]+$/.test(new URL(response.url()).pathname), { timeout: 12000 }),
    clickVisible(thread.getByRole('button', { name: locale.resolve, exact: true }), `resolve_comment_${locale.key}`),
  ]);
  check(`comment_${locale.key}_resolve_request_succeeded`, resolveResponse.ok());
  await thread.getByText(locale.resolved, { exact: true }).waitFor({ state: 'visible', timeout: 10000 });
  check(`comment_${locale.key}_resolved`, true);

  const publishButton = page.getByRole('button', { name: locale.publish, exact: true });
  await page.locator('.knowledge-reader .collab-save-ok').waitFor({ state: 'visible', timeout: 30000 });
  const publishModal = await openModal(page, locale.publish, `open_publish_${locale.key}`);
  await formItem(publishModal, locale.changeSummary).locator('input').first().fill(`Browser acceptance ${marker}`);
  const [publishResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/draft/publish'), { timeout: 15000 }),
    clickVisible(publishModal.getByRole('button', { name: locale.publish, exact: true }), `submit_publish_${locale.key}`),
  ]);
  check(`publish_${locale.key}_created_immutable_version`, publishResponse.status() === 201);
  await publishModal.waitFor({ state: 'hidden' });
  await page.locator('.version-history-current').filter({ hasText: 'v2' }).waitFor({ state: 'visible', timeout: 15000 });

  const [diffResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'GET' && new URL(response.url()).pathname.endsWith('/diff'), { timeout: 12000 }),
    clickVisible(page.getByRole('button', { name: locale.compare, exact: true }), `compare_versions_${locale.key}`),
  ]);
  check(`diff_${locale.key}_loaded`, diffResponse.ok());
  const diffModal = page.locator('.ant-modal:visible').last();
  await diffModal.getByText(locale.diffDialog, { exact: true }).waitFor({ state: 'visible' });
  const diffText = await diffModal.locator('.knowledge-diff').innerText();
  check(`diff_${locale.key}_contains_markdown_changes`, diffText.includes(locale.boldSource) && diffText.includes(locale.tableHeader));
  await clickVisible(diffModal.getByRole('button', { name: locale.closeDialog, exact: true }), `close_diff_${locale.key}`);

  const oldVersion = page.locator('.version-history-row').filter({ hasText: 'v1' }).first();
  await clickVisible(oldVersion, `select_old_version_${locale.key}`);
  const restoreButton = page.locator('button:visible').filter({ hasText: locale.restore }).last();
  check(`open_restore_${locale.key}_visible_action_text_matches`, (await restoreButton.innerText().catch(() => '')).trim() === locale.restore);
  await clickVisible(restoreButton, `open_restore_${locale.key}`);
  const confirm = page.locator('.ant-modal-confirm:visible').last();
  const [restoreResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/restore'), { timeout: 15000 }),
    clickVisible(confirm.getByRole('button', { name: locale.restoreConfirm, exact: true }), `confirm_restore_${locale.key}`),
  ]);
  check(`restore_${locale.key}_created_new_version`, restoreResponse.status() === 201);
  await confirm.waitFor({ state: 'hidden', timeout: 30000 });

  const structureButton = page.getByRole('button', { name: locale.structure, exact: true });
  await clickVisible(structureButton, `open_structure_${locale.key}`);
  const structureModal = page.locator('.ant-modal:visible').last();
  await chooseVisibleOption(page, formItem(structureModal, locale.parentField).locator('.ant-select'), parentDocument.title, `parent_document_${locale.key}`);
  const archiveSwitch = formItem(structureModal, locale.archiveField).locator('.ant-switch');
  await clickVisible(archiveSwitch, `archive_switch_${locale.key}`);
  check(`archive_${locale.key}_switch_enabled`, await archiveSwitch.evaluate(element => element.classList.contains('ant-switch-checked')));
  const [organizationResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'PATCH' && new URL(response.url()).pathname.endsWith('/organization'), { timeout: 12000 }),
    clickVisible(structureModal.getByRole('button', { name: locale.saveStructure, exact: true }), `save_structure_${locale.key}`),
  ]);
  check(`organization_${locale.key}_parent_and_archive_saved`, organizationResponse.ok());
  await structureModal.waitFor({ state: 'hidden' });

  const archivedToggle = page.locator('.knowledge-archive-toggle .ant-switch');
  if (!(await archivedToggle.evaluate(element => element.classList.contains('ant-switch-checked')))) {
    await clickVisible(archivedToggle, `show_archived_${locale.key}`);
  }
  const archivedItem = page.locator('.knowledge-document-item').filter({ hasText: title }).first();
  await archivedItem.waitFor({ state: 'visible', timeout: 15000 });
  check(`archive_${locale.key}_visible_in_archived_list`, await archivedItem.getByText(locale.archived, { exact: true }).isVisible());
  await clickVisible(archivedItem, `select_archived_document_${locale.key}`);
  await waitForSelectionAgreement(page, title, `archived_selection_${locale.key}`);
  await checkDocumentListBounds(page, `archived_document_list_${locale.key}`);
  await waitForTransientMessages(page, `messages_hidden_before_capture_${locale.key}`);

  await capture(page, locale);
  return { id: createdDocumentId, title, bodyHeading: locale.bodyHeading, otherId: parentDocument.id, otherTitle: parentDocument.title };
}

async function runSelectionRaceChecks(page, target) {
  const targetRow = page.locator('.knowledge-document-item').filter({ hasText: target.title }).first();
  const otherRow = page.locator('.knowledge-document-item').filter({ hasText: target.otherTitle }).first();
  await clickVisible(otherRow, 'selection_race_prime_other_document');
  await waitForSelectionAgreement(page, target.otherTitle, 'selection_race_prime_other_document');

  const targetPath = `/knowledge-api/documents/${encodeURIComponent(target.id)}`;
  const contextPaths = [targetPath, `${targetPath}/versions`];
  const routePattern = '**/knowledge-api/documents/**';
  let releaseDelayed;
  const delayedGate = new Promise(resolve => { releaseDelayed = resolve; });
  const delayedPaths = [];
  await page.route(routePattern, async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (contextPaths.includes(pathname)) {
      delayedPaths.push(pathname);
      await delayedGate;
    }
    await route.continue();
  });
  const delayedContextRequests = contextPaths.map(pathname => page.waitForRequest(request => new URL(request.url()).pathname === pathname, { timeout: 15000 }));
  try {
    await clickVisible(targetRow, 'selection_race_slow_context_select');
    await Promise.all(delayedContextRequests);
    check('selection_race_context_requests_delayed', contextPaths.every(pathname => delayedPaths.includes(pathname)));
    const delayedContextResponses = contextPaths.map(pathname => page.waitForResponse(response => new URL(response.url()).pathname === pathname, { timeout: 15000 }));
    await clickVisible(otherRow, 'selection_race_switch_during_context_load');
    await waitForSelectionAgreement(page, target.otherTitle, 'selection_race_other_context_loaded');
    releaseDelayed();
    const responses = await Promise.all(delayedContextResponses);
    check('selection_race_delayed_context_responses_arrived', responses.every(response => response.ok()));
    await waitForSelectionAgreement(page, target.otherTitle, 'selection_race_late_context_did_not_replace_reader');
  } finally {
    releaseDelayed();
    await page.unroute(routePattern);
  }

  await clickVisible(targetRow, 'version_race_open_target');
  await waitForSelectionAgreement(page, target.title, 'version_race_target_loaded');
  check('version_race_archived_filter_enabled', await page.locator('.knowledge-archive-toggle .ant-switch').evaluate(element => element.classList.contains('ant-switch-checked')));
  check('version_race_target_is_archived', await targetRow.getByText('Archived', { exact: true }).isVisible());
  const historyRows = page.locator('.version-history-row');
  await historyRows.first().waitFor({ state: 'visible', timeout: 10000 });
  check('version_race_history_has_multiple_versions', await historyRows.count() >= 2);
  check('version_race_document_current_version_is_v3', await targetRow.getByText('v3', { exact: true }).isVisible());
  const oldVersion = page.locator('.version-history-row:not(.version-history-current)').first();
  await oldVersion.waitFor({ state: 'visible', timeout: 10000 });
  const oldVersionLabel = (await oldVersion.locator('.version-history-number').innerText()).trim();
  const oldVersionNumber = Number(oldVersionLabel.replace(/[^0-9]/g, ''));
  check('version_race_historical_version_available', Number.isInteger(oldVersionNumber) && oldVersionNumber > 0);
  const delayedVersionPath = `${targetPath}/versions/${oldVersionNumber}`;
  let releaseVersion;
  const delayedVersionGate = new Promise(resolve => { releaseVersion = resolve; });
  let delayedVersionReached = false;
  await page.route(routePattern, async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === delayedVersionPath) {
      delayedVersionReached = true;
      await delayedVersionGate;
    }
    await route.continue();
  });
  const delayedVersionRequest = page.waitForRequest(request => new URL(request.url()).pathname === delayedVersionPath, { timeout: 15000 });
  try {
    await clickVisible(oldVersion, 'version_race_slow_old_version_select');
    await delayedVersionRequest;
    check('version_race_old_version_response_delayed', delayedVersionReached);
    const delayedVersionResponse = page.waitForResponse(response => new URL(response.url()).pathname === delayedVersionPath, { timeout: 15000 });
    await clickVisible(otherRow, 'version_race_switch_during_old_version_load');
    await waitForSelectionAgreement(page, target.otherTitle, 'version_race_other_document_loaded');
    releaseVersion();
    const response = await delayedVersionResponse;
    check('version_race_delayed_old_version_arrived', response.ok());
    await waitForSelectionAgreement(page, target.otherTitle, 'version_race_late_version_did_not_replace_reader');
  } finally {
    releaseVersion();
    await page.unroute(routePattern);
  }

  await clickVisible(targetRow, 'mobile_target_document_reselect');
  await waitForSelectionAgreement(page, target.title, 'mobile_target_document_selected');
}

async function runMobileStructureCheck(page, title, bodyHeading) {
  await page.setViewportSize({ width: 390, height: 844 });
  await waitForSelectionAgreement(page, title, 'mobile_selected_document_stable');
  await checkDocumentListBounds(page, 'mobile_document_list');
  const heading = page.locator('.knowledge-reader .reader-document-head h3');
  await heading.waitFor({ state: 'visible', timeout: 15000 });
  await heading.scrollIntoViewIfNeeded();
  check('mobile_selected_document_readable', (await heading.innerText()).trim() === title);
  const liveStatus = page.locator('.knowledge-reader .collab-editor .collab-connection-live');
  const savedStatus = page.locator('.knowledge-reader .collab-editor .collab-save-ok');
  const loadingIndicator = page.locator('.knowledge-reader .collab-editor .collab-loading');
  const markdownBody = page.locator('.knowledge-reader .collab-codemirror .cm-content[contenteditable="true"]');
  await liveStatus.waitFor({ state: 'visible', timeout: 20000 });
  await savedStatus.waitFor({ state: 'visible', timeout: 20000 });
  await loadingIndicator.waitFor({ state: 'hidden', timeout: 20000 });
  await markdownBody.waitFor({ state: 'visible', timeout: 20000 });
  check('mobile_shared_draft_live_and_saved', await liveStatus.isVisible() && await savedStatus.isVisible());
  check('mobile_shared_draft_loading_finished', !(await loadingIndicator.isVisible().catch(() => false)));
  check('mobile_document_body_visible', (await markdownBody.innerText()).includes(bodyHeading));

  const structureButton = page.getByRole('button', { name: 'Document structure', exact: true });
  await clickVisible(structureButton, 'mobile_open_structure');
  const structureModal = page.locator('.ant-modal:visible').last();
  await structureModal.waitFor({ state: 'visible' });
  const modalBox = await structureModal.boundingBox();
  check('mobile_structure_modal_fits_viewport', Boolean(modalBox && modalBox.x >= 0 && modalBox.y >= 0 && modalBox.x + modalBox.width <= 390 && modalBox.y + modalBox.height <= 844));
  await clickVisible(structureModal.getByRole('button', { name: 'Cancel', exact: true }), 'mobile_cancel_structure');
  await structureModal.waitFor({ state: 'hidden' });

  const dimensions = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
  check('mobile_page_has_no_horizontal_overflow', dimensions.document <= dimensions.viewport + 1 && dimensions.body <= dimensions.viewport + 1);
  await waitForSelectionAgreement(page, title, 'mobile_screenshot_document_stable');
  await waitForTransientMessages(page, 'messages_hidden_before_mobile_capture');
  await capture(page, { key: 'mobile' });
}

async function main() {
  await fs.mkdir(screenshotsDirectory, { recursive: true });
  const qaContext = JSON.parse(await fs.readFile(contextPath, 'utf8'));
  assert.equal(qaContext.base_url, baseExpected, 'refusing to run outside the isolated QA host');
  assert.ok(qaContext.run_id && qaContext.knowledge?.space_id && qaContext.knowledge?.document_id, 'synthetic Knowledge fixture missing');
  const session = qaContext.users?.admin;
  assert.ok(session && typeof session.cookie_name === 'string' && typeof session.cookie_value === 'string', 'synthetic admin session missing');
  sensitiveValues.push(session.cookie_value, session.csrf_token);

  const browser = await chromium.launch({ headless: true, ...(chromeExecutable ? { executablePath: chromeExecutable } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-TW', serviceWorkers: 'block' });
  await context.addCookies([{ name: session.cookie_name, value: session.cookie_value, url: baseExpected, httpOnly: true }]);
  await context.route('**/*', route => {
    if (!isFixedLocalTarget(route.request().url())) {
      externalRequestsBlocked += 1;
      return route.abort();
    }
    return route.continue();
  });
  context.on('page', page => page.on('pageerror', () => browserErrors.push('pageerror')));
  try {
    const page = await context.newPage();
    activePage = page;
    currentStep = 'open_fixed_local_knowledge';
    await page.goto(`${baseExpected}/knowledge`, { waitUntil: 'domcontentloaded' });
    await page.locator('.language-control .ant-select').waitFor({ state: 'visible' });
    check('target_is_fixed_local_qa_host', page.url().startsWith(baseExpected));
    await page.locator('.side-rail .workspace-identity').waitFor({ state: 'visible' });
    let finalDocument;
    for (let index = 0; index < locales.length; index += 1) {
      finalDocument = await runLocale(page, locales[index], qaContext, index);
    }
    await runSelectionRaceChecks(page, finalDocument);
    await runMobileStructureCheck(page, finalDocument.title, finalDocument.bodyHeading);
    check('browser_pages_have_no_javascript_errors', browserErrors.length === 0);
    report.browserErrors = browserErrors.length;
    report.externalRequestsBlocked = externalRequestsBlocked;
    report.status = 'passed';
  } catch (error) {
    report.failedStep = currentStep;
    report.errors = [{ step: currentStep, message: safeError(error) }];
    report.browserErrors = browserErrors.length;
    report.externalRequestsBlocked = externalRequestsBlocked;
    if (activePage) {
      try {
        const filename = 'knowledge-authoring-failure.png';
        await activePage.screenshot({ path: path.join(screenshotsDirectory, filename), fullPage: false });
        report.screenshots.push(`screenshots/${filename}`);
        report.diagnostics = {
          language: await activePage.locator('html').getAttribute('lang'),
          heading: (await activePage.locator('.page-heading').innerText().catch(() => '')).slice(0, 180),
          visibleButtons: (await activePage.locator('button:visible').allInnerTexts()).map(text => text.trim()).filter(Boolean).slice(0, 24),
        };
      } catch {
        report.diagnostics = { screenshot: 'unavailable' };
      }
    }
    throw error;
  } finally {
    await context.close().catch(() => undefined);
    await browser.close().catch(() => undefined);
    await fs.writeFile(path.join(qaDirectory, 'report.json'), JSON.stringify(report, null, 2), 'utf8');
  }
}

main().then(() => {
  console.log(`KNOWLEDGE_AUTHORING_BROWSER_${report.status.toUpperCase()} checks=${Object.keys(report.checks).length} screenshots=${report.screenshots.length} report=.cache/p0-p1-qa/report.json`);
}).catch(error => {
  report.externalRequestsBlocked = externalRequestsBlocked;
  console.error(`${currentStep}: ${safeError(error)}`);
  process.exitCode = 1;
});
