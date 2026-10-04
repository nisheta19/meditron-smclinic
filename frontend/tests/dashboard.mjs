// Static dashboard: reference geometry, inert controls and independence from the backend.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');
const root = resolve(import.meta.dirname, '../..');
const base = process.env.FRONTEND_URL || 'http://127.0.0.1:13000';
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}) });
const context = await browser.newContext({ viewport: { width: 1280, height: 1038 }, deviceScaleFactor: 2 });
const page = await context.newPage();
const results = [], errors = [], apiCalls = [];
await mkdir(resolve(root, '.local'), { recursive: true });
page.on('pageerror', e => errors.push(e.message));
// A disconnected backend must not affect this screen or receive background polling.
await page.route('**/api/**', route => { apiCalls.push(route.request().url()); return route.abort(); });
const ready = async () => { await page.locator('.dash-mapsvg').waitFor(); await page.evaluate(() => document.fonts.ready); };
const test = async (name, fn) => {
  try { await fn(); results.push({ name, ok: true }); console.log(`PASS ${name}`); }
  catch (error) { results.push({ name, ok: false, error: error.message }); console.error(`FAIL ${name}: ${error.message}`); }
};
const near = (actual, expected, label) => assert.ok(Math.abs(actual - expected) <= 1, `${label}: ${actual}, expected ${expected}`);
try {
  await page.goto(`${base}/#/dashboard`); await ready();
  await test('reference frame, card geometry and sidebar at 1280 × 1038', async () => {
    const boxes = {
      '.searchbar': [222, 25, 1042, 64], '.dash-map': [222, 167, 518, 562],
      '.dash-mapsvg': [316, 264, 330, 429], '.dash-hero': [746, 167, 518, 278],
      '.dash-metric:nth-of-type(3)': [746, 451, 256, 278],
      '.dash-metric:nth-of-type(4)': [1008, 451, 256, 278],
      '.dash-funnel': [222, 735, 518, 278],
      '.dash-metric:nth-of-type(6)': [746, 735, 256, 278],
      '.dash-metric:nth-of-type(7)': [1008, 735, 256, 278],
      '.dash-select:first-child': [1030, 109, 102, 38], '.dash-select:last-child': [1140, 109, 124, 38],
      // User refinement: same footer position as the list, with no dashboard-only inset.
      '.nav-avatar': [19, 953, 32, 32], '.nav [aria-current="page"]': [8, 106, 190, 36],
    };
    for (const [selector, expected] of Object.entries(boxes)) {
      const box = await page.locator(selector).boundingBox();
      ['x', 'y', 'width', 'height'].forEach((axis, i) => near(box[axis], expected[i], `${selector} ${axis}`));
    }
    assert.equal(await page.locator('.nav a[aria-current="page"]').innerText(), 'Дашборд');
    assert.deepEqual(await page.locator('.nav .nav-item').allTextContents(), ['Дашборд', 'Входящие', 'Находки']);
    assert.equal(await page.locator('.dash-select:last-child span').innerText(), 'За неделю');
    assert.ok((await page.locator('.dash-select:last-child span').boundingBox()).height < 20, 'Period must stay on one line');
    await page.screenshot({ path: resolve(root, '.local/dashboard-final.png'), fullPage: true });
  });
  await test('reference figures, map and notification bars', async () => {
    assert.equal(await page.locator('.dash-hero h2').innerText(), 'Доходят до конца');
    assert.equal(await page.locator('.dash-hero p').innerText(), '1367 из 2067 пациентов');
    assert.deepEqual(await page.locator('.dash strong').allTextContents(), ['67%', '57%', '67%', '78%', '1.2']);
    assert.deepEqual(await page.locator('.dash-delta').allTextContents(), ['-15% за неделю', '+10% за неделю', '+10% за неделю', '-21% за неделю']);
    assert.deepEqual(await page.locator('.funnel-pct').allTextContents(), ['67%', '42%', '78%']);
    for (const [index, width] of [266, 186, 347].entries()) near((await page.locator('.funnel-bar').nth(index).boundingBox()).width, width, `Bar ${index}`);
    assert.equal(await page.locator('.dash-mapsvg circle').count(), 1228);
    assert.equal(await page.locator('.dash-wave path').count(), 2);
  });
  await test('all dashboard controls are inert, without a popup or navigation', async () => {
    const before = await page.locator('.dashboard').innerHTML();
    const buttons = page.locator('.dashboard button');
    assert.equal(await buttons.count(), 9);
    for (let i = 0; i < await buttons.count(); i++) {
      const button = buttons.nth(i); assert.ok(await button.isDisabled());
      // Native disabled click must not invoke a handler or alter data.
      await button.evaluate(element => element.click());
    }
    assert.ok(await page.locator('.dashboard input').isDisabled());
    assert.equal(await page.locator('.dashboard a, .dashboard select').count(), 0);
    assert.equal(await page.locator('.dashboard').innerHTML(), before);
    assert.ok(page.url().endsWith('/#/dashboard'));
  });
  await test('dashboard renders and stays idle while every backend request is blocked', async () => {
    // Wait through the existing lists’ polling interval to detect accidental API reuse.
    await page.waitForTimeout(5500);
    assert.deepEqual(apiCalls, []);
    assert.equal(await page.locator('.state, .toast').count(), 0);
  });
  await test('sidebar navigation works and list polling stops on return', async () => {
    const footer = await page.locator('.nav-bottom').boundingBox();
    await page.unroute('**/api/**');
    await page.route('**/api/**', route => route.fulfill({ json: { items: [], total: 0, page: 0, size: 50 } }));
    await page.getByRole('link', { name: 'Находки', exact: true }).click();
    await page.locator('.chips').waitFor();
    assert.ok(page.url().endsWith('/#/findings'));
    assert.deepEqual(await page.locator('.nav-bottom').boundingBox(), footer, 'Footer must not jump between dashboard and list');
    assert.deepEqual(await page.locator('.nav .nav-item').allTextContents(), ['Дашборд', 'Входящие', 'Находки']);
    await page.getByRole('link', { name: 'Дашборд', exact: true }).click(); await ready();
    await page.unroute('**/api/**');
    await page.route('**/api/**', route => { apiCalls.push(route.request().url()); return route.abort(); });
    await page.waitForTimeout(5500);
    assert.deepEqual(apiCalls, []);
  });
  await test('mock mode shows the same static frame without demo buttons', async () => {
    await page.goto(`${base}/?mock=1#/dashboard`); await ready();
    assert.equal(await page.locator('.demo, .demo-toggle').count(), 0);
    assert.deepEqual(await page.locator('.dash strong').allTextContents(), ['67%', '57%', '67%', '78%', '1.2']);
    assert.deepEqual(apiCalls, []);
  });
  await test('no horizontal overflow on phone, tablet or wide desktop', async () => {
    await page.goto(`${base}/#/dashboard`); await ready();
    for (const width of [390, 768, 1024, 1280, 1920]) {
      await page.setViewportSize({ width, height: 1038 });
      // Wait for the shared sidebar transition and media-query React update.
      await page.waitForTimeout(400);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Overflow at ${width}px`);
      assert.ok(await page.locator('.dash-map').isVisible());
      assert.ok(await page.locator('.dash-funnel').isVisible());
    }
    assert.deepEqual(apiCalls, []); assert.deepEqual(errors, []);
  });
} finally {
  await writeFile(resolve(root, '.local/dashboard-results.json'), JSON.stringify({ results, apiCalls, errors }, null, 2));
  await browser.close();
}
if (results.some(result => !result.ok)) process.exitCode = 1;
