// Run with: node scripts/planning_browser.cjs
// Uses only synthetic sessions and fixtures created by planning_acceptance.py.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(path.resolve('.cache/browser-qa/node_modules/playwright'));

const baseUrl = 'http://127.0.0.1:8096';
const projectName = 'ordivant-collaboration-qa-20261014';
const sourceContextPath = path.resolve('.cache/collaboration-qa/context.json');
const fixtureContextPath = path.resolve('.cache/p0-p1-qa/context.json');
const outputDir = path.resolve('.cache/p0-p1-qa');
const screenshotDir = path.join(outputDir, 'screenshots');
const reportPath = path.join(outputDir, 'browser-report.json');
const screenshots = [];
const checks = {};
const errors = [];
const networkEvents = [];
const dropdownHitDiagnostics = [];
const sensitiveValues = [];
let step = 'initialize';
let diagnosticPage = null;

const chromePath = [
  path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
  path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe'),
].find(candidate => fs.existsSync(candidate));

function check(name, condition) {
  step = name;
  checks[name] = Boolean(condition);
  assert.ok(condition, name);
}

function redact(value) {
  let text = String(value instanceof Error ? value.message : value).split('\n')[0]
    .replace(/https?:\/\/[^\s]+/g, '[url]')
    .replace(/(cookie|csrf|token|password|authorization)\s*[:=]\s*[^\s,;]+/gi, '$1=[redacted]')
    .replace(/\b[a-f0-9]{8}-[a-f0-9-]{27,}\b/gi, '[id]');
  for (const secret of sensitiveValues) if (secret) text = text.split(secret).join('[redacted]');
  return text.slice(0, 300);
}

function sessionFor(context, name) {
  const session = context?.users?.[name];
  assert.ok(session && typeof session.cookie_name === 'string' && typeof session.cookie_value === 'string', `missing ${name} QA session`);
  sensitiveValues.push(session.cookie_value);
  return session;
}

async function makeContext(browser, qaContext, name) {
  const session = sessionFor(qaContext, name);
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-TW' });
  await context.addCookies([{ name: session.cookie_name, value: session.cookie_value, url: baseUrl, httpOnly: true }]);
  context.on('page', page => page.on('pageerror', () => errors.push('pageerror')));
  return context;
}

async function readJson(page, url) {
  const result = await page.evaluate(async target => {
    const response = await fetch(target, { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok) return { ok: false };
    return { ok: true, value: await response.json() };
  }, url);
  assert.ok(result.ok, 'QA API fixture metadata unavailable');
  return result.value;
}

async function chooseVisibleOption(page, select, text, name, { scrollToEnd = false, closePopup = true } = {}) {
  step = name;
  await select.click();
  const popup = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last();
  await popup.waitFor({ state: 'visible' });
  if (scrollToEnd) {
    const holder = popup.locator('.rc-virtual-list-holder');
    await holder.evaluate(element => { element.scrollTop = element.scrollHeight; });
  }
  const option = popup.locator('.ant-select-item-option').filter({ hasText: text }).first();
  await option.waitFor({ state: 'visible' });
  await option.click({ trial: true });
  const box = await option.boundingBox();
  const viewport = page.viewportSize();
  check(`${name}_option_in_view`, Boolean(box && viewport && box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1));
  const hitDiagnostic = await option.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    const hitChain = [];
    for (let current = hit; current && hitChain.length < 4; current = current.parentElement) {
      hitChain.push({ tag: current.tagName, className: typeof current.className === 'string' ? current.className.slice(0, 100) : '' });
    }
    return { receivesMouse: Boolean(hit && element.contains(hit)), hitChain };
  });
  dropdownHitDiagnostics.push({ name, receivesMouse: hitDiagnostic.receivesMouse, hitChain: hitDiagnostic.hitChain });
  check(`${name}_option_receives_mouse`, hitDiagnostic.receivesMouse);
  await option.click();
  if (closePopup) await popup.waitFor({ state: 'hidden' });
}

