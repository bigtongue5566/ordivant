'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const fsSync = require('node:fs');
const path = require('node:path');
const { chromium } = require(path.resolve('.cache/browser-qa/node_modules/playwright'));

const ROOT = path.resolve(__dirname, '..');
const QA_URL = 'http://127.0.0.1:8096';
const QA_DIR = path.join(ROOT, '.cache', 'p0-p1-qa');
const PRIVATE_FIXTURE = path.join(QA_DIR, 'code-governance-context.json');
const SHARED_CONTEXT = path.join(ROOT, '.cache', 'collaboration-qa', 'context.json');
const API_REPORT = path.join(QA_DIR, 'code-governance-api-report.json');
const REPORT = path.join(QA_DIR, 'code-governance-browser-report.json');
const SCREENSHOTS = path.join(QA_DIR, 'screenshots');
const chromeCandidates = [
  path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
  path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe'),
];
const chromeExecutable = chromeCandidates.find((file) => fsSync.existsSync(file));
const locales = [
  { key: 'zh-TW', label: '繁體中文', lang: 'zh-Hant' },
  { key: 'zh-CN', label: '简体中文', lang: 'zh-Hans' },
  { key: 'en', label: 'English', lang: 'en' },
];
const checks = {};
const screenshots = [];
const errors = [];
const sensitiveValues = [];
let pageErrors = 0;
let step = 'initialize';

function check(name, value) {
  checks[name] = Boolean(value);
  assert.ok(value, name);
}

function safeError(error) {
  let message = error instanceof Error ? error.message : String(error);
  message = message.split('\n')[0]
    .replace(/https?:\/\/[^\s]+/g, '[url]')
    .replace(/(cookie|csrf|token|password|authorization)\s*[:=]\s*[^\s,;]+/gi, '$1=[redacted]')
    .replace(/\b[a-f0-9]{8}-[a-f0-9-]{27,}\b/gi, '[id]')
    .replace(/locator\([^)]*\)/g, 'locator');
  for (const value of sensitiveValues) if (value) message = message.split(value).join('[redacted]');
  return message.slice(0, 260);
}

function account(context, name) {
  const user = context?.users?.[name];
  assert.ok(user && typeof user.cookie_name === 'string' && typeof user.cookie_value === 'string', `missing QA ${name} browser session`);
  sensitiveValues.push(user.cookie_value);
  return user;
}

async function browserContext(browser, source, name) {
  const session = account(source, name);
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-TW' });
  await context.addCookies([{ name: session.cookie_name, value: session.cookie_value, url: QA_URL, httpOnly: true }]);
  context.on('page', (page) => page.on('pageerror', () => { pageErrors += 1; }));
  return context;
}

async function chooseVisibleOption(page, select, text, name) {
  step = name;
  await select.click();
  const popup = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last();
  await popup.waitFor({ state: 'visible' });
  const option = popup.locator('.ant-select-item-option').filter({ hasText: text }).first();
  await option.waitFor({ state: 'visible' });
  const box = await option.boundingBox();
  const viewport = page.viewportSize();
  check(`${name}_dropdown_in_view`, Boolean(box && viewport && box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1));
  const hitTest = await option.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return Boolean(hit && element.contains(hit));
  });
  check(`${name}_dropdown_hit_test`, hitTest);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await popup.waitFor({ state: 'hidden' });
}

async function setLanguage(page, locale) {
  if (await page.locator('html').getAttribute('lang') !== locale.lang) {
    await chooseVisibleOption(page, page.locator('.language-control .ant-select'), locale.label, `language_${locale.key}`);
    await page.waitForFunction((expected) => document.documentElement.lang === expected, locale.lang);
  }
  check(`language_${locale.key}_applied`, true);
}

async function capture(page, name) {
  const filename = `code-governance-${name}.png`;
  await page.screenshot({ path: path.join(SCREENSHOTS, filename), fullPage: false });
  screenshots.push(filename);
}

async function waitForPullData(drawer, runId) {
  step = 'wait_governance_readiness';
  await drawer.locator('.code-upstream-readiness').waitFor({ state: 'visible', timeout: 30000 });
  step = 'wait_inline_sha';
  await drawer.locator('.code-inline-review .code-inline-sha').waitFor({ state: 'visible', timeout: 30000 });
  step = 'wait_inline_comment';
  await drawer.locator('.code-inline-review').getByText(`QA inline ${runId}`).waitFor({ state: 'attached', timeout: 30000 });
  const collaboration = drawer.locator('.code-pr-collaboration');
  step = 'wait_local_human_comment';
  await collaboration.getByText(`QA local human comment ${runId}`).waitFor({ state: 'attached', timeout: 30000 });
  step = 'wait_local_agent_comment';
  await collaboration.getByText(`QA local Agent comment ${runId}`).waitFor({ state: 'attached', timeout: 30000 });
  step = 'wait_shared_agent_discussion';
  await drawer.locator('.ant-card').getByText(`QA Agent discussion ${runId}`).waitFor({ state: 'attached', timeout: 30000 });
}

