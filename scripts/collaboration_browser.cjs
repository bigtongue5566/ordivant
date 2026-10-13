// Run with: node scripts/collaboration_browser.cjs
// Uses only the isolated synthetic browser sessions prepared by the QA API harness.
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const fsSync = require('node:fs');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(path.resolve('.cache/browser-qa/node_modules/playwright'));

const qaDirectory = path.resolve('.cache/collaboration-qa');
const contextPath = path.join(qaDirectory, 'context.json');
const reportPath = path.join(qaDirectory, 'report.json');
const baseExpected = 'http://127.0.0.1:8096';
const chromeExecutable = [
  path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
  path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe'),
].find(candidate => fsSync.existsSync(candidate));
const locales = [
  { key: 'zh-TW', label: '繁體中文', htmlLang: 'zh-Hant' },
  { key: 'zh-CN', label: '简体中文', htmlLang: 'zh-Hans' },
  { key: 'en', label: 'English', htmlLang: 'en' },
];
const checks = {};
const screenshots = [];
const browserErrors = [];
const sensitiveValues = [];
const networkEvents = [];
const recordedErrors = new WeakSet();
let currentStep = 'initialize';
let diagnosticPage = null;
let report = { status: 'failed', target: baseExpected, checks, screenshots, browserErrors: 0 };

function check(name, condition) {
  currentStep = name;
  checks[name] = Boolean(condition);
  assert.ok(condition, name);
}

function observePosts(page, module) {
  const isTrackedRequest = request => {
    const pathname = new URL(request.url()).pathname;
    const method = request.method();
    return ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)
      || (method === 'GET' && pathname.includes('/pulls/') && pathname.endsWith('/collaboration'));
  };
  const record = (kind, request, status) => {
    const pathname = new URL(request.url()).pathname;
    if (!pathname.includes('/tasks/') && !pathname.includes('/pulls/')) return;
    if (request.method() === 'GET' && !pathname.endsWith('/collaboration')) return;
    const route = pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, '[id]').slice(0, 180);
    if (networkEvents.length < 80) networkEvents.push({ module, kind, method: request.method(), route, ...(status == null ? {} : { status }) });
  };
  page.on('request', request => {
    if (isTrackedRequest(request)) record('request', request);
  });
  page.on('response', response => {
    if (isTrackedRequest(response.request())) record('response', response.request(), response.status());
  });
  page.on('requestfailed', request => {
    if (isTrackedRequest(request)) record('requestfailed', request);
  });
}

function safeSocketType(payload) {
  const raw = Buffer.isBuffer(payload) ? payload.toString() : String(payload);
  try {
    const type = JSON.parse(raw)?.type;
    return ['authenticate', 'update', 'sync', 'presence', 'ack', 'error'].includes(type) ? type : 'other';
  } catch {
    return 'other';
  }
}

function observeCodeCollaborationRead(page, role, markerState) {
  page.on('response', async response => {
    const request = response.request();
    const pathname = new URL(response.url()).pathname;
    if (request.method() !== 'GET' || !pathname.includes('/pulls/') || !pathname.endsWith('/collaboration')) return;
    let value = null;
    try {
      if (response.ok()) value = await response.json();
    } catch {
      value = null;
    }
    const comments = Array.isArray(value?.comments) ? value.comments : [];
    const reviews = Array.isArray(value?.reviews) ? value.reviews : [];
    report.codeReadbacks ??= {};
    report.codeReadbacks[role] = {
      status: response.status(),
      comment_count: comments.length,
      review_count: reviews.length,
      head_sha: typeof value?.head_sha === 'string' ? value.head_sha.slice(0, 64) : null,
      comment_marker_present: Boolean(markerState.comment && comments.some(item => String(item?.body ?? '').includes(markerState.comment))),
      review_marker_present: Boolean(markerState.review && reviews.some(item => String(item?.comment ?? '').includes(markerState.review))),
    };
  });
}

function safeError(error) {
  const message = error instanceof Error ? error.message : String(error);
  let sanitized = message
    .split('\n')[0]
    .replace(/https?:\/\/[^\s]+/g, '[url]')
    .replace(/(cookie|csrf|token|password|authorization)\s*[:=]\s*[^\s,;]+/gi, '$1=[redacted]')
    .replace(/\b[a-f0-9]{8}-[a-f0-9-]{27,}\b/gi, '[id]')
    .replace(/tr\[data-row-key="[^"]+"\]/g, 'tr[data-row-key]')
    .replace(/locator\([^)]*\)/g, 'locator');
  for (const value of sensitiveValues) if (value) sanitized = sanitized.split(value).join('[redacted]');
  return sanitized.slice(0, 320);
}

function account(context, name) {
  const user = context?.users?.[name];
  assert.ok(user && typeof user.cookie_name === 'string' && typeof user.cookie_value === 'string', `missing synthetic ${name} session`);
  return user;
}

