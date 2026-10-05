// Deterministic browser checks for date editing, calendar focus, and filter styling.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createRequire } from 'node:module';
import { patients } from './design-fixtures.mjs';
const { chromium } = createRequire(import.meta.url)('playwright');
const root = resolve(import.meta.dirname, '../..');
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}) });
const page = await browser.newPage({ viewport: { width: 1280, height: 832 }, timezoneId: 'Europe/Moscow' });
const results = [], errors = [], requests = [];
const from = page.getByRole('combobox', { name: 'Дата исследования с', exact: true });
const to = page.getByRole('combobox', { name: 'Дата исследования по', exact: true });
const calendar = page.locator('.date-calendar');
const toggle = page.getByRole('button', { name: 'Фильтры', exact: true });
const test = async (name, fn) => { await fn(); results.push({ name, passed: true }); console.log(`PASS ${name}`); };
const hasValue = async (field, value) => assert.equal(await field.inputValue(), value);
const focused = async (field) => assert.ok(await field.evaluate((el) => el === document.activeElement));
const outside = async () => page.getByRole('searchbox').click();
const expectRequest = async (query) => {
  await page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === '/api/patients' && Object.entries(query).every(([key, value]) => url.searchParams.get(key) === value);
  });
};
await page.route("**/api/auth/me", route => route.fulfill({ json: { login: "123", roles: ["DOCTOR"] } }));
page.on('pageerror', (e) => errors.push(e.message));
await page.route('**/api/patients?*', (route) => {
  requests.push(Object.fromEntries(new URL(route.request().url()).searchParams));
  return route.fulfill({ json: { items: patients, total: 4, page: 0, size: 50 } });
});
await mkdir(resolve(root, '.local'), { recursive: true });
try {
  await page.goto(process.env.FRONTEND_URL || 'http://127.0.0.1:3000');
  await page.locator('.row-card').first().waitFor();
  await test('unsupported booking counters show zero and remain disabled', async () => {
    for (const name of ['Просрочена запись', 'Без записи']) {
      const actual = page.getByRole('tab').filter({ hasText: name });
      assert.equal(await actual.locator('.chip-count').innerText(), '0');
      assert.ok(await actual.isDisabled());
    }
    assert.equal(await page.getByRole('tab').first().locator('.chip-count').innerText(), '4');
  });
  await toggle.click();
  await test('every part of both date fields opens the calendar without an icon', async () => {
    for (const field of [from, to]) {
      assert.equal(await field.getAttribute('type'), 'text');
      for (const fraction of [0.08, 0.5, 0.92]) {
        await outside(); const box = await field.boundingBox();
        await field.click({ position: { x: box.width * fraction, y: box.height / 2 } });
        await calendar.waitFor(); await focused(field);
      }
    }
  });
  await test('calendar stays visible during manual entry and day selection', async () => {
    await from.click();
    for (const character of '07.09.2026') {
      await from.pressSequentially(character);
      assert.ok(await calendar.isVisible()); await focused(from);
    }
    await hasValue(from, '07.09.2026');
    assert.match(await calendar.locator('.date-calendar-head').innerText(), /сентябрь 2026/i);
    const request = expectRequest({ dateFrom: '2026-09-08' });
    await calendar.getByRole('button', { name: '08.09.2026', exact: true }).click(); await request;
    assert.ok(await calendar.isVisible()); await focused(from); await hasValue(from, '08.09.2026');
  });
  await test('date survives outside click, Escape, and closing the filter panel', async () => {
    await outside(); await calendar.waitFor({ state: 'hidden' });
    await from.click(); await hasValue(from, '08.09.2026');
    await from.press('Escape'); await calendar.waitFor({ state: 'hidden' }); await hasValue(from, '08.09.2026');
    await from.press('Enter'); await calendar.waitFor();
    await toggle.click(); await calendar.waitFor({ state: 'hidden' });
    await toggle.click(); await from.click(); await hasValue(from, '08.09.2026');
    assert.equal(await calendar.getByRole('button', { name: '08.09.2026' }).getAttribute('aria-pressed'), 'true');
  });
  await test('partial and invalid drafts survive closing without reaching the API', async () => {
    await from.fill('07.09.'); await outside(); await from.click(); await hasValue(from, '07.09.');
    await toggle.click(); await toggle.click(); await from.click(); await hasValue(from, '07.09.');
    await from.fill('31.02.2026'); assert.equal(await from.getAttribute('aria-invalid'), 'true');
    await from.fill('29.02.2024');
    assert.equal(await calendar.locator('[data-date]').count(), 29);
    assert.equal(await calendar.getByRole('button', { name: '29.02.2024' }).getAttribute('aria-pressed'), 'true');
    assert.ok(requests.every((query) => !['2026-02-31', '2026-09-07.'].includes(query.dateFrom)));
  });
  await test('month navigation and keyboard selection keep the calendar active', async () => {
    await from.fill('15.12.2025');
    await calendar.getByRole('button', { name: 'Следующий месяц' }).click();
    assert.match(await calendar.locator('.date-calendar-head').innerText(), /январь 2026/i);
    await calendar.getByRole('button', { name: 'Предыдущий месяц' }).click();
    const day = calendar.getByRole('button', { name: '15.12.2025' });
    await day.focus(); await day.press('ArrowRight');
    const next = calendar.getByRole('button', { name: '16.12.2025' }); await focused(next);
    await next.press('Enter'); await hasValue(from, '16.12.2025'); assert.ok(await calendar.isVisible());
    await from.fill('31.12.2025'); await from.press('ArrowDown');
    const end = calendar.getByRole('button', { name: '31.12.2025' }); await focused(end);
    await end.press('ArrowRight');
    const january = calendar.getByRole('button', { name: '01.01.2026' }); await focused(january);
    await january.press('Enter'); await hasValue(from, '01.01.2026');
  });
  await test('switching fields leaves one calendar and sends ISO date bounds', async () => {
    await from.fill('08.09.2026');
    await from.press('Tab'); await focused(to); assert.equal(await calendar.count(), 1);
    assert.equal(await calendar.getAttribute('aria-label'), 'Календарь: Дата исследования по');
    const request = expectRequest({ dateFrom: '2026-09-08', dateTo: '2026-09-15' });
    await to.fill('15.09.2026'); await request;
    await outside(); await to.click(); await hasValue(to, '15.09.2026');
  });
  await test('all date and dropdown filters use gray borders without green glow', async () => {
    const gray = async (control) => {
      await page.waitForFunction((element) => {
        const s = getComputedStyle(element);
        return s.borderColor === 'rgb(215, 215, 215)' && s.borderWidth === '1px' && s.boxShadow === 'none' && s.outlineStyle === 'none';
      }, await control.elementHandle());
    };
    for (const field of [from, to]) { await field.click(); await gray(field); }
    for (const name of ['Исследование', 'Проверка находок']) {
      const button = page.locator('.field').filter({ has: page.locator('span', { hasText: new RegExp(`^${name}$`) }) }).locator('.dd-btn');
      await button.click(); await gray(button);
      const selected = page.locator('.dd-list [aria-selected="true"]');
      assert.equal(await selected.evaluate((el) => getComputedStyle(el).color), 'rgb(83, 83, 83)');
      assert.equal(await button.locator('svg').evaluate((el) => getComputedStyle(el).color), 'rgb(129, 129, 129)');
      await button.press('Escape'); await button.focus(); await gray(button);
    }
    await from.click();
    await page.screenshot({ path: resolve(root, '.local/filter-controls.png'), fullPage: true });
  });
  await test('reset clears applied values and incomplete drafts together', async () => {
    await to.fill(''); await to.fill('15.09.');
    await page.getByRole('button', { name: 'Сбросить фильтры', exact: true }).click();
    await hasValue(from, ''); await hasValue(to, ''); await calendar.waitFor({ state: 'hidden' });
    await from.click(); assert.equal(await calendar.locator('[aria-pressed="true"]').count(), 0);
  });
  await test('calendar stays inside the viewport on mobile and desktop', async () => {
    for (const width of [390, 768, 1280]) {
      await page.setViewportSize({ width, height: 832 });
      for (const field of [from, to]) {
        await field.click(); await calendar.waitFor();
        await page.waitForFunction(() => {
          const r = document.querySelector('.date-calendar').getBoundingClientRect();
          return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight;
        });
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      }
      if (width === 390) await page.screenshot({ path: resolve(root, '.local/filter-controls-mobile.png'), fullPage: true });
    }
  });
  await test('no browser errors or malformed dates in filter requests', async () => {
    assert.deepEqual(errors, []);
    for (const query of requests) for (const key of ['dateFrom', 'dateTo']) if (query[key]) assert.match(query[key], /^\d{4}-\d{2}-\d{2}$/);
  });
} catch (error) {
  errors.push(error.stack); await page.screenshot({ path: resolve(root, '.local/filter-controls-failure.png'), fullPage: true }); process.exitCode = 1;
} finally {
  await writeFile(resolve(root, '.local/filter-controls-results.json'), JSON.stringify({ passed: !errors.length, results, errors }, null, 2));
  await browser.close();
}
if (errors.length) console.error(errors.join('\n'));
