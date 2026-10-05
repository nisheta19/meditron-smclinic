// Real nginx -> Spring cookie/CSRF session. No mocked API responses or patient mutations.
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const base = process.env.FRONTEND_URL || 'http://127.0.0.1:13000';
const out = resolve(process.env.AUTH_REPORT_DIR || '../.local/auth-integration');
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'msedge' });
const context = await browser.newContext({ viewport: { width: 1280, height: 832 }, deviceScaleFactor: 2 });
const page = await context.newPage();
page.setDefaultTimeout(15000);
const results = [], errors = [];
page.on('pageerror', error => errors.push(error.message));
async function check(name, fn) { await fn(); results.push({ name, passed: true }); console.log(`PASS ${name}`); }
async function login(password = process.env.AUTH_PASSWORD || '123') {
  await page.getByLabel('Логин', { exact: true }).fill(process.env.AUTH_LOGIN || '123');
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  await page.locator('.auth-submit:enabled').click();
}
try {
  await check('anonymous API and deep links require a real server session', async () => {
    assert.equal((await context.request.get(`${base}/api/patients`)).status(), 401);
    assert.equal((await context.request.get(`${base}/api/auth/me`)).status(), 401);
    await page.goto(`${base}/#/dashboard`);
    await page.locator('.auth-submit:enabled').waitFor();
    assert.equal(await page.locator('.sidebar').count(), 0);
  });
  await check('incorrect credentials stay on the login screen', async () => {
    await login('incorrect-password');
    await page.getByRole('alert').waitFor();
    assert.equal(await page.getByRole('alert').innerText(), 'Неверный логин или пароль');
    assert.equal((await context.request.get(`${base}/api/auth/me`)).status(), 401);
  });
  await check('login opens the requested dashboard and survives reload', async () => {
    await login();
    await page.locator('.dash-mapsvg').waitFor();
    assert.equal((await context.request.get(`${base}/api/auth/me`)).status(), 200);
    assert.equal((await context.request.get(`${base}/api/patients?size=1`)).status(), 200);
    await page.reload(); await page.locator('.dash-mapsvg').waitFor();
    assert.deepEqual(await page.evaluate(() => Object.keys(localStorage)), []);
  });
  await check('doctor actions require CSRF after real authentication', async () => {
    const path = `${base}/api/findings/00000000-0000-0000-0000-000000000000`;
    assert.equal((await context.request.patch(path, { data: { status: 'CONFIRMED' } })).status(), 403);
    const token = await (await context.request.get(`${base}/api/auth/csrf`)).json();
    const response = await context.request.patch(path, { headers: { [token.headerName]: token.token }, data: { status: 'CONFIRMED' } });
    assert.equal(response.status(), 404); // authentication passed; fictional finding does not exist
  });
  await check('logout revokes the cookie and returns to login, including after reload', async () => {
    await page.getByRole('link', { name: 'Находки', exact: true }).click();
    await page.getByRole('searchbox').waitFor();
    const previous = (await context.cookies()).find(cookie => cookie.name === 'JSESSIONID');
    assert.ok(previous);
    await page.locator('.doctor-menu-trigger').click();
    await page.screenshot({ path: resolve(out, 'live-profile.png') });
    const logout = page.waitForResponse(response => response.url().endsWith('/api/auth/logout'));
    await page.getByRole('button', { name: 'Выйти', exact: true }).click();
    assert.equal((await logout).status(), 204);
    await page.locator('.auth-submit:enabled').waitFor();
    assert.equal((await context.request.get(`${base}/api/auth/me`)).status(), 401);
    assert.equal((await context.request.get(`${base}/api/patients`, { headers: { Cookie: `JSESSIONID=${previous.value}` } })).status(), 401);
    await page.reload(); await page.locator('.auth-submit:enabled').waitFor();
    assert.equal(await page.locator('.sidebar').count(), 0);
  });
  await check('repeat login works; session ended elsewhere is detected by the open page', async () => {
    await login(); await page.getByRole('searchbox').waitFor();
    const token = await (await context.request.get(`${base}/api/auth/csrf`)).json();
    assert.equal((await context.request.post(`${base}/api/auth/logout`, { headers: { [token.headerName]: token.token } })).status(), 204);
    await page.locator('.auth-submit:enabled').waitFor();
    assert.equal(await page.locator('.sidebar').count(), 0);
  });
  await check('no JavaScript errors', async () => assert.deepEqual(errors, []));
} catch (error) {
  results.push({ passed: false, error: error.message });
  process.exitCode = 1;
  console.error(error);
} finally {
  await writeFile(resolve(out, 'auth-live-results.json'), JSON.stringify({ base, results, errors }, null, 2));
  await browser.close();
}