async function newUserContext(browser, qaContext, name, viewport = { width: 1440, height: 1000 }) {
  const session = account(qaContext, name);
  sensitiveValues.push(session.cookie_value);
  const context = await browser.newContext({ viewport, locale: 'zh-TW' });
  await context.addCookies([{ name: session.cookie_name, value: session.cookie_value, url: baseExpected, httpOnly: true }]);
  context.on('page', page => page.on('pageerror', () => browserErrors.push('pageerror')));
  return context;
}

async function gotoProduct(page, product, ensureDefaultLanguage = true) {
  await page.goto(`${baseExpected}/${product}`, { waitUntil: 'domcontentloaded' });
  await page.locator('.language-control').waitFor({ state: 'visible' });
  if (ensureDefaultLanguage && await page.locator('html').getAttribute('lang') !== 'zh-Hant') await changeLanguage(page, locales[0]);
  await page.locator('.side-rail .workspace-identity').waitFor({ state: 'visible' });
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
  assert.ok(result?.ok, 'scoped QA fixture metadata unavailable');
  return result.value;
}

async function chooseVisibleOption(page, select, searchText, name) {
  currentStep = name;
  await select.click();
  const popup = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last();
  await popup.waitFor({ state: 'visible' });
  const options = popup.locator('.ant-select-item-option');
  const option = options.filter({ hasText: searchText }).first();
  await option.waitFor({ state: 'visible' });
  const box = await option.boundingBox();
  const viewport = page.viewportSize();
  check(`${name}_dropdown_open_and_in_view`, Boolean(box && viewport && box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1));
  const receivesMouse = await option.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(hit && element.contains(hit));
  });
  check(`${name}_dropdown_receives_mouse`, receivesMouse);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await popup.waitFor({ state: 'hidden' });
  return option;
}

function buttonWithText(container, text) {
  return container.locator('button').filter({ hasText: text }).last();
}

async function waitForNodeCondition(predicate, timeoutMs, message) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(message);
}

async function changeLanguage(page, locale) {
  await chooseVisibleOption(
    page,
    page.locator('.language-control .ant-select'),
    locale.label,
    `language_${locale.key}`,
  );
  await page.waitForFunction(expected => document.documentElement.lang === expected, locale.htmlLang);
  check(`language_${locale.key}_applied`, true);
}

async function assertEnglishInterface(page, selector, name) {
  const text = await page.locator(selector).allInnerTexts();
  check(`${name}_english_has_no_chinese`, text.length > 0 && !/[\u3400-\u9fff]/u.test(text.join(' ')));
}

async function capture(page, filename) {
  const target = path.join(qaDirectory, filename);
  await page.screenshot({ path: target, fullPage: false });
  screenshots.push(filename);
}

async function recordFailure(error) {
  if (error && typeof error === 'object') {
    if (recordedErrors.has(error)) return;
    recordedErrors.add(error);
  }
  const step = currentStep;
  const errors = report.errors ?? [];
  errors.push({ step, message: safeError(error) });
  report.errors = errors;
  report.failed_step ??= step;
  if (!diagnosticPage) return;
  try {
    report.network = networkEvents;
    const diagnostics = await diagnosticPage.evaluate(() => {
      const element = document.querySelector('.project-select');
      const rect = element?.getBoundingClientRect();
      const hit = rect ? document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2) : null;
      const taskDrawer = document.querySelector('.task-drawer');
      const claimButtons = [...(taskDrawer?.querySelectorAll('button') ?? [])].filter(button => button.innerText?.includes('認領任務'));
      const actionButton = label => {
        const button = [...document.querySelectorAll('button')].find(item => item.innerText?.includes(label));
        const buttonRect = button?.getBoundingClientRect();
        const buttonHit = buttonRect ? document.elementFromPoint(buttonRect.x + buttonRect.width / 2, buttonRect.y + buttonRect.height / 2) : null;
        return {
          found: Boolean(button),
          visible: Boolean(buttonRect && buttonRect.width > 0 && buttonRect.height > 0),
          enabled: Boolean(button && !button.disabled),
          centerHitClass: typeof buttonHit?.className === 'string' ? buttonHit.className.slice(0, 120) : null,
        };
      };
      const toastKinds = [...document.querySelectorAll('.ant-message-notice-content')].map(item => {
        const text = item.textContent ?? '';
        if (text.includes('已認領')) return 'claim_success';
        if (text.includes('認領') && /(不可|無法)/.test(text)) return 'claim_denied';
        if (text.includes('成功')) return 'success';
        return 'other';
      });
      const dialogs = [...document.querySelectorAll('.ant-modal')].map(modal => ({
        visible: Boolean(modal.getBoundingClientRect().width && modal.getBoundingClientRect().height),
        buttons: [...modal.querySelectorAll('button')].map(button => ({ text: button.innerText?.trim() ?? '', enabled: !button.disabled, primary: button.classList.contains('ant-btn-primary') })),
        fieldErrors: [...modal.querySelectorAll('.ant-form-item-explain-error')].map(item => item.textContent?.trim() ?? '').filter(Boolean),
      }));
      return {
        path: location.pathname,
        projectSelectCount: document.querySelectorAll('.project-select').length,
        projectSelectVisible: Boolean(rect && rect.width > 0 && rect.height > 0),
        projectSelectCenterHit: hit?.tagName?.toLowerCase() ?? null,
        projectSelectCenterHitClass: typeof hit?.className === 'string' ? hit.className.slice(0, 120) : null,
        taskDrawerVisible: Boolean(taskDrawer && taskDrawer.getBoundingClientRect().width > 0),
        claimButtonCount: claimButtons.length,
        claimButtonEnabled: claimButtons.some(button => !button.disabled),
        taskActionTexts: [...(taskDrawer?.querySelectorAll('button') ?? [])].map(button => button.innerText?.trim() ?? '').filter(text => ['認領任務', '目前由你執行', '回報進度', '解除執行', '阻塞'].some(label => text.includes(label))),
        actionButtons: {
          claim: actionButton('認領任務'),
          codeComment: actionButton('送出討論'),
          codeReview: actionButton('送出審查記錄'),
        },
        dialogs,
        toastKinds,
      };
    });
    report.diagnostics ??= {};
    report.diagnostics[step] = diagnostics;
    const filename = `${step.replace(/[^a-z0-9-]/gi, '-')}-failure.png`;
    await diagnosticPage.screenshot({ path: path.join(qaDirectory, filename), fullPage: false });
    if (!screenshots.includes(filename)) screenshots.push(filename);
  } catch {
    report.diagnostics ??= { screenshot: 'unavailable' };
  }
}