async function main() {
  await fs.mkdir(SCREENSHOTS, { recursive: true });
  const [source, privateContext, apiReport] = await Promise.all([
    fs.readFile(SHARED_CONTEXT, 'utf8').then(JSON.parse),
    fs.readFile(PRIVATE_FIXTURE, 'utf8').then(JSON.parse),
    fs.readFile(API_REPORT, 'utf8').then(JSON.parse),
  ]);
  const fixture = privateContext?.code;
  check('only_isolated_qa_host', source.base_url === QA_URL && privateContext.base_url === QA_URL);
  check('private_gitea_fixture_ready', Boolean(fixture?.repository_id && fixture?.pull_id && fixture?.pull_number && fixture?.branches?.base && fixture?.project_key));
  check('api_evidence_reports_no_actions_runs', apiReport.status === 'passed' && apiReport.evidence?.actions?.run_count === 0);
  check('api_evidence_reports_no_deployment_provider', apiReport.evidence?.deployments?.available === false && apiReport.evidence?.deployments?.item_count === 0);
  const managerName = fixture.manager_name;
  account(source, managerName);
  account(source, 'reader');

  const browser = await chromium.launch({ headless: true, ...(chromeExecutable ? { executablePath: chromeExecutable } : {}) });
  const contexts = [];
  try {
    const managerContext = await browserContext(browser, source, managerName);
    contexts.push(managerContext);
    const managerPage = await managerContext.newPage();
    step = 'manager_open_code';
    await managerPage.goto(`${QA_URL}/code`, { waitUntil: 'domcontentloaded' });
    await managerPage.locator('.language-control').waitFor({ state: 'visible' });
    await managerPage.locator('.product-scope-select').waitFor({ state: 'visible' });
    await chooseVisibleOption(managerPage, managerPage.locator('.product-scope-select'), fixture.project_key, 'code_project');
    const selectedProject = await managerPage.locator('.product-scope-select .ant-select-selection-item').innerText();
    check('code_project_selected_in_scope', selectedProject.includes(fixture.project_key));

    step = 'manager_open_governance_pull';
    await managerPage.goto(`${QA_URL}/code?kind=pull&resource=${encodeURIComponent(fixture.pull_id)}`, { waitUntil: 'domcontentloaded' });
    const drawer = managerPage.locator('.code-pr-drawer');
    await drawer.locator('.pull-detail').waitFor({ state: 'visible', timeout: 30000 });
    const governance = drawer.locator('.code-upstream-governance');
    await governance.waitFor({ state: 'visible' });
    await waitForPullData(drawer, privateContext.run_id);
    await governance.locator('.code-policy-editor').waitFor({ state: 'visible' });
    check('pull_deep_link_opened_governance_view', await drawer.locator('.pull-detail').isVisible() && await governance.isVisible());

    step = 'manager_change_real_branch_policy';
    const policyEditor = governance.locator('.code-policy-editor');
    const outdatedToggle = policyEditor.locator('.ant-checkbox-wrapper').filter({ hasText: '阻擋未同步目標分支的 PR' });
    await outdatedToggle.waitFor({ state: 'visible' });
    const toggleInput = outdatedToggle.locator('input[type="checkbox"]');
    if (!(await toggleInput.isChecked())) await outdatedToggle.click();
    const saveResponse = managerPage.waitForResponse((response) => {
      const request = response.request();
      return request.method() === 'PATCH' && new URL(response.url()).pathname.endsWith('/branch-protection');
    }, { timeout: 20000 });
    await policyEditor.getByRole('button', { name: '儲存上游規則' }).click();
    const saved = await saveResponse;
    check('policy_editor_saved_to_gitea', saved.status() === 200);
    await managerPage.waitForFunction(async ({ repositoryId, branch }) => {
      try {
        const response = await fetch(`/code-api/api/repositories/${encodeURIComponent(repositoryId)}/branch-protection?branch=${encodeURIComponent(branch)}`, { credentials: 'same-origin', cache: 'no-store' });
        if (!response.ok) return false;
        const data = await response.json();
        return data.available === true && data.protection?.block_on_outdated_branch === true;
      } catch { return false; }
    }, { repositoryId: fixture.repository_id, branch: fixture.branches.base }, { timeout: 20000 });
    await managerPage.waitForFunction(() => !document.querySelector('.code-policy-editor .ant-btn-loading'), undefined, { timeout: 20000 });
    check('branch_policy_readback_matches_gitea', true);

    for (const [index, locale] of locales.entries()) {
      step = `locale_${locale.key}`;
      if (index > 0) {
        await managerPage.locator('.code-pr-drawer .ant-drawer-close').click();
        await managerPage.locator('.code-pr-drawer').waitFor({ state: 'hidden' });
      }
      await setLanguage(managerPage, locale);
      if (index > 0) {
        await managerPage.goto(`${QA_URL}/code?kind=pull&resource=${encodeURIComponent(fixture.pull_id)}`, { waitUntil: 'domcontentloaded' });
        await managerPage.locator('.code-pr-drawer .pull-detail').waitFor({ state: 'visible', timeout: 30000 });
        await waitForPullData(managerPage.locator('.code-pr-drawer'), privateContext.run_id);
      }
      const localizedGovernance = managerPage.locator('.code-pr-drawer .code-upstream-governance');
      await localizedGovernance.waitFor({ state: 'visible' });
      await localizedGovernance.scrollIntoViewIfNeeded();
      const text = await localizedGovernance.innerText();
      check(`governance_${locale.key}_content_visible`, text.trim().length > 0);
      const expectedMissingStatus = { 'zh-TW': '尚未回報', 'zh-CN': '尚未回报', en: 'Not reported' }[locale.key];
      const requiredCheckText = await localizedGovernance.locator('.code-upstream-check').first().innerText();
      check(`governance_${locale.key}_missing_status_localized`, requiredCheckText.includes(expectedMissingStatus) && !/\bmissing\b/i.test(requiredCheckText));
      const actionsHeading = localizedGovernance.locator('.code-upstream-subhead').filter({ hasText: 'Gitea Actions' });
      check(`governance_${locale.key}_empty_actions_are_not_fabricated`, await localizedGovernance.locator('.code-upstream-run').count() === 0 && /\b0\b/.test(await actionsHeading.innerText()));
      const deploymentUnavailableText = { 'zh-TW': '沒有可驗證的部署結果', 'zh-CN': '没有可验证的部署结果', en: 'No verifiable deployment results' }[locale.key];
      check(`governance_${locale.key}_unconfigured_deployment_is_explicit`, await localizedGovernance.getByText(deploymentUnavailableText).count() > 0);
      if (locale.key === 'en') check('governance_en_has_no_chinese', !/[\u3400-\u9fff]/u.test(text));
      await capture(managerPage, `${privateContext.run_id}-${locale.key}`);
    }

    const readerContext = await browserContext(browser, source, 'reader');
    contexts.push(readerContext);
    const readerPage = await readerContext.newPage();
    step = 'reader_open_same_pull';
    await readerPage.goto(`${QA_URL}/code?kind=pull&resource=${encodeURIComponent(fixture.pull_id)}`, { waitUntil: 'domcontentloaded' });
    const readerDrawer = readerPage.locator('.code-pr-drawer');
    await readerDrawer.locator('.pull-detail').waitFor({ state: 'visible', timeout: 30000 });
    await waitForPullData(readerDrawer, privateContext.run_id);
    await readerDrawer.locator('.code-inline-review .code-collaboration-readonly').waitFor({ state: 'visible' });
    check('reader_can_read_pull_and_inline_discussion', await readerDrawer.locator('.code-upstream-governance').isVisible());
    check('reader_has_no_policy_editor', await readerDrawer.locator('.code-policy-editor').count() === 0);
    check('reader_has_no_discussion_or_review_submit_controls', await readerDrawer.locator('button').filter({ hasText: /送出討論|送出審查記錄|Submit comment|Submit review/i }).count() === 0);
    await readerDrawer.locator('.code-pr-collaboration').scrollIntoViewIfNeeded();
    await capture(readerPage, `${privateContext.run_id}-reader`);
    await readerPage.close();
    await managerPage.close();

    check('browser_pages_have_no_javascript_errors', pageErrors === 0);
    const report = {
      status: 'passed',
      target: QA_URL,
      fixture_run_id: privateContext.run_id,
      checks,
      screenshots,
      page_errors: pageErrors,
    };
    await fs.writeFile(REPORT, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    process.stdout.write(`CODE_GOVERNANCE_BROWSER_PASSED checks=${Object.keys(checks).length} screenshots=${screenshots.length} report=.cache/p0-p1-qa/code-governance-browser-report.json\n`);
  } catch (error) {
    errors.push({ step, message: safeError(error) });
    const report = {
      status: 'failed',
      target: QA_URL,
      fixture_run_id: privateContext.run_id,
      checks,
      screenshots,
      page_errors: pageErrors,
      errors,
    };
    await fs.writeFile(REPORT, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    process.stderr.write(`CODE_GOVERNANCE_BROWSER_FAILED step=${step} reason=${errors[0].message}\n`);
    process.exitCode = 1;
  } finally {
    for (const context of contexts) await context.close().catch(() => undefined);
    await browser.close().catch(() => undefined);
  }
}

main().catch(async (error) => {
  const message = safeError(error);
  await fs.mkdir(QA_DIR, { recursive: true });
  await fs.writeFile(REPORT, `${JSON.stringify({ status: 'failed', target: QA_URL, checks, screenshots, page_errors: pageErrors, errors: [{ step, message }] }, null, 2)}\n`, 'utf8').catch(() => undefined);
  process.stderr.write(`CODE_GOVERNANCE_BROWSER_FAILED step=${step} reason=${message}\n`);
  process.exitCode = 1;
});
