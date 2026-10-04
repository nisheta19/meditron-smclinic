// Requires a running demo stack, Playwright, and tests/frontend_fixtures.py.
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');
const root = resolve(import.meta.dirname, '../..');
const fixture = JSON.parse(await readFile(process.env.UI_FIXTURES || resolve(root, '.local/frontend-fixtures.json'), 'utf8'));
const base = process.env.FRONTEND_URL || fixture.frontend;
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}) });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(12000);
const errors = [], badResponses = [], patientQueries = [], results = [];
let expectedFailure = false;
page.on('pageerror', (e) => errors.push(e.message));
page.on('response', (r) => { if (!expectedFailure && r.status() >= 400) badResponses.push(`${r.status()} ${r.url()}`); });
page.on('request', (r) => { const u = new URL(r.url()); if (u.pathname === '/api/patients') patientQueries.push(u.searchParams); });
const api = async (path) => { const r = await context.request.get(`${base}${path}`); assert.equal(r.status(), 200); return r.json(); };
const until = async (fn) => { const end = Date.now() + 12000; while (true) { if (await fn()) return; if (Date.now() > end) throw Error('Condition timed out'); await new Promise((r) => setTimeout(r, 100)); } };
const test = async (name, fn) => { await fn(); results.push({ name, passed: true }); console.log(`PASS ${name}`); };
const card = async (key) => {
  await page.goto(`${base}/#/patients/${fixture.cases[key].id}`);
  await page.locator('.pc-info h3').waitFor();
  await until(async () => !(await page.locator('.pc-protocol').innerText()).includes('Загружаем'));
};
const search = async (text) => { await page.getByRole('searchbox').fill(text); await page.getByRole('button', { name: 'Найти', exact: true }).click(); };
try {
  await test('real API, server order, pagination and search', async () => {
    await page.goto(base);
    await page.locator('.row-card').first().waitFor();
    assert.equal(await page.locator('.demo').count(), 0);
    const server = await api('/api/patients?size=50&page=0');
    assert.equal(await page.locator('.row-card').count(), server.items.length);
    assert.ok((await page.locator('.row-card').first().innerText()).includes(server.items[0].fullName));
    if (server.total > 50) {
      await page.getByRole('button', { name: 'Далее', exact: true }).click();
      await until(async () => (await page.locator('.pagination').innerText()).includes('Страница 2'));
      const second = await api('/api/patients?size=50&page=1');
      await until(async () => (await page.locator('.row-card').first().innerText()).includes(second.items[0].fullName));
    }
    await search(fixture.cases.positive.externalId);
    await until(async () => await page.locator('.row-card').count() === 1);
    await page.locator('.row-card').click();
    await page.locator('.pc-info h3').waitFor();
    assert.ok(page.url().endsWith(fixture.cases.positive.id));
  });
  await test('new ML result appears without page reload', async () => {
    const event = fixture.autoRefreshEvent;
    await page.goto(`${base}/#/findings`);
    await search(event.patient.externalId);
    await until(async () => (await page.locator('.row-empty').innerText()).includes('Пациентов не найдено'));
    const response = await context.request.post(`${base}/api/integration/events`, { data: event });
    assert.equal(response.status(), 202);
    await page.locator('.row-card').waitFor();
    assert.ok((await page.locator('.row-card').innerText()).includes(event.patient.fullName));
  });
  await test('Unicode quote highlighting and real routing deadline', async () => {
    await card('positive');
    const f = fixture.cases.positive.findings[0];
    const marks = page.locator(`[data-evidence-ids~="ev-${f.id}"]`);
    assert.equal((await marks.allTextContents()).join(''), f.evidence.text);
    await page.locator('.pc-row-main').first().click();
    assert.ok((await page.locator('.pc-detail').innerText()).includes('В течение 7 дней'));
    assert.equal(await page.getByRole('button', { name: 'Уведомить пациента', exact: true }).count(), 0);
    await page.screenshot({ path: resolve(root, '.local/frontend-patient-desktop.png'), fullPage: true });
  });
  await test('confirm finding persists in PostgreSQL', async () => {
    await page.getByRole('button', { name: /^Подтвердить:/ }).first().click();
    await until(async () => (await api(`/api/patients/${fixture.cases.positive.id}`)).currentFindings[0].status === 'CONFIRMED');
    await page.reload();
    await page.locator('.pc-row.confirmed').waitFor();
  });
  await test('manual fields follow YAML, typed BI-RADS, remove finding', async () => {
    await card('breast');
    await page.getByRole('button', { name: '+ Добавить', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Добавить находку', exact: true });
    await dialog.getByRole('option').filter({ hasText: 'BREAST_LESION' }).click();
    await dialog.getByLabel('BI-RADS', { exact: true }).fill('4');
    await dialog.getByLabel('Сторона', { exact: true }).selectOption('right');
    await dialog.getByLabel('Размер, мм', { exact: true }).fill('15');
    await dialog.getByLabel('Под вопросом', { exact: true }).selectOption('false');
    await dialog.getByRole('button', { name: 'Добавить находку', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    let manual;
    await until(async () => { manual = (await api(`/api/patients/${fixture.cases.breast.id}`)).currentFindings.find((f) => f.source === 'MANUAL'); return !!manual; });
    assert.equal(manual.attributes.birads, 4); assert.equal(manual.attributes.side, 'right'); assert.equal(manual.attributes.sizeMm, 15);
    assert.equal(manual.attributes.uncertain, false);
    assert.equal('category' in manual.attributes, false);
    const row = page.locator(`[data-finding-id="${manual.id}"]`);
    await row.getByRole('button', { name: /^Удалить:/ }).click();
    await page.getByRole('dialog').getByLabel('Причина').fill('Проверка интерфейса');
    await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click();
    await until(async () => !(await api(`/api/patients/${fixture.cases.breast.id}`)).currentFindings.some((f) => f.id === manual.id));
  });
  await test('reject finding with comment', async () => {
    await card('breast');
    await page.getByRole('button', { name: /^Отклонить:/ }).first().click();
    await page.getByRole('dialog').getByLabel('Комментарий врача').fill('Синтетическая проверка');
    await page.getByRole('dialog').getByRole('button', { name: 'Отклонить', exact: true }).click();
    await until(async () => (await api(`/api/patients/${fixture.cases.breast.id}`)).currentFindings.some((f) => f.status === 'REJECTED' && f.comment === 'Синтетическая проверка'));
  });
  await test('failed and annulled documents are not shown as normal', async () => {
    for (const key of ['failed', 'annulled']) {
      await card(key);
      assert.ok(await page.getByRole('button', { name: '+ Добавить', exact: true }).isDisabled());
      const text = await page.locator('.pc-main').innerText();
      assert.ok(text.includes(key === 'failed' ? 'Извлечь находки не удалось' : 'Протокол аннулирован'));
      assert.ok(!text.includes('Значимых находок нет'));
    }
  });
  await test('missing conclusion warning and normal notTriggered', async () => {
    await card('missing'); await page.locator('.pc-more').click();
    assert.ok((await page.getByRole('dialog').innerText()).includes('не найдено заключение'));
    await page.getByRole('dialog').getByRole('button', { name: 'Закрыть', exact: true }).first().click();
    await card('normal'); assert.equal(await page.locator('.findings-table .pc-row').count(), 0);
    assert.equal(await page.locator('.pc-main .pc-nt').count(), 0);
    await page.locator('.pc-more').click(); assert.ok(await page.getByRole('dialog').locator('.pc-nt').count());
    await page.getByRole('dialog').getByRole('button', { name: 'Закрыть', exact: true }).first().click();
  });
  await test('previous version read-only, independent old protocol editable', async () => {
    for (const key of ['versions', 'independent']) {
      await card(key);
      await page.locator('.pc-event').last().click();
      await until(async () => (await page.locator('.pc-protocol').innerText()).includes('8 мм'));
      await until(async () => await page.getByRole('button', { name: '+ Добавить', exact: true }).isEnabled() === (key === 'independent'));
    }
  });
  await test('dictionary has 48 codes, code search, no unsupported actions', async () => {
    await page.goto(`${base}/#/settings`);
    await until(async () => await page.locator('.row-card').count() === 48);
    assert.equal(await page.getByRole('button', { name: 'Добавить тип находки' }).count(), 0);
    await search('BREAST_LESION');
    await until(async () => await page.locator('.row-card').count() === 1);
    assert.ok((await page.locator('.row-card').innerText()).includes('BREAST_LESION'));
  });
  await test('emergency and attention filters', async () => {
    await page.goto(`${base}/#/findings`);
    await page.getByRole('tab', { name: /^Экстренные/ }).click();
    await until(async () => await page.locator('.row-card').count() > 0);
    await until(async () => await page.locator('.row-card:not(.emergency)').count() === 0);
    await search(fixture.cases.emergency.externalId);
    await until(async () => await page.locator('.row-card').count() === 1);
    assert.ok((await page.locator('.row-card').innerText()).includes('Немедленно'));
    await page.goto(`${base}/#/inbox`);
    await page.getByRole('tab', { name: /^Требует внимания/ }).click();
    await search(fixture.cases.failed.externalId);
    await until(async () => await page.locator('.row-card').count() === 1);
  });
  await test('protocol HTTP error visible and retry restores it', async () => {
    expectedFailure = true;
    const pattern = `**/api/protocols/${fixture.cases.positive.protocolId}`;
    await page.route(pattern, (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ message: 'Тестовый отказ' }) }));
    await page.goto(`${base}/#/patients/${fixture.cases.positive.id}`);
    await page.locator('.pc-protocol .error-box').waitFor();
    assert.ok(await page.getByRole('button', { name: '+ Добавить', exact: true }).isDisabled());
    await page.unroute(pattern);
    await page.getByRole('button', { name: 'Повторить', exact: true }).click();
    await page.locator('.pc-protocol mark').first().waitFor();
    expectedFailure = false;
  });
  await test('offline error has retry and never substitutes demo data', async () => {
    expectedFailure = true;
    await page.route('**/api/patients?*', (route) => route.abort());
    await page.goto(`${base}/#/findings`);
    await page.locator('.error-box').waitFor();
    assert.equal(await page.locator('.demo, .row-card').count(), 0);
    await page.unroute('**/api/patients?*');
    await page.getByRole('button', { name: 'Повторить', exact: true }).click();
    await page.locator('.row-card').first().waitFor();
    expectedFailure = false;
  });
  await test('mobile layout does not overflow', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await card('positive');
    await until(async () => await page.locator('main').evaluate((el) => el.getBoundingClientRect().x <= 13 && el.getBoundingClientRect().width >= 350));
    await page.screenshot({ path: resolve(root, '.local/frontend-patient-mobile.png'), fullPage: true });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.goto(`${base}/#/findings`); await search(fixture.run);
    await page.locator('.row-card').first().waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({ path: resolve(root, '.local/frontend-list-mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
  });
  await test('API docs deep link and explicit synthetic offline demo', async () => {
    await page.goto(`${base}/open-api`);
    await until(async () => (await page.locator('body').innerText()).includes('/api/integration/protocols'));
    await page.goto(`${base}/?mock=1`);
    await page.locator('.row-card').first().waitFor();
    await page.getByRole('button', { name: 'Демо', exact: true }).click();
    assert.ok((await page.locator('.demo-body').innerText()).includes('Вымышленные данные'));
  });
  await test('no JavaScript errors, unexpected HTTP errors or oversized pages', async () => {
    assert.deepEqual(errors, []); assert.deepEqual(badResponses, []);
    assert.ok(patientQueries.length > 0);
    assert.ok(patientQueries.every((q) => Number(q.get('size') || 50) <= 200));
  });
} catch (e) {
  results.push({ name: 'failure', passed: false, message: e.stack });
  await mkdir(resolve(root, '.local'), { recursive: true });
  await page.screenshot({ path: resolve(root, '.local/frontend-e2e-failure.png'), fullPage: true });
  await writeFile(resolve(root, '.local/frontend-e2e-failure.txt'), await page.locator('body').innerText());
  process.exitCode = 1;
  console.error(e);
} finally {
  await writeFile(resolve(root, '.local/frontend-e2e.json'), JSON.stringify({ results, pageErrors: errors, badResponses, patientRequests: patientQueries.length }, null, 2));
  await browser.close();
}