async function selectWorkProject(page, projectId) {
  const projects = await readJson(page, '/api/projects');
  const project = Array.isArray(projects) ? projects.find(item => item.id === projectId) : null;
  assert.ok(project?.key, 'Work project fixture unavailable');
  await chooseVisibleOption(page, page.locator('.project-select'), project.key, 'work_project_picker');
}

async function workAcceptance(alice, qaContext) {
  const page = await alice.newPage();
  diagnosticPage = page;
  observePosts(page, 'work');
  await gotoProduct(page, 'work');
  await selectWorkProject(page, qaContext.work.project_id);
  currentStep = 'work_task_open';
  const taskRow = page.locator(`tr[data-row-key="${qaContext.work.browser_task_id}"]`);
  await taskRow.waitFor({ state: 'visible' });
  await taskRow.click();
  const drawer = page.locator('.task-drawer');
  await drawer.waitFor({ state: 'visible' });

  await page.waitForFunction(taskId => {
    const taskDrawer = document.querySelector('.task-drawer');
    if (!taskDrawer) return false;
    const text = taskDrawer.innerText ?? '';
    return text.includes('目前由你執行') || [...taskDrawer.querySelectorAll('button')].some(button => button.innerText?.includes('認領任務'));
  }, qaContext.work.browser_task_id, { timeout: 20000 });
  const claimButton = buttonWithText(drawer, '認領任務');
  const currentExecution = drawer.getByText('目前由你執行', { exact: true });
  if (await claimButton.count() > 0 && await claimButton.isVisible().catch(() => false)) {
    currentStep = 'work_human_claim';
    check('work_human_claim_button_enabled', await claimButton.isEnabled());
    check('work_human_claim_button_receives_mouse', await claimButton.evaluate(element => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return Boolean(hit && element.contains(hit));
    }));
    const [claimed] = await Promise.all([
      page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith(`/tasks/${qaContext.work.browser_task_id}/claim`), { timeout: 12000 }),
      claimButton.click({ timeout: 5000 }),
    ]);
    check('work_human_claim_succeeded', claimed.ok());
    await currentExecution.waitFor({ state: 'visible' });
  } else {
    currentStep = 'work_human_execution_resume';
    await currentExecution.waitFor({ state: 'visible' });
    check('work_human_execution_resumed_same_principal', true);
  }

  await drawer.getByRole('button', { name: '回報進度', exact: true }).click();
  const progressDialog = page.getByRole('dialog').last();
  await progressDialog.waitFor({ state: 'visible' });
  await progressDialog.locator('.ant-form-item').filter({ hasText: '完成進度' }).locator('input').fill('41');
  await progressDialog.locator('.ant-form-item').filter({ hasText: '執行摘要' }).locator('textarea').fill('Synthetic browser collaboration progress check.');
  currentStep = 'work_human_progress';
  const progressSubmit = page.locator('.ant-modal:visible .ant-modal-footer button.ant-btn-primary').last();
  check('work_progress_submit_button_enabled', await progressSubmit.isEnabled());
  check('work_progress_submit_button_receives_mouse', await progressSubmit.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(hit && element.contains(hit));
  }));
  const [progressResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith(`/tasks/${qaContext.work.browser_task_id}/progress`)),
    progressSubmit.click(),
  ]);
  check('work_progress_saved', progressResponse.ok());
  await drawer.getByRole('button', { name: '回報進度', exact: true }).waitFor({ state: 'visible' });

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.locator('.side-rail .workspace-identity').waitFor({ state: 'visible' });
  await selectWorkProject(page, qaContext.work.project_id);
  const reopenedRow = page.locator(`tr[data-row-key="${qaContext.work.browser_task_id}"]`);
  await reopenedRow.waitFor({ state: 'visible' });
  await reopenedRow.click();
  const reopenedDrawer = page.locator('.task-drawer');
  await reopenedDrawer.getByText('目前由你執行', { exact: true }).waitFor({ state: 'visible' });
  await reopenedDrawer.getByRole('button', { name: '回報進度', exact: true }).waitFor({ state: 'visible' });
  check('work_human_execution_recovers_after_reload', true);

  const editSpecButton = buttonWithText(reopenedDrawer, '編輯規格');
  check('work_edit_spec_button_enabled', await editSpecButton.isEnabled());
  check('work_edit_spec_button_receives_mouse', await editSpecButton.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(hit && element.contains(hit));
  }));
  await editSpecButton.click();
  const editDialog = page.getByRole('dialog').last();
  await editDialog.waitFor({ state: 'visible' });
  const assignee = editDialog.locator('.ant-form-item').filter({ hasText: '負責者' }).locator('.ant-select');
  await assignee.click();
  const picker = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last();
  await picker.waitFor({ state: 'visible' });
  const aliceName = await page.locator('.workspace-user strong').innerText();
  const aliceOption = picker.locator('.ant-select-item-option').filter({ hasText: aliceName }).first();
  await aliceOption.waitFor({ state: 'visible' });
  const optionText = await aliceOption.innerText();
  check('work_human_assignee_option_and_badge', optionText.includes('真人') && optionText.includes(aliceName));
  const pickerBox = await aliceOption.boundingBox();
  const viewport = page.viewportSize();
  check('work_assignee_picker_not_covered', Boolean(pickerBox && viewport && pickerBox.x >= 0 && pickerBox.y >= 0 && pickerBox.x + pickerBox.width <= viewport.width + 1 && pickerBox.y + pickerBox.height <= viewport.height + 1));
  const pickerReceivesMouse = await aliceOption.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(hit && element.contains(hit));
  });
  check('work_assignee_picker_receives_mouse', pickerReceivesMouse);
  await page.mouse.click(pickerBox.x + pickerBox.width / 2, pickerBox.y + pickerBox.height / 2);
  const cancelEdit = editDialog.locator('.ant-modal-footer button:not(.ant-btn-primary)').last();
  check('work_assignee_picker_cancel_enabled', await cancelEdit.isEnabled());
  check('work_assignee_picker_cancel_receives_mouse', await cancelEdit.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(hit && element.contains(hit));
  }));
  await cancelEdit.click();
  await capture(page, 'work-human-reload.png');
  return page;
}

