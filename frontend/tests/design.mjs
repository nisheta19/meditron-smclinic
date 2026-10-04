// Visual geometry + interaction checks on deterministic, fictional data.
// Actual backend/ML integration is separately verified by e2e.mjs.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createRequire } from 'node:module';
import { patients, patientCard, protocol } from './design-fixtures.mjs';
const { chromium } = createRequire(import.meta.url)('playwright');
const root = resolve(import.meta.dirname, '../..');
const base = process.env.FRONTEND_URL || 'http://127.0.0.1:3000';
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}) });
const context = await browser.newContext({ viewport: { width: 1280, height: 832 }, deviceScaleFactor: 2, timezoneId: 'Europe/Moscow' });
const page = await context.newPage();
const results = [], errors = [], unexpected = [], measurements = {};
await mkdir(resolve(root, '.local'), { recursive: true });
page.on('pageerror', (e) => errors.push(e.message));
await page.route('**/api/**', async (route) => {
  const req = route.request(), u = new URL(req.url());
  let body;
  if (req.method() !== 'GET') { unexpected.push(`${req.method()} ${u.pathname}`); return route.abort(); }
  if (u.pathname === '/api/patients') {
    body = { items: patients.slice(0, Number(u.searchParams.get('size') || 50)), total: 4, page: 0, size: 50 };
  } else if (u.pathname.startsWith('/api/patients/')) body = patientCard;
  else if (u.pathname.startsWith('/api/protocols/')) body = protocol;
  else if (u.pathname === '/api/dictionary/findings') body = [{ code: 'THYROID_NODULE', name: 'Узел щитовидной железы' }];
  else { unexpected.push(u.pathname); return route.abort(); }
  return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
});
const test = async (name, fn) => { await fn(); results.push({ name, passed: true }); console.log(`PASS ${name}`); };
const box = async (selector) => page.locator(selector).first().boundingBox();
const near = (value, target, name, tolerance = 2) => assert.ok(Math.abs(value - target) <= tolerance, `${name}: ${value}, expected ${target} ± ${tolerance}`);
const ready = async () => { await page.evaluate(() => document.fonts.ready); await page.locator('main').evaluate((el) => Promise.all(el.getAnimations({ subtree: true }).map((a) => a.finished))); };
try {
  await test('list geometry follows 1280px design', async () => {
    await page.goto(base); await page.locator('.row-card').first().waitFor(); await ready();
    measurements.list = { search: await box('.searchbar'), row: await box('.row-card'), chips: await box('.chip-row'), heads: await box('.rowlist-head') };
    near(measurements.list.search.x, 222, 'Search left'); near(measurements.list.search.y, 25, 'Search top');
    near(measurements.list.search.height, 64, 'Search height'); near(measurements.list.chips.y, 111, 'Chips top');
    near(measurements.list.row.x, 222, 'Row left'); near(measurements.list.row.y, 205, 'Row top');
    near(measurements.list.row.height, 102, 'Row height');
    assert.equal(await page.locator('.row-card').count(), 4);
    const rows = await page.locator('.row-card').evaluateAll((els) => els.map((el) => ({ y: el.getBoundingClientRect().y, height: el.getBoundingClientRect().height })));
    rows.forEach((row, i) => { near(row.y, [205, 313, 432, 538][i], `Row ${i + 1} top`); near(row.height, [102, 113, 100, 100][i], `Row ${i + 1} height`); });
    assert.ok(await page.evaluate(() => document.fonts.check('14px "Inter Variable"')));
  });
  await test('selection and unavailable booking filters', async () => {
    const chosen = page.getByRole('checkbox').nth(3); await chosen.click();
    assert.equal(await chosen.getAttribute('aria-checked'), 'true');
    assert.equal(await page.locator('.cbx-dash').count(), 0);
    assert.ok(!page.url().includes('/patients/'));
    for (const label of ['Просрочена запись', 'Без записи']) assert.ok(await page.getByRole('tab', { name: new RegExp(`^${label}`) }).isDisabled());
    await page.screenshot({ path: resolve(root, '.local/design-list.png'), fullPage: true });
    await chosen.focus(); await page.keyboard.press('Enter'); assert.ok(!page.url().includes('/patients/'));
  });
  await test('patient sheet geometry and evidence', async () => {
    await page.setViewportSize({ width: 1280, height: 1464 });
    await page.goto(`${base}/#/patients/design-0`); await page.locator('.pc-protocol mark').first().waitFor(); await ready();
    measurements.card = { search: await box('.searchbar'), sheet: await box('.pc-grid'), history: await box('.pc-history'), info: await box('.pc-info'), text: await box('.pc-protocol'), head: await box('.pc-head'), person: await box('.pc-person'), name: await box('.pc-person h3'), contacts: await box('.pc-contacts'), identifier: await box('.pc-id') };
    near(measurements.card.sheet.x, 212, 'Sheet left'); near(measurements.card.sheet.y, 169, 'Sheet top');
    near(measurements.card.sheet.width, 1052, 'Sheet width'); near(measurements.card.history.x, 980, 'History divider');
    near(measurements.card.text.x, 225, 'Protocol left'); near(measurements.card.text.width, 727, 'Protocol width');
    near(measurements.card.text.y, 485, 'Protocol top');
    assert.equal(await page.locator('.pc-protocol .protocol-text').innerText(), protocol.text);
    assert.equal(await page.locator('.pc-events > *').count(), 10);
    await page.screenshot({ path: resolve(root, '.local/design-patient.png'), fullPage: true });
  });
  await test('route controls are inert, history and close work', async () => {
    const buttons = page.locator('.route-placeholder button');
    for (let i = 0; i < await buttons.count(); i++) assert.ok(await buttons.nth(i).isDisabled());
    assert.ok(await page.getByRole('button', { name: 'Дашборд', exact: true }).isDisabled());
    await page.locator('.pc-history-more').click(); assert.equal(await page.locator('.pc-events > *').count(), 11);
    await page.getByRole('button', { name: 'Закрыть карточку' }).click(); await page.locator('.row-card').first().waitFor();
    assert.ok(page.url().endsWith('/findings'));
  });
  await test('no horizontal overflow from phone to wide desktop', async () => {
    for (const width of [390, 768, 1024, 1280, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      for (const path of ['findings', 'patients/design-0']) {
        await page.goto(`${base}/#/${path}`); await page.locator(path === 'findings' ? '.row-card' : '.pc-protocol').first().waitFor(); await ready();
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${path} overflows at ${width}px`);
        if (width === 390) await page.screenshot({ path: resolve(root, `.local/design-${path === 'findings' ? 'list' : 'patient'}-mobile.png`), fullPage: true });
      }
    }
  });
  await test('urgent and flagged data never add decorations outside the mockup', async () => {
    await page.setViewportSize({ width: 1280, height: 900 });
    for (const level of ['EMERGENCY', 'URGENT']) {
      patients.forEach((p) => { p.maxLevel = level; p.activeFindings = 3; });
      await page.goto(`${base}/#/findings`); await page.locator('.row-card').first().waitFor(); await ready();
      assert.equal(await page.locator('.row-card .badge, .row-card .lvl, .row-card small').count(), 0);
      const styles = await page.locator('.row-card').evaluateAll((rows) => rows.map((el) => ({ shadow: getComputedStyle(el).boxShadow, border: getComputedStyle(el).borderLeftWidth })));
      assert.ok(styles.every((s) => s.shadow === 'none' && s.border === '0px'));
      assert.ok(!(await page.locator('.rowlist').innerText()).match(/Экстренно|Срочно|Новые находки|Этап не задан|Нет данных/u));
    }
    protocol.flags = [{ code: 'INCOMPLETE', note: 'Синтетический флаг', setBy: 'ML' }];
    protocol.conclusionFound = false;
    protocol.notTriggered = [{ code: 'THYROID_NODULE', reason: 'BELOW_THRESHOLD', evidence: patientCard.currentFindings[0].evidence }];
    for (const status of ['SUGGESTED', 'CONFIRMED', 'REJECTED']) {
      patientCard.currentFindings.forEach((f) => Object.assign(f, { status, level: 'EMERGENCY', source: 'MANUAL', flags: protocol.flags }));
      await page.goto(`${base}/#/patients/design-0`); await page.locator('.pc-protocol mark').first().waitFor(); await ready();
      assert.equal(await page.locator('.pc-main .tag, .pc-main .lvl, .pc-main .pc-note, .pc-main .pc-all, .pc-main .pc-nt, .pc-main .pc-flags, .pc-main mark.nt').count(), 0);
      assert.equal(await page.locator('.pc-head button').count(), 0);
      assert.deepEqual(await page.locator('.pc-fname').allTextContents(), patientCard.currentFindings.map((f) => f.name));
      assert.ok(!(await page.locator('.pc-main').innerText()).match(/экстренно|ждёт проверки|добавлена врачом|Подтвердить все|текущий|Синтетический флаг/u));
    }
    await page.locator('.pc-more').click();
    assert.ok((await page.getByRole('dialog').innerText()).includes('Синтетический флаг'));
    assert.ok((await page.getByRole('dialog').innerText()).includes('не найдено заключение'));
    assert.equal(await page.getByRole('dialog').locator('.pc-nt').count(), 1);
  });
  await test('no JavaScript errors or unsupported API requests', async () => { assert.deepEqual(errors, []); assert.deepEqual(unexpected, []); });
} catch (e) {
  measurements.overflow = await page.evaluate(() => [...document.querySelectorAll('main *')].map((el) => ({ tag: el.tagName, cls: el.className, x: el.getBoundingClientRect().x, width: el.getBoundingClientRect().width, right: el.getBoundingClientRect().right })).filter((el) => el.right > innerWidth + 1));
  results.push({ name: 'failure', passed: false, message: e.stack }); console.error(e); process.exitCode = 1;
  await page.screenshot({ path: resolve(root, '.local/design-failure.png'), fullPage: true });
} finally {
  await writeFile(resolve(root, '.local/design-results.json'), JSON.stringify({ results, measurements, errors, unexpected }, null, 2));
  await browser.close();
}