async function selectProject(page, projectId) {
  const projects = await readJson(page, '/api/projects');
  const project = Array.isArray(projects) ? projects.find(item => item.id === projectId) : null;
  assert.ok(project?.key, 'authorized Work project fixture unavailable');
  await chooseVisibleOption(page, page.locator('.project-select'), project.key, 'project_picker');
}

async function changeLanguage(page, locale) {
  await chooseVisibleOption(page, page.locator('.language-control .ant-select'), locale.label, `language_${locale.key}`);
  await page.waitForFunction(expected => document.documentElement.lang === expected, locale.htmlLang);
  check(`language_${locale.key}_applied`, true);
}

async function capture(page, name) {
  await page.screenshot({ path: path.join(screenshotDir, name), fullPage: false });
  screenshots.push(name);
}

async function measureCardControlBounds(page) {
  return page.evaluate(() => {
    const toRect = (element) => {
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height };
    };
    const within = (inner, outer) => Boolean(inner && outer
      && inner.left >= outer.left - 1 && inner.right <= outer.right + 1
      && inner.top >= outer.top - 1 && inner.bottom <= outer.bottom + 1);
    const card = [...document.querySelectorAll('.planning-task-card')].find(item =>
      item.querySelector(':scope > .ant-card-body > .ant-select[aria-label="規劃階段"]')
      && item.querySelector(':scope > .ant-card-body > .planning-card-actions > .ant-select[aria-label="變更規劃狀態"]'));
    if (!card) return { found: false };
    const body = card.querySelector(':scope > .ant-card-body');
    const stage = card.querySelector(':scope > .ant-card-body > .ant-select[aria-label="規劃階段"]');
    const actions = card.querySelector(':scope > .ant-card-body > .planning-card-actions');
    const status = card.querySelector(':scope > .ant-card-body > .planning-card-actions > .ant-select[aria-label="變更規劃狀態"]');
    const cardRect = toRect(card);
    const bodyRect = toRect(body);
    const stageRect = toRect(stage);
    const statusRect = toRect(status);
    const actionsRect = toRect(actions);
    return {
      found: true,
      card: cardRect,
      body: bodyRect,
      stage: stageRect,
      status: statusRect,
      actions: actionsRect,
      selectsInsideBody: within(stageRect, bodyRect) && within(statusRect, bodyRect),
      selectsInsideCard: within(stageRect, cardRect) && within(statusRect, cardRect),
      actionsInsideBody: within(actionsRect, bodyRect),
    };
  });
}

async function openWork(page, projectId) {
  await page.goto(`${baseUrl}/work`, { waitUntil: 'domcontentloaded' });
  await page.locator('.side-rail .workspace-identity').waitFor({ state: 'visible', timeout: 20000 });
  await selectProject(page, projectId);
}