async function openKnowledgeDocument(page, qaContext) {
  await gotoProduct(page, 'knowledge');
  const spaces = await readJson(page, '/knowledge-api/spaces');
  const space = Array.isArray(spaces) ? spaces.find(item => item.id === qaContext.knowledge.space_id) : null;
  assert.ok(space?.key, 'Knowledge space fixture unavailable');
  await chooseVisibleOption(page, page.locator('.product-scope-select'), space.key, 'knowledge_space_picker');

  const docs = await readJson(page, `/knowledge-api/documents?space_id=${encodeURIComponent(qaContext.knowledge.space_id)}`);
  const document = Array.isArray(docs) ? docs.find(item => item.id === qaContext.knowledge.document_id) : null;
  assert.ok(document?.title, 'Knowledge document fixture unavailable');
  const docButton = page.locator('.knowledge-document-item').filter({ hasText: document.title }).first();
  await docButton.waitFor({ state: 'visible' });
  await docButton.click();
  await page.locator('.collab-codemirror .cm-content').waitFor({ state: 'visible' });
  await page.locator('.collab-connection-live').waitFor({ state: 'visible' });
  return { document, editor: page.locator('.collab-codemirror .cm-content') };
}

async function typeAtDocumentStart(page, editor, text, step) {
  await page.bringToFront();
  await editor.click();
  const focused = await editor.evaluate(element => document.activeElement === element);
  check(`${step}_codemirror_focused_before_typing`, focused);
  await page.keyboard.press('Control+Home');
  await page.keyboard.type(`${text}\n`, { delay: 1 });
}

async function waitForEditorText(page, text, step) {
  currentStep = step;
  await page.waitForFunction(marker => [...document.querySelectorAll('.collab-codemirror .cm-content')].some(element => element.innerText.includes(marker)), text, { timeout: 30000 });
}

