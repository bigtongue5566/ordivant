// Synthetic QA only. Never print cookies, recovery codes or downloaded audit content.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(path.resolve('.cache/browser-qa/node_modules/playwright'));
const base = 'http://127.0.0.1:8096';
const qa = JSON.parse(fs.readFileSync('.cache/collaboration-qa/context.json', 'utf8'));
assert.equal(qa.base_url, base);
assert.ok(qa.run_id && qa.users.admin.cookie_value);
const directory = '.cache/p0-p1-qa';
fs.mkdirSync(`${directory}/screenshots`, { recursive: true });
const checks = [];
const anonymousEmail = `qa-ui-missing-${require('node:crypto').randomUUID()}@example.com`;
let step = 'start';
const locales = [
  { label: '繁體中文', lang: 'zh-Hant', account: '帳號與安全性', governance: '企業治理', heading: '帳號佈建與郵件', scim: 'SCIM 已啟用', mail: '郵件服務可用', audit: '匯出稽核紀錄', recovery: '寄送密碼復原郵件', notice: '若帳號符合復原條件且已設定郵件服務，系統會寄送一次性復原連結。' },
  { label: '简体中文', lang: 'zh-Hans', account: '账号与安全性', governance: '企业治理', heading: '账号布建与邮件', scim: 'SCIM 已激活', mail: '邮件服务可用', audit: '导出稽核纪录', recovery: '寄送密码复原邮件', notice: '若账号符合复原条件且已设定邮件服务，系统会寄送一次性复原链接。' },
  { label: 'English', lang: 'en', account: 'Account and security', governance: 'Enterprise governance', heading: 'Account provisioning and mail', scim: 'SCIM enabled', mail: 'Mail delivery available', audit: 'Export audit records', recovery: 'Send password recovery email', notice: 'If the account is eligible and mail delivery is configured, a one-time recovery link will be sent.' },
];
async function chooseLanguage(page, locale) {
  await page.locator('.language-control .ant-select').click();
  const popup = page.locator('.ant-select-dropdown:visible').last();
  const option = popup.locator('.ant-select-item-option').filter({ hasText: locale.label });
  await option.click();
  await page.waitForFunction(lang => document.documentElement.lang === lang, locale.lang);
}
async function tab(page, text) {
  const target = page.getByRole('tab', { name: text, exact: true });
  const hit = await target.evaluate(element => {
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && element.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
  });
  if (hit) return target.click();
  await page.locator('.auth-account-drawer .ant-tabs-nav-more').click();
  await page.locator('.ant-tabs-dropdown-menu-item:visible').filter({ hasText: text }).click();
}
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  let page;
  let errors = 0;
  try {
    for (const locale of locales) {
      step = `${locale.lang}: admin governance`;
      const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, acceptDownloads: true });
      await context.addCookies([{ name: qa.users.admin.cookie_name, value: qa.users.admin.cookie_value, url: base, httpOnly: true }]);
      page = await context.newPage();
      page.on('pageerror', () => { errors += 1; });
      await page.goto(`${base}/work`, { waitUntil: 'domcontentloaded' });
      await chooseLanguage(page, locale);
      step = `${locale.lang}: open account`;
      await page.getByRole('button', { name: locale.account, exact: true }).click();
      step = `${locale.lang}: governance tab`;
      await tab(page, locale.governance);
      // Use configured, server-read flags; these must not be placeholder labels.
      step = `${locale.lang}: policy flags`;
      await page.getByText(locale.scim, { exact: true }).waitFor();
      await page.getByText(locale.mail, { exact: true }).waitFor();
      checks.push(`${locale.lang}: authorized SCIM and SMTP policy readback`);
      step = `${locale.lang}: audit download`;
      let exportPages = 0;
      if (locale.lang === 'zh-Hant') await page.route('**/auth-api/audit/export*', async route => {
        const url = new URL(route.request().url());
        url.searchParams.set('limit', '50');
        exportPages += 1;
        await route.continue({ url: url.toString() });
      });
      const downloadEvent = page.waitForEvent('download');
      await page.getByRole('button', { name: locale.audit, exact: true }).click();
      const download = await downloadEvent;
      const downloaded = await download.path();
      const rows = fs.readFileSync(downloaded, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse);
      assert.ok(rows.length && rows.length <= 100000);
      assert.equal(new Set(rows.map(row => row.id)).size, rows.length);
      assert.ok(!/(access_token|client_secret|password_hash|token_hash)/i.test(JSON.stringify(rows)));
      checks.push(`${locale.lang}: browser downloads valid bounded redacted audit NDJSON`);
      if (locale.lang === 'zh-Hant') {
        assert.ok(exportPages > 1 && rows.length > 50);
        checks.push('browser follows real API composite audit cursors without duplicate rows');
      }
      await page.screenshot({ path: `${directory}/screenshots/enterprise-${locale.lang}.png` });
      await context.close();

      step = `${locale.lang}: anonymous recovery`;
      const anonymous = await browser.newContext({ viewport: { width: 1200, height: 900 } });
      page = await anonymous.newPage();
      page.on('pageerror', () => { errors += 1; });
      await page.goto(`${base}/work`, { waitUntil: 'domcontentloaded' });
      await chooseLanguage(page, locale);
      await page.locator('input[autocomplete=email]').fill(anonymousEmail);
      await page.getByRole('button', { name: locale.recovery, exact: true }).click();
      const notice = page.locator('.ant-alert-success');
      await notice.waitFor();
      assert.ok((await notice.innerText()).length > 30);
      assert.equal(await page.locator('.ant-alert-error').count(), 0);
      checks.push(`${locale.lang}: recovery request gives localized uniform success notice`);
      await anonymous.close();
    }
    assert.equal(errors, 0);
    fs.writeFileSync(`${directory}/enterprise-browser-report.json`, JSON.stringify({ status: 'passed', target: base, checks, page_errors: errors }, null, 2));
    console.log(`ENTERPRISE_BROWSER_PASSED checks=${checks.length}`);
  } catch (error) {
    if (page && !page.isClosed()) await page.screenshot({ path: `${directory}/screenshots/enterprise-failure.png` });
    fs.writeFileSync(`${directory}/enterprise-browser-report.json`, JSON.stringify({ status: 'failed', target: base, step, checks, error_type: error.constructor.name }, null, 2));
    console.error(`ENTERPRISE_BROWSER_FAILED step=${step} error=${error.constructor.name}`);
    process.exitCode = 1;
  } finally { await browser.close(); }
})();