async function main() {
  assert.equal(baseUrl, 'http://127.0.0.1:8096', 'only the dedicated QA target is allowed');
  assert.equal(projectName, 'ordivant-collaboration-qa-20261014', 'only the dedicated QA Compose project is allowed');
  assert.ok(chromePath, 'installed Chrome executable was not found');
  const [qaContext, fixtures] = await Promise.all([
    fsp.readFile(sourceContextPath, 'utf8').then(JSON.parse),
    fsp.readFile(fixtureContextPath, 'utf8').then(JSON.parse),
  ]);
  assert.equal(qaContext.base_url, baseUrl, 'synthetic session context belongs to another host');
  assert.equal(fixtures.base_url, baseUrl, 'fixture context belongs to another host');
  assert.equal(fixtures.compose_project, projectName, 'fixture context belongs to another Compose project');
  assert.ok(typeof fixtures.run_id === 'string' && typeof fixtures.prefix === 'string', 'fixture context is incomplete');
  await fsp.mkdir(screenshotDir, { recursive: true });

  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  const contexts = [];
  const pages = [];
  const report = { status: 'failed', target: baseUrl, compose_project: projectName, run_id: fixtures.run_id, checks, screenshots, page_errors: errors };
  try {
    const admin = await makeContext(browser, qaContext, 'admin'); contexts.push(admin);
    const adminPage = await admin.newPage(); pages.push(adminPage);
    diagnosticPage = adminPage;
    adminPage.on('request', request => {
      if (networkEvents.length >= 100) return;
      const url = new URL(request.url());
      if (url.origin === baseUrl && ['POST', 'PATCH', 'PUT', 'DELETE'].includes(request.method())) {
        networkEvents.push({ method: request.method(), path: url.pathname, status: 'pending' });
      }
    });
    adminPage.on('response', response => {
      if (networkEvents.length >= 100) return;
      const url = new URL(response.url());
      if (url.origin === baseUrl && ['GET', 'POST', 'PATCH', 'PUT', 'DELETE'].includes(response.request().method())) {
        networkEvents.push({ method: response.request().method(), path: url.pathname, status: response.status() });
      }
    });
    await openWork(adminPage, fixtures.project_id);
    await changeLanguage(adminPage, { key: 'zh-TW', label: '繁體中文', htmlLang: 'zh-Hant' });
    await adminPage.locator('.rail-nav .nav-item').filter({ hasText: '規劃工作區' }).click();
    const workspace = adminPage.locator('.planning-workspace');
    await workspace.waitFor({ state: 'visible' });
    await workspace.locator('.planning-board').waitFor({ state: 'visible' });
    check('planning_board_loaded', true);
    const desktopControlBounds = await measureCardControlBounds(adminPage);
    report.card_control_bounds = { desktop: desktopControlBounds };
    check('desktop_stage_and_status_selects_inside_card', desktopControlBounds.found && desktopControlBounds.selectsInsideBody && desktopControlBounds.selectsInsideCard && desktopControlBounds.actionsInsideBody);
    await capture(adminPage, 'planning-board-zh-TW.png');

    const statusSelect = workspace.locator('.planning-toolbar .ant-select').first();
    await chooseVisibleOption(adminPage, statusSelect, '待執行', 'planning_status_filter');
    check('planning_status_filter_applied', await statusSelect.innerText().then(text => text.includes('待執行')));

    const toolbarSearch = workspace.locator('.planning-toolbar input').first();
    await toolbarSearch.fill(fixtures.prefix);
    const browserRunId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const queryName = `${fixtures.prefix} browser query ${browserRunId}`;
    await workspace.locator('.planning-query-name').fill(queryName);
    check('saved_query_name_entered', await workspace.locator('.planning-query-name').inputValue().then(value => value === queryName));
    step = 'saved_query_button_located';
    const saveQueryButton = workspace.getByText('儲存查詢', { exact: true }).locator('xpath=ancestor::button[1]');
    const saveButtonCount = await saveQueryButton.count();
    report.saved_query_button = { matching_text_buttons: saveButtonCount };
    check('saved_query_button_unique', saveButtonCount === 1);
    step = 'saved_query_button_location';
    const saveButtonBox = await saveQueryButton.boundingBox();
    const saveButtonHit = await saveQueryButton.evaluate(button => {
      button.dataset.qaTarget = 'save-query';
      window.__qaSaveQueryEvents = [];
      for (const type of ['pointerdown', 'click']) {
        document.addEventListener(type, event => {
          if (event.target instanceof Element && event.target.closest('[data-qa-target="save-query"]')) {
            window.__qaSaveQueryEvents.push(type);
          }
        }, true);
      }
      const rect = button.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return {
        visible: Boolean(button.offsetWidth && button.offsetHeight),
        disabled: button.disabled,
        centerReceivesMouse: Boolean(hit && button.contains(hit)),
        centerHitTag: hit?.tagName ?? null,
        centerHitClass: typeof hit?.className === 'string' ? hit.className.slice(0, 100) : '',
      };
    });
    report.saved_query_button = { ...report.saved_query_button, ...saveButtonHit, box: saveButtonBox };
    check('saved_query_button_receives_mouse', saveButtonHit.visible && !saveButtonHit.disabled && saveButtonHit.centerReceivesMouse);
    step = 'saved_query_create';
    const [saveQueryResponse] = await Promise.all([
      adminPage.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/saved-queries'), { timeout: 12000 }),
      saveQueryButton.click(),
    ]);
    report.saved_query_button.events = await adminPage.evaluate(() => window.__qaSaveQueryEvents ?? []);
    if (!saveQueryResponse.ok()) {
      const responseText = await saveQueryResponse.text().catch(() => '');
      let body = null;
      try { body = JSON.parse(responseText); } catch { /* Report only a short sanitized response excerpt below. */ }
      const detail = body?.detail;
      const queryRequest = saveQueryResponse.request().postDataJSON();
      report.saved_query_response = {
        status: saveQueryResponse.status(),
        content_type: (await saveQueryResponse.headerValue('content-type'))?.slice(0, 100) ?? null,
        filter_keys: queryRequest?.filters && typeof queryRequest.filters === 'object' ? Object.keys(queryRequest.filters).sort() : [],
        status_filter: typeof queryRequest?.filters?.status === 'string' ? queryRequest.filters.status : null,
        validation_errors: Array.isArray(detail) ? detail.map(item => ({
          loc: Array.isArray(item.loc) ? item.loc.map(String) : [],
          type: typeof item.type === 'string' ? item.type.slice(0, 100) : '',
          msg: typeof item.msg === 'string' ? item.msg.slice(0, 200) : '',
        })) : undefined,
        error_code: typeof detail?.code === 'string' ? detail.code.slice(0, 100) : typeof body?.code === 'string' ? body.code.slice(0, 100) : undefined,
        error_message: typeof detail?.message === 'string' ? detail.message.slice(0, 200) : typeof detail === 'string' ? detail.slice(0, 200) : typeof body?.message === 'string' ? body.message.slice(0, 200) : undefined,
        response_excerpt: body ? undefined : redact(responseText).slice(0, 300),
      };
    }
    check('saved_query_created_from_browser', saveQueryResponse.status() === 201);
    const savedQueriesAfterCreate = await readJson(adminPage, '/api/saved-queries');
    report.saved_query_count_after_create = Array.isArray(savedQueriesAfterCreate) ? savedQueriesAfterCreate.length : null;
    check('saved_query_persisted_after_create', Array.isArray(savedQueriesAfterCreate) && savedQueriesAfterCreate.some(item => item?.name === queryName));
    await toolbarSearch.fill(`${fixtures.prefix}-NO-MATCH`);
    const savedSelect = workspace.locator('.planning-saved-query');
    await chooseVisibleOption(adminPage, savedSelect, queryName, 'saved_query_loader', { scrollToEnd: true });
    await workspace.locator('.planning-card-title').filter({ hasText: fixtures.browser_task_title }).waitFor({ state: 'visible' });
    check('saved_query_restores_text_filter', true);

    await capture(adminPage, 'planning-filtered-board-zh-TW.png');
    const backlogStatusFilter = workspace.locator('.planning-toolbar .ant-select').first();
    await backlogStatusFilter.hover();
    const clearStatusFilter = backlogStatusFilter.locator('.ant-select-clear');
    await clearStatusFilter.waitFor({ state: 'visible' });
    await clearStatusFilter.click();
    check('planning_status_filter_cleared_for_backlog', await backlogStatusFilter.innerText().then(text => text.includes('全部狀態')));
    const orderSearch = workspace.locator('.planning-toolbar input').first();
    await orderSearch.fill(fixtures.order_key);
    await workspace.getByRole('tab', { name: 'Backlog 排序' }).click();
    const tableRows = workspace.locator('.ant-table-tbody tr');
    await tableRows.filter({ hasText: fixtures.order_a_key }).waitFor({ state: 'visible' });
    await tableRows.filter({ hasText: fixtures.order_b_key }).waitFor({ state: 'visible' });
    const initialRows = await tableRows.allInnerTexts();
    const initialA = initialRows.findIndex(text => text.includes(fixtures.order_a_key));
    const initialB = initialRows.findIndex(text => text.includes(fixtures.order_b_key));
    check('backlog_initial_order_fixture_visible', initialA >= 0 && initialB >= 0 && initialA !== initialB);
    const fullOrderBefore = await readJson(adminPage, `/api/tasks?project_id=${encodeURIComponent(fixtures.project_id)}`);
    const initialPositions = new Map(fullOrderBefore.map((item, index) => [item.id, index]));
    const hiddenBefore = fullOrderBefore.find(item => item.id === fixtures.order_hidden_id);
    check('backlog_hidden_fixture_starts_between_visible_tasks', initialPositions.get(fixtures.order_a_id) < initialPositions.get(fixtures.order_hidden_id) && initialPositions.get(fixtures.order_hidden_id) < initialPositions.get(fixtures.order_b_id));
    assert.ok(hiddenBefore, 'Hidden backlog fixture is unavailable');
    const moveUpKey = initialA < initialB ? fixtures.order_b_key : fixtures.order_a_key;
    const otherKey = moveUpKey === fixtures.order_a_key ? fixtures.order_b_key : fixtures.order_a_key;
    const moveUp = workspace.getByRole('button', { name: `將 ${moveUpKey} 上移` });
    const [reorderResponse] = await Promise.all([
      adminPage.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/reorder')),
      moveUp.click(),
    ]);
    check('backlog_move_up_saved', reorderResponse.ok());
    await adminPage.waitForFunction(({ moved, other }) => {
      const rows = [...document.querySelectorAll('.planning-workspace .ant-table-tbody tr')].map(row => row.innerText);
      return rows.findIndex(text => text.includes(moved)) < rows.findIndex(text => text.includes(other));
    }, { moved: moveUpKey, other: otherKey });
    check('backlog_visible_order_changed', true);
    const fullOrderAfter = await readJson(adminPage, `/api/tasks?project_id=${encodeURIComponent(fixtures.project_id)}`);
    const finalPositions = new Map(fullOrderAfter.map((item, index) => [item.id, index]));
    const hiddenAfter = fullOrderAfter.find(item => item.id === fixtures.order_hidden_id);
    check('backlog_hidden_task_stays_between_reordered_visible_tasks', finalPositions.get(fixtures.order_hidden_id) > Math.min(finalPositions.get(fixtures.order_a_id), finalPositions.get(fixtures.order_b_id)) && finalPositions.get(fixtures.order_hidden_id) < Math.max(finalPositions.get(fixtures.order_a_id), finalPositions.get(fixtures.order_b_id)));
    check('backlog_hidden_task_keeps_rank', hiddenAfter?.rank === hiddenBefore.rank);

    await workspace.getByRole('tab', { name: '規劃設定' }).click();
    const settings = workspace.locator('.planning-settings');
    await settings.getByRole('tab', { name: 'Sprint', exact: true }).click();
    const sprintName = `${fixtures.prefix} browser Sprint ${browserRunId}`;
    const addSprint = settings.locator('.planning-section-actions button').first();
    await addSprint.click();
    const sprintDialog = adminPage.locator('.ant-modal:visible').last();
    await sprintDialog.waitFor({ state: 'visible' });
    await sprintDialog.locator('.ant-form-item').filter({ hasText: '名稱' }).locator('input').fill(sprintName);
    const sprintSaveButton = sprintDialog.locator('.ant-modal-footer .ant-btn-primary');
    check('sprint_save_button_unique', await sprintSaveButton.count() === 1);
    report.sprint_submit_control = await sprintSaveButton.evaluate(button => {
      const formId = button.getAttribute('form');
      const form = formId ? document.getElementById(formId) : null;
      window.__qaSprintSubmitEvents = [];
      if (form instanceof HTMLFormElement) form.addEventListener('submit', () => window.__qaSprintSubmitEvents.push('submit'), true);
      return {
        button_type: button.getAttribute('type'),
        button_form_id: formId,
        target_is_form: form instanceof HTMLFormElement,
        target_form_id: form?.id ?? null,
      };
    });
    await capture(adminPage, 'planning-sprint-form-zh-TW.png');
    step = 'sprint_create';
    let sprintResponse;
    try {
      [sprintResponse] = await Promise.all([
        adminPage.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/sprints'), { timeout: 10000 }),
        sprintSaveButton.click(),
      ]);
    } catch (error) {
      report.sprint_form = await adminPage.evaluate(() => {
        const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
        const errors = [...(modal?.querySelectorAll('.ant-form-item-explain-error') ?? [])]
          .map(item => (item.textContent ?? '').trim()).filter(Boolean).slice(0, 10);
        const fields = [...(modal?.querySelectorAll('.ant-form-item') ?? [])].map(item => {
          const input = item.querySelector('input');
          return {
            label: (item.querySelector('.ant-form-item-label label')?.textContent ?? '').trim().slice(0, 80),
            type: input?.type ?? null,
            required: Boolean(input?.required),
            valid: input ? input.checkValidity() : null,
          };
        });
        return { visible_errors: errors, fields, submit_events: window.__qaSprintSubmitEvents ?? [] };
      }).catch(() => undefined);
      throw error;
    }
    check('sprint_created_from_browser', sprintResponse.status() === 201);
    const planningAfterSprint = await readJson(adminPage, `/api/projects/${fixtures.project_id}/planning`);
    const sprintIndex = Array.isArray(planningAfterSprint?.sprints)
      ? planningAfterSprint.sprints.findIndex(item => item?.name === sprintName)
      : -1;
    const apiHasSprint = sprintIndex >= 0;
    check('sprint_created_visible_in_planning_api', apiHasSprint);
    assert.ok(apiHasSprint, 'Created Sprint was not returned by planning API');
    await capture(adminPage, 'planning-sprint-created-zh-TW.png');
    const sprintRow = settings.locator('.ant-table-tbody tr').filter({ hasText: sprintName });
    const sprintPage = Math.floor(sprintIndex / 8) + 1;
    report.sprint_settings_page = sprintPage;
    for (let page = 2; page <= sprintPage; page += 1) {
      const nextPage = settings.locator('.ant-pagination-next');
      await nextPage.click();
      await adminPage.waitForFunction(expectedPage => {
        const active = document.querySelector('.planning-settings .ant-pagination-item-active');
        return active?.getAttribute('title') === String(expectedPage);
      }, page);
    }
    await sprintRow.waitFor({ state: 'visible' });
    check('sprint_created_row_visible_in_settings', true);

    const alice = await makeContext(browser, qaContext, 'alice'); contexts.push(alice);
    const alicePage = await alice.newPage(); pages.push(alicePage);
    await openWork(alicePage, fixtures.project_id);
    await changeLanguage(alicePage, { key: 'zh-TW', label: '繁體中文', htmlLang: 'zh-Hant' });
    await alicePage.locator('.rail-nav .nav-item').filter({ hasText: '規劃工作區' }).click();
    const aliceWorkspace = alicePage.locator('.planning-workspace');
    await aliceWorkspace.waitFor({ state: 'visible' });
    await aliceWorkspace.locator('.planning-toolbar input').first().fill(fixtures.prefix);
    const browserTaskCard = aliceWorkspace.locator('.planning-card-title').filter({ hasText: fixtures.browser_task_title });
    await browserTaskCard.waitFor({ state: 'visible' });
    await browserTaskCard.click();
    const drawer = alicePage.locator('.task-drawer');
    await drawer.waitFor({ state: 'visible' });
    const collabPanel = drawer.locator('.ant-card').filter({ hasText: '附件與協作通知' }).last();
    await collabPanel.scrollIntoViewIfNeeded();
    await collabPanel.getByText(`${fixtures.run_id}.txt`, { exact: true }).waitFor({ state: 'visible' });
    await collabPanel.getByText(fixtures.mention_body, { exact: true }).waitFor({ state: 'visible' });
    check('task_details_show_shared_attachment_and_discussion', true);
    await capture(alicePage, 'planning-task-collaboration-zh-TW.png');

    const bob = sessionFor(qaContext, 'bob');
    const aliceParticipants = await readJson(alicePage, `/api/projects/${fixtures.project_id}/participants`);
    const bobParticipant = Array.isArray(aliceParticipants) ? aliceParticipants.find(person => person.id === bob.principal_id) : null;
    assert.ok(bobParticipant?.name, 'Bob is not available as a scoped mention participant');
    const uiMention = `${fixtures.prefix} browser UI mention to Bob`;
    await collabPanel.getByLabel('協作留言').fill(uiMention);
    const mentionPicker = collabPanel.locator('.ant-select').last();
    await chooseVisibleOption(alicePage, mentionPicker, bobParticipant.name, 'collaboration_mention_picker', { closePopup: false });
    await mentionPicker.press('Escape');
    const [discussionResponse] = await Promise.all([
      alicePage.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith(`/collaboration/task/${fixtures.browser_task_id}/discussion`)),
      collabPanel.getByRole('button', { name: '傳送協作留言', exact: true }).click(),
    ]);
    check('browser_mention_message_saved', discussionResponse.status() === 201);
    await collabPanel.getByText(uiMention, { exact: true }).first().waitFor({ state: 'visible' });

    const bobContext = await makeContext(browser, qaContext, 'bob'); contexts.push(bobContext);
    const bobPage = await bobContext.newPage(); pages.push(bobPage);
    await openWork(bobPage, fixtures.project_id);
    await bobPage.getByRole('button', { name: '通知中心' }).click();
    step = 'notification_deeplink';
    const mentionNotice = bobPage.locator('.ant-list-items > .ant-list-item').filter({ hasText: uiMention }).first();
    const noticeLink = mentionNotice.locator(`a[href="/work?resource=${fixtures.browser_task_id}"]`).first();
    await noticeLink.waitFor({ state: 'visible', timeout: 30000 });
    check('bob_receives_collaboration_notification_deeplink', true);
    await noticeLink.click();
    const deepLinkDrawer = bobPage.locator('.task-drawer');
    await deepLinkDrawer.waitFor({ state: 'visible', timeout: 30000 });
    await deepLinkDrawer.getByText(fixtures.browser_task_title, { exact: false }).first().waitFor({ state: 'visible' });
    check('notification_deeplink_opens_task_details', true);
    await capture(bobPage, 'collaboration-notification-deeplink-zh-TW.png');

    const searchPage = await alice.newPage(); pages.push(searchPage);
    await openWork(searchPage, fixtures.project_id);
    await searchPage.getByRole('button', { name: '全域搜尋' }).click();
    const searchDrawer = searchPage.locator('.ant-drawer-content');
    await searchDrawer.getByRole('tab', { name: '全域搜尋', exact: true }).click();
    const globalSearch = searchDrawer.getByLabel('搜尋工作、文件與程式碼協作');
    await globalSearch.fill(fixtures.prefix);
    await globalSearch.press('Enter');
    const workResult = searchDrawer.locator(`a[href^="/work?resource=${fixtures.browser_task_id}"]`);
    const knowledgeResult = searchDrawer.locator(`a[href^="/knowledge?resource=${fixtures.knowledge_document_id}"]`);
    await workResult.waitFor({ state: 'visible', timeout: 30000 });
    await knowledgeResult.waitFor({ state: 'visible', timeout: 30000 });
    const isolatedResult = searchDrawer.locator(`a[href*="${fixtures.isolated_task_id}"]`);
    check('global_search_returns_authorized_work_and_knowledge', await workResult.count() > 0 && await knowledgeResult.count() > 0);
    check('global_search_excludes_cross_scope_work_task', await isolatedResult.count() === 0);
    await capture(searchPage, 'collaboration-global-search-zh-TW.png');

    const adminWorkspace = workspace;
    await adminWorkspace.getByRole('tab', { name: '工時與報表' }).click();
    await adminWorkspace.locator('.planning-insights .ant-table').first().waitFor({ state: 'visible' });
    check('planning_reports_and_capacity_table_render', true);
    await capture(adminPage, 'planning-reports-zh-TW.png');

    await adminWorkspace.getByRole('tab', { name: '看板' }).click();
    for (const locale of [
      { key: 'zh-CN', label: '简体中文', htmlLang: 'zh-Hans', screenshot: 'planning-board-zh-CN.png' },
      { key: 'en', label: 'English', htmlLang: 'en', screenshot: 'planning-board-en.png' },
    ]) {
      await changeLanguage(adminPage, locale);
      await adminWorkspace.locator('.planning-board').waitFor({ state: 'visible' });
      await capture(adminPage, locale.screenshot);
    }

    const mobilePage = await admin.newPage(); pages.push(mobilePage);
    await mobilePage.setViewportSize({ width: 390, height: 844 });
    await openWork(mobilePage, fixtures.project_id);
    await changeLanguage(mobilePage, { key: 'zh-TW', label: '繁體中文', htmlLang: 'zh-Hant' });
    await mobilePage.locator('.rail-nav .nav-item').filter({ hasText: '規劃工作區' }).click();
    const mobileWorkspace = mobilePage.locator('.planning-workspace');
    const mobileBoard = mobileWorkspace.locator('.planning-board');
    await mobileBoard.waitFor({ state: 'visible' });
    const mobileControlBounds = await measureCardControlBounds(mobilePage);
    report.card_control_bounds.mobile = mobileControlBounds;
    check('mobile_stage_and_status_selects_inside_card', mobileControlBounds.found && mobileControlBounds.selectsInsideBody && mobileControlBounds.selectsInsideCard && mobileControlBounds.actionsInsideBody);
    const mobileLayout = await mobilePage.evaluate(() => {
      const board = document.querySelector('.planning-board');
      const scroller = board?.parentElement;
      const card = document.querySelector('.planning-task-card');
      const cardText = card?.querySelector('.planning-card-title')?.textContent?.trim() ?? '';
      return {
        viewportWidth: window.innerWidth,
        pageWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
        boardWidth: board?.scrollWidth ?? 0,
        boardViewportWidth: scroller?.clientWidth ?? 0,
        cardVisible: Boolean(card && card.getBoundingClientRect().width > 0 && card.getBoundingClientRect().height > 0),
        cardTextReadable: cardText.length > 0,
      };
    });
    report.mobile_layout = mobileLayout;
    check('mobile_page_has_no_horizontal_overflow', mobileLayout.pageWidth <= mobileLayout.viewportWidth + 1);
    check('mobile_board_has_horizontal_scroll', mobileLayout.boardWidth > mobileLayout.boardViewportWidth);
    check('mobile_task_card_is_readable', mobileLayout.cardVisible && mobileLayout.cardTextReadable);
    await capture(mobilePage, 'planning-mobile-zh-TW.png');
    const mobileStatusFilter = mobileWorkspace.locator('.planning-toolbar .ant-select').first();
    await chooseVisibleOption(mobilePage, mobileStatusFilter, '進行中', 'mobile_status_filter');
    check('mobile_status_filter_applies', await mobileStatusFilter.innerText().then(text => text.includes('進行中')));

    report.status = 'passed';
    report.browser_errors = errors.length;
  } catch (error) {
    report.status = 'failed';
    report.failed_step = step;
    report.failure = redact(error);
    if (diagnosticPage) {
      report.diagnostics = await diagnosticPage.evaluate(() => {
        const query = document.querySelector('.planning-query-name');
        const input = query instanceof HTMLInputElement ? query : query?.querySelector('input');
        const messageText = [...document.querySelectorAll('.ant-message-notice-content')].map(item => (item.textContent ?? '').trim()).filter(Boolean);
        const save = [...document.querySelectorAll('button')].find(button => (button.textContent ?? '').includes('儲存查詢'));
        return { queryNamePresent: Boolean(input?.value), saveDisabled: Boolean(save?.disabled), messageKinds: messageText.map(text => text.includes('失敗') ? 'failure' : text.includes('成功') ? 'success' : 'other'), saveEvents: window.__qaSaveQueryEvents ?? [] };
      }).catch(() => undefined);
    }
    throw error;
  } finally {
    report.checks = checks;
    report.screenshots = screenshots;
    report.browser_errors = errors.length;
    report.dropdown_hit_diagnostics = dropdownHitDiagnostics;
    report.network_events = networkEvents;
    await fsp.mkdir(outputDir, { recursive: true });
    await fsp.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    await Promise.all(pages.map(page => page.close().catch(() => undefined)));
    await Promise.all(contexts.map(context => context.close().catch(() => undefined)));
    await browser.close();
    console.log(`P0P1_BROWSER_ACCEPTANCE_${report.status.toUpperCase()} checks=${Object.keys(checks).length} screenshots=${screenshots.length} report=.cache/p0-p1-qa/browser-report.json`);
    if (report.failure) console.log(`Failure: ${report.failure}`);
  }
}

main().catch(() => { process.exitCode = 1; });