async function knowledgeAcceptance(browser, alice, bob, qaContext) {
  const alicePage = await alice.newPage();
  diagnosticPage = alicePage;
  const bobPage = await bob.newPage();
  const pages = [alicePage, bobPage];
  let refreshPage = null;
  const socketState = {
    relayEnabled: true,
    matched: 0,
    blocked: 0,
    links: [],
    phase: 'concurrent',
    opened: 0,
    closed: 0,
    socketErrors: 0,
    messages: { sent: {}, received: {}, phases: {} },
  };
  const documentId = qaContext.knowledge.document_id;
  const trackSocketMessage = (direction, payload) => {
    const type = safeSocketType(payload);
    const phaseCounts = socketState.messages.phases[socketState.phase] ??= { sent: {}, received: {} };
    const counts = [socketState.messages[direction], phaseCounts[direction]];
    for (const counter of counts) counter[type] = (counter[type] ?? 0) + 1;
  };
  alicePage.on('websocket', socket => {
    if (!new URL(socket.url()).pathname.includes(`/documents/${documentId}/collaborate`)) return;
    socketState.opened += 1;
    socket.on('framesent', event => trackSocketMessage('sent', event.payload));
    socket.on('framereceived', event => trackSocketMessage('received', event.payload));
    socket.on('socketerror', () => { socketState.socketErrors += 1; });
    socket.on('close', () => { socketState.closed += 1; });
  });
  await alice.routeWebSocket(new RegExp(`${documentId}/collaborate(?:\\?.*)?$`), route => {
    socketState.matched += 1;
    if (!socketState.relayEnabled) {
      socketState.blocked += 1;
      void route.close({ code: 1011, reason: 'Synthetic QA collaboration outage' }).catch(() => undefined);
      return;
    }
    socketState.links.push({ client: route, server: route.connectToServer(), closed: false });
  });
  try {
  const aliceDoc = await openKnowledgeDocument(alicePage, qaContext);
  const bobDoc = await openKnowledgeDocument(bobPage, qaContext);
  check('knowledge_real_websocket_route_intercepts_document', socketState.matched >= 1);
  const runPrefix = randomUUID();
  const aliceMarker = `QA-BROWSER-${runPrefix}-ALICE`;
  const bobMarker = `QA-BROWSER-${runPrefix}-BOB`;
  const initialBody = await aliceDoc.editor.innerText();
  check('knowledge_loaded_run_scoped_draft', initialBody.includes(`QA-COLLAB-${runPrefix}`) || initialBody.includes('QA-COLLAB-'));

  await alicePage.waitForFunction(() => document.querySelectorAll('.collab-avatar-human').length >= 2, null, { timeout: 20000 });
  check('knowledge_presence_shows_two_humans', await alicePage.locator('.collab-avatar-human').count() >= 2);
  currentStep = 'knowledge_concurrent_edits';
  await typeAtDocumentStart(alicePage, aliceDoc.editor, aliceMarker, 'knowledge_alice_concurrent');
  await typeAtDocumentStart(bobPage, bobDoc.editor, bobMarker, 'knowledge_bob_concurrent');
  for (const [name, editor] of [['alice', aliceDoc.editor], ['bob', bobDoc.editor]]) {
    await waitForEditorText(name === 'alice' ? alicePage : bobPage, aliceMarker, `knowledge_concurrent_merge_${name}_alice`);
    await waitForEditorText(name === 'alice' ? alicePage : bobPage, bobMarker, `knowledge_concurrent_merge_${name}_bob`);
    check(`knowledge_concurrent_merge_${name}`, true);
  }
  await alicePage.locator('.collab-save-ok').waitFor({ state: 'visible', timeout: 30000 });
  await bobPage.locator('.collab-save-ok').waitFor({ state: 'visible', timeout: 30000 });
  check('knowledge_concurrent_updates_saved', true);

  refreshPage = await alice.newPage();
  pages.push(refreshPage);
  const refreshed = await openKnowledgeDocument(refreshPage, qaContext);
  await waitForEditorText(refreshPage, aliceMarker, 'knowledge_fresh_page_merge_alice');
  await waitForEditorText(refreshPage, bobMarker, 'knowledge_fresh_page_merge_bob');
  check('knowledge_merged_draft_survives_fresh_page', true);

  const offlineMarker = `QA-BROWSER-${runPrefix}-RECONNECT`;
  report.knowledge ??= {};
  report.knowledge.offline_marker = offlineMarker;
  currentStep = 'knowledge_offline_disconnect';
  socketState.phase = 'disconnecting';
  socketState.relayEnabled = false;
  const openLinks = socketState.links.filter(link => !link.closed);
  assert.ok(openLinks.length > 0, 'no live Knowledge WebSocket route to disconnect');
  await Promise.all(openLinks.map(async link => {
    await link.client.close({ code: 1011, reason: 'Synthetic QA collaboration outage' }).catch(() => undefined);
    link.closed = true;
  }));
  socketState.phase = 'offline';
  await alicePage.locator('.collab-connection-reconnecting').waitFor({ state: 'visible', timeout: 20000 });
  await waitForNodeCondition(() => socketState.blocked > 0, 20000, 'Knowledge reconnect was not intercepted while collaboration was offline');
  check('knowledge_collaboration_websocket_disconnected', true);
  currentStep = 'knowledge_offline_edit';
  const preTypeBody = await aliceDoc.editor.innerText();
  report.knowledge.offline_local_marker_before_count = preTypeBody.split(offlineMarker).length - 1;
  report.knowledge.offline_local_marker_before_present = report.knowledge.offline_local_marker_before_count > 0;
  await typeAtDocumentStart(alicePage, aliceDoc.editor, offlineMarker, 'knowledge_offline');
  await waitForEditorText(alicePage, offlineMarker, 'knowledge_offline_input_local_full_marker');
  const localBody = await aliceDoc.editor.innerText();
  report.knowledge.offline_local_marker_count = localBody.split(offlineMarker).length - 1;
  check('knowledge_offline_input_contains_full_marker', report.knowledge.offline_local_marker_count === 1);
  await alicePage.locator('.collab-save-pending').waitFor({ state: 'visible', timeout: 15000 });
  check('knowledge_offline_edit_held_pending', true);
  currentStep = 'knowledge_offline_reconnect';
  socketState.relayEnabled = true;
  socketState.phase = 'reconnecting';
  await alicePage.locator('.collab-connection-live').waitFor({ state: 'visible', timeout: 45000 });
  await alicePage.locator('.collab-save-ok').waitFor({ state: 'visible', timeout: 30000 });
  await waitForEditorText(bobPage, offlineMarker, 'knowledge_offline_edit_visible_to_peer');
  const peerBody = await bobDoc.editor.innerText();
  report.knowledge.offline_peer_marker_count = peerBody.split(offlineMarker).length - 1;
  socketState.phase = 'merged';
  check('knowledge_offline_edit_merged_after_reconnect', true);
  await capture(alicePage, 'knowledge-live-merge.png');
  } catch (error) {
    await recordFailure(error);
    throw error;
  } finally {
    socketState.relayEnabled = true;
    await alice.setOffline(false).catch(() => undefined);
    report.websocket = { knowledge: {
      matched: socketState.matched,
      blocked: socketState.blocked,
      opened: socketState.opened,
      closed: socketState.closed,
      socket_errors: socketState.socketErrors,
      messages: socketState.messages,
    } };
    await Promise.all(pages.map(page => page.close().catch(() => undefined)));
  }
}

async function openCodePull(page, qaContext, role, preserveLanguage = false) {
  await gotoProduct(page, 'code', !preserveLanguage);
  const projectId = qaContext.code.project_id;
  const projectList = await readJson(page, '/code-api/projects');
  const project = Array.isArray(projectList) ? projectList.find(item => item.id === projectId) : null;
  assert.ok(project?.key, 'Code project fixture unavailable');
  await chooseVisibleOption(page, page.locator('.product-scope-select'), project.key, `code_${role}_project_picker`);

  const repositoryRow = page.locator(`tr[data-row-key="${qaContext.code.repository_id}"] .repository-list-row`);
  await repositoryRow.waitFor({ state: 'visible' });
  await repositoryRow.click();
  const pullRows = page.locator('.repository-pr-row');
  await pullRows.first().waitFor({ state: 'visible' });
  const pullIndex = await pullRows.evaluateAll((elements, number) => elements.findIndex(element => new RegExp(`^#${number}\\s*·`).test(element.innerText.trim())), qaContext.code.pull_number);
  assert.ok(pullIndex >= 0, 'Code PR fixture unavailable in repository UI');
  await pullRows.nth(pullIndex).click();
  const drawer = page.locator('.code-pr-drawer');
  await drawer.waitFor({ state: 'visible' });
  const collaboration = drawer.locator('.code-pr-collaboration');
  await collaboration.waitFor({ state: 'visible' });
  await collaboration.locator('.code-collaboration-heads').waitFor({ state: 'visible' });
  await collaboration.locator('.code-collaboration-entry').first().waitFor({ state: 'visible' });
  return { drawer, collaboration };
}

async function closeCodePull(page, drawer) {
  const closeButton = drawer.locator('.ant-drawer-close');
  if (await closeButton.count()) await closeButton.click();
  else await page.keyboard.press('Escape');
  await drawer.waitFor({ state: 'hidden' });
}

async function codeAcceptance(alice, reader, qaContext) {
  const writerPage = await alice.newPage();
  diagnosticPage = writerPage;
  observePosts(writerPage, 'code');
  const markerState = { comment: null, review: null };
  observeCodeCollaborationRead(writerPage, 'writer', markerState);
  const writerUi = await openCodePull(writerPage, qaContext, 'writer');
  const reviewEntries = writerUi.collaboration.locator('.code-collaboration-entry:has(.code-collaboration-sha)');
  const reviewStatuses = await reviewEntries.locator('.code-collaboration-entry-head .ant-tag').allInnerTexts();
  check('code_review_history_has_current_and_stale', reviewStatuses.includes('最新 head') && reviewStatuses.includes('已過期'));
  const reviewActors = await reviewEntries.evaluateAll(entries => entries.flatMap(entry => Array.from(entry.querySelectorAll('.code-collaboration-entry-head .ant-tag')).map(tag => tag.textContent?.trim() ?? '')));
  check('code_reviews_show_human_actor_badges', reviewActors.includes('真人'));
  check('code_orvidant_gitea_boundary_copy_visible', await writerUi.collaboration.locator('.code-collaboration-note').isVisible());

  const runPrefix = randomUUID();
  markerState.comment = `QA-BROWSER-CODE-${runPrefix}`;
  const commentMarker = markerState.comment;
  await writerUi.collaboration.getByPlaceholder('新增討論').fill(`**Synthetic browser check** ${commentMarker}`);
  currentStep = 'code_writer_comment_submit';
  const commentSubmit = buttonWithText(writerUi.collaboration, '送出討論');
  check('code_writer_comment_button_enabled', await commentSubmit.isEnabled());
  check('code_writer_comment_button_receives_mouse', await commentSubmit.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(hit && element.contains(hit));
  }));
  const [commentResponse] = await Promise.all([
    writerPage.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith(`/pulls/${qaContext.code.pull_number}/comments`), { timeout: 12000 }),
    commentSubmit.click({ timeout: 5000 }),
  ]);
  check('code_writer_comment_post_succeeded', commentResponse.ok());
  const commentEntry = writerUi.collaboration.locator('.code-collaboration-entry').filter({ hasText: commentMarker }).first();
  await commentEntry.waitFor({ state: 'visible' });
  check('code_writer_comment_marked_human', await commentEntry.getByText('真人', { exact: true }).isVisible());

  markerState.review = `QA-BROWSER-REVIEW-${runPrefix}`;
  const reviewMarker = markerState.review;
  await writerUi.collaboration.getByPlaceholder('請輸入審查意見').fill(`Synthetic browser review check ${reviewMarker}`);
  currentStep = 'code_writer_review_submit';
  const reviewSubmit = buttonWithText(writerUi.collaboration, '送出審查記錄');
  check('code_writer_review_button_enabled', await reviewSubmit.isEnabled());
  check('code_writer_review_button_receives_mouse', await reviewSubmit.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(hit && element.contains(hit));
  }));
  const [reviewResponse] = await Promise.all([
    writerPage.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith(`/pulls/${qaContext.code.pull_number}/reviews`), { timeout: 12000 }),
    reviewSubmit.click({ timeout: 5000 }),
  ]);
  check('code_writer_review_post_succeeded', reviewResponse.ok());
  const currentReview = writerUi.collaboration.locator('.code-collaboration-entry:has(.code-collaboration-sha)').filter({ hasText: reviewMarker }).first();
  await currentReview.waitFor({ state: 'visible' });
  check('code_writer_review_shows_human_and_current_head', await currentReview.getByText('真人', { exact: true }).isVisible() && await currentReview.getByText('最新 head', { exact: true }).isVisible());
  await capture(writerPage, 'code-pr-collaboration.png');

  const readerPage = await reader.newPage();
  diagnosticPage = readerPage;
  observePosts(readerPage, 'code-reader');
  observeCodeCollaborationRead(readerPage, 'reader', markerState);
  const readerUi = await openCodePull(readerPage, qaContext, 'reader');
  await waitForNodeCondition(() => Boolean(report.codeReadbacks?.reader), 5000, 'reader collaboration API readback missing');
  currentStep = 'code_reader_comment_visible';
  await readerUi.collaboration.getByText(commentMarker, { exact: false }).waitFor({ state: 'visible' });
  currentStep = 'code_reader_review_visible';
  await readerUi.collaboration.getByText(reviewMarker, { exact: false }).first().waitFor({ state: 'visible' });
  check('code_reader_sees_writer_comment', true);
  check('code_reader_sees_current_writer_review', true);
  currentStep = 'code_reader_readonly_notice_visible';
  check('code_reader_has_readonly_notice', await readerUi.collaboration.locator('.code-collaboration-readonly:visible').count() > 0);
  currentStep = 'code_reader_cannot_submit';
  check('code_reader_cannot_submit_comment_or_review', await buttonWithText(readerUi.collaboration, '送出討論').count() === 0 && await buttonWithText(readerUi.collaboration, '送出審查記錄').count() === 0);
  await readerPage.close();
  await writerPage.close();
}

async function languageAcceptance(alice, qaContext) {
  const page = await alice.newPage();
  diagnosticPage = page;
  const moduleChecks = [
    { product: 'work', name: 'work', labels: '.page-heading h2, .rail-nav .nav-item' },
    { product: 'knowledge', name: 'knowledge', labels: '.page-heading h2, .rail-nav .nav-item, .collab-status-group .ant-tag, .collab-toolbar .ant-segmented-item-label' },
    { product: 'code', name: 'code', labels: '.page-heading h2, .rail-nav .nav-item, .code-collaboration-note .ant-alert-message' },
  ];
  for (const module of moduleChecks) {
    await gotoProduct(page, module.product);
    if (module.product === 'knowledge') await openKnowledgeDocument(page, qaContext);
    for (const locale of locales) {
      await changeLanguage(page, locale);
      let codePull = null;
      if (module.product === 'code') {
        codePull = await openCodePull(page, qaContext, 'language', true);
        await codePull.collaboration.locator('.code-collaboration-note').waitFor({ state: 'visible' });
        check(`code_${locale.key}_collaboration_copy_visible`, await page.locator('.code-pr-collaboration .code-collaboration-note').isVisible());
      }
      const heading = await page.locator('.page-heading h2').innerText();
      check(`${module.name}_${locale.key}_functional_view_visible`, Boolean(heading.trim()));
      if (locale.key === 'en') await assertEnglishInterface(page, module.labels, `${module.name}_${locale.key}`);
      if (module.product === 'knowledge') {
        const toolbar = page.locator('.collab-status-group, .collab-toolbar .ant-segmented');
        check(`knowledge_${locale.key}_collaboration_controls_visible`, await toolbar.first().isVisible() && await toolbar.count() >= 2);
      }
      if (codePull) await closeCodePull(page, codePull.drawer);
    }
  }
  await capture(page, 'collaboration-english.png');
  await page.close();
}

function selectedPhaseFromArgs() {
  const phaseIndex = process.argv.indexOf('--phase');
  if (phaseIndex < 0) {
    assert.equal(process.argv.length, 2, 'usage: node scripts/collaboration_browser.cjs [--phase work|knowledge|code|language]');
    return null;
  }
  assert.equal(phaseIndex, 2, 'usage: node scripts/collaboration_browser.cjs [--phase work|knowledge|code|language]');
  assert.equal(process.argv.length, 4, 'usage: node scripts/collaboration_browser.cjs [--phase work|knowledge|code|language]');
  const phase = process.argv[3];
  assert.ok(['work', 'knowledge', 'code', 'language'].includes(phase), 'phase must be work, knowledge, code, or language');
  return phase;
}

async function main() {
  await fs.mkdir(qaDirectory, { recursive: true });
  const selectedPhase = selectedPhaseFromArgs();
  const qaContext = JSON.parse(await fs.readFile(contextPath, 'utf8'));
  const baseUrl = String(qaContext.base_url ?? '').replace(/\/$/, '');
  assert.equal(baseUrl, baseExpected, 'refusing to run outside the isolated QA host');
  for (const name of ['alice', 'bob', 'reader']) account(qaContext, name);
  assert.ok(qaContext.work?.project_id && qaContext.work?.browser_task_id, 'Work browser fixtures missing');
  assert.ok(qaContext.knowledge?.space_id && qaContext.knowledge?.document_id, 'Knowledge browser fixtures missing');
  assert.ok(qaContext.code?.project_id && qaContext.code?.repository_id && Number.isInteger(qaContext.code?.pull_number), 'Code browser fixtures missing');

  const browser = await chromium.launch({ headless: true, ...(chromeExecutable ? { executablePath: chromeExecutable } : {}) });
  const contexts = [];
  try {
    const alice = await newUserContext(browser, qaContext, 'alice');
    contexts.push(alice);
    const bob = await newUserContext(browser, qaContext, 'bob');
    contexts.push(bob);
    const reader = await newUserContext(browser, qaContext, 'reader');
    contexts.push(reader);

    const phases = [
      ['work', async () => { const page = await workAcceptance(alice, qaContext); await page.close(); }],
      ['knowledge', () => knowledgeAcceptance(browser, alice, bob, qaContext)],
      ['code', () => codeAcceptance(alice, reader, qaContext)],
      ['language', () => languageAcceptance(alice, qaContext)],
    ];
    const phasesToRun = selectedPhase ? phases.filter(([name]) => name === selectedPhase) : phases;
    report.phase = selectedPhase ?? 'all';
    for (const [name, phase] of phasesToRun) {
      currentStep = `phase_${name}`;
      try {
        await phase();
      } catch (error) {
        await recordFailure(error);
      }
    }
    try {
      check('browser_pages_have_no_javascript_errors', browserErrors.length === 0);
    } catch (error) {
      await recordFailure(error);
    }
    report.status = report.errors?.length ? 'failed' : 'passed';
  } finally {
    report.browserErrors = browserErrors.length;
    for (const context of contexts) await context.close().catch(() => undefined);
    await browser.close().catch(() => undefined);
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
  }

  console.log(`ORDIVANT_BROWSER_QA_${report.status.toUpperCase()} phase=${report.phase ?? 'all'} checks=${Object.keys(checks).length} report=.cache/collaboration-qa/report.json`);
  if (report.status !== 'passed') {
    const failure = report.errors?.[0];
    console.error(`${failure?.step ?? 'unknown'}: ${failure?.message ?? 'acceptance failed'}`);
    process.exitCode = 1;
  }
}

main().catch(async error => {
  report.failed_step = currentStep;
  report.errors = [{ step: currentStep, message: safeError(error) }];
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2)).catch(() => undefined);
  console.error(`${currentStep}: ${safeError(error)}`);
  process.exitCode = 1;
});
