import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
const base = process.env.FRONTEND_URL || 'http://127.0.0.1:15175';
const out = resolve('../.local/auth-integration');
await mkdir(out, { recursive: true });

const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 832 }, deviceScaleFactor: 2 });
const page = await context.newPage();
const results = [], errors = [], calls = [];
let signedIn = false, token = 0, logoutOffline = false, logoutCalls = 0;
page.on('pageerror', error => errors.push(error.message));
await page.route(url => url.origin === new URL(base).origin && url.pathname.startsWith('/api/'), async route => {
  const request = route.request(), path = new URL(request.url()).pathname;
  calls.push({ path, method: request.method() });
  const reply = (status, json) => route.fulfill({ status, json });
  if (path === '/api/auth/me') return reply(signedIn ? 200 : 401, signedIn ? { login: '123', roles: ['DOCTOR'] } : { code: 'UNAUTHORIZED' });
  if (path === '/api/auth/csrf') return reply(200, { token: `csrf-${++token}`, headerName: 'X-CSRF-TOKEN', parameterName: '_csrf' });
  if (path === '/api/auth/logout') {
    logoutCalls += 1;
    assert.equal(request.method(), 'POST');
    assert.equal(request.headers()['x-csrf-token'], `csrf-${token}`);
    if (logoutOffline) return route.abort();
    signedIn = false;
    return route.fulfill({ status: 204 });
  }
  if (path === '/api/auth/login') {
    assert.equal(request.headers()['x-csrf-token'], `csrf-${token}`);
    const { login, password } = request.postDataJSON();
    signedIn = login === '123' && password === '123';
    return reply(signedIn ? 200 : 401, signedIn ? { login, roles: ['DOCTOR'] } : { code: 'INVALID_CREDENTIALS' });
  }
  if (!signedIn) return reply(401, { code: 'UNAUTHORIZED' });
  if (path.startsWith('/api/patients')) return reply(200, { items: [], total: 0, page: 0, size: 20 });
  return reply(200, []);
});
async function check(name, fn) {
  try { await fn(); results.push({ name, ok: true }); console.log(`PASS ${name}`); }
  catch (error) { results.push({ name, ok: false, error: error.message }); console.error(`FAIL ${name}: ${error.message}`); await page.keyboard.press('Escape'); }
}
const settleSidebar = () => page.locator('.sidebar').evaluate(el => Promise.all(el.getAnimations({ subtree: true }).map(animation => animation.finished)));
try {
  await page.goto(`${base}/#/dashboard`);
  await page.evaluate(() => document.fonts.ready);
  await page.locator('.auth-submit:enabled').waitFor();
  await check('unauthenticated route shows only the supplied login form', async () => {
    assert.equal(await page.locator('h1').innerText(), 'Добро пожаловать');
    assert.equal(await page.locator('input').count(), 2);
    assert.equal(await page.locator('button').count(), 1);
    assert.equal(await page.locator('.sidebar').count(), 0);
    assert.equal(calls.filter(call => !call.path.startsWith('/api/auth')).length, 0);
    assert.deepEqual(await page.evaluate(() => Object.keys(localStorage)), []);
  });
  await check('reference geometry matches 1280 × 832 exactly', async () => {
    for (const [selector, expected] of Object.entries({
      '.auth-card': [808, 17, 456, 799], '.auth-logo': [213, 89, 395, 63], '.auth-doctor': [55, 311, 712, 534],
      '[name=login]': [835, 312, 401, 56], '[name=password]': [835, 412, 401, 56], '.auth-submit': [835, 492, 401, 56],
    })) {
      const b = await page.locator(selector).boundingBox();
      assert.deepEqual([b.x, b.y, b.width, b.height], expected, selector);
    }
  });
  await check('keyboard order and password masking', async () => {
    await page.keyboard.press('Tab'); assert.equal(await page.locator(':focus').getAttribute('name'), 'login');
    await page.keyboard.press('Tab'); assert.equal(await page.locator(':focus').getAttribute('name'), 'password');
    assert.equal(await page.locator(':focus').getAttribute('type'), 'password');
    await page.keyboard.press('Tab'); assert.equal(await page.locator(':focus').innerText(), 'Войти в систему');
  });
  await check('password caret follows native dots while editing and scrolling', async () => {
    const field = page.getByLabel('Пароль', { exact: true });
    await field.fill('123'); await field.press('End');
    assert.equal(await field.evaluate(el => el.selectionStart), 3);
    await field.screenshot({ path: resolve(out, 'password-caret-end.png'), caret: 'initial' });
    await field.press('Home'); await field.press('ArrowRight');
    assert.equal(await field.evaluate(el => el.selectionStart), 1);
    await field.screenshot({ path: resolve(out, 'password-caret-middle.png'), caret: 'initial' });
    await field.press('4');
    assert.equal(await field.inputValue(), '1423');
    await field.press('Backspace');
    assert.equal(await field.inputValue(), '123');
    const step = await field.evaluate(el => {
      const style = getComputedStyle(el), canvas = document.createElement('canvas').getContext('2d');
      canvas.font = style.font;
      return { padding: parseFloat(style.paddingLeft), advance: canvas.measureText('•').width + parseFloat(style.letterSpacing) };
    });
    await field.click({ position: { x: step.padding + step.advance, y: 28 } });
    assert.equal(await field.evaluate(el => el.selectionStart), 1);
    await field.fill('a'.repeat(128)); await field.press('End');
    assert.equal(await field.evaluate(el => el.selectionStart), 128);
    assert.ok(await field.evaluate(el => el.scrollLeft > 0), 'long passwords scroll with the caret');
    await field.press('Home');
    assert.equal(await field.evaluate(el => el.selectionStart), 0);
    await field.fill('');
  });
  await check('incorrect credentials do not grant access', async () => {
    await page.getByLabel('Логин', { exact: true }).fill('maria_doctor');
    await page.getByLabel('Пароль', { exact: true }).fill('123456789');
    await page.getByRole('button', { name: 'Войти в систему' }).click();
    await page.getByRole('alert').waitFor();
    assert.equal(await page.getByRole('alert').innerText(), 'Неверный логин или пароль');
    assert.equal(await page.locator('.sidebar').count(), 0);
  });
  await check('successful CSRF login opens the original route; reload checks the server session', async () => {
    await page.getByLabel('Логин', { exact: true }).fill('123');
    await page.getByLabel('Пароль', { exact: true }).fill('123');
    await page.getByRole('button', { name: 'Войти в систему' }).click();
    await page.locator('.dash-mapsvg').waitFor();
    assert.equal(await page.locator('.auth').count(), 0);
    assert.ok(token >= 2, 'CSRF must refresh after rejected login');
    await page.reload(); await page.locator('.dash-mapsvg').waitFor();
    assert.equal(await page.locator('.auth').count(), 0);
    assert.deepEqual(await page.evaluate(() => Object.keys(localStorage)), []);
  });
  await check('doctor popup keeps the avatar and name stationary and replaces only the collapse control', async () => {
    const before = await page.locator('.doctor-menu-trigger .nav-avatar').boundingBox();
    const textBefore = await page.locator('.doctor-menu-trigger .nav-user-text').boundingBox();
    assert.deepEqual([before.x, before.y, before.width, before.height], [19, 747, 32, 32]);
    await page.locator('.doctor-menu-trigger').click();
    const box = await page.locator('.doctor-menu-card').boundingBox();
    assert.deepEqual([box.x, box.y, box.width, box.height], [8, 739, 190, 86]);
    assert.deepEqual(await page.locator('.doctor-menu-card .nav-avatar').boundingBox(), before);
    assert.deepEqual(await page.locator('.doctor-menu-card .nav-user-text').boundingBox(), textBefore);
    assert.equal(await page.locator('.nav-bottom > .faint').isVisible(), false);
    assert.equal(await page.locator('.doctor-menu-card').evaluate(el => getComputedStyle(el).boxShadow), 'none');
    await page.screenshot({ path: resolve(out, 'profile-in-app.png'), clip: { x: 0, y: 700, width: 206, height: 132 } });
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.doctor-menu-card').count(), 0);
    assert.equal(await page.locator('.doctor-menu-trigger').evaluate(el => el === document.activeElement), true);
    await page.locator('.doctor-menu-trigger').click();
    await page.locator('.main').click({ position: { x: 300, y: 30 } });
    assert.equal(await page.locator('.doctor-menu-card').count(), 0);
    assert.equal(await page.locator('.nav-bottom > .faint').isVisible(), true);
  });
  await check('profile stays stationary in collapsed and narrow sidebars without clipping logout', async () => {
    await page.getByRole('button', { name: 'Свернуть', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.sidebar').getBoundingClientRect().width === 64);
    await settleSidebar();
    let avatar = await page.locator('.doctor-menu-trigger .nav-avatar').boundingBox();
    await page.locator('.doctor-menu-trigger').click();
    const box = await page.locator('.doctor-menu-card').boundingBox();
    assert.equal(box.width, 190);
    assert.deepEqual(await page.locator('.doctor-menu-card .nav-avatar').boundingBox(), avatar);
    assert.equal(await page.getByRole('button', { name: 'Выйти', exact: true }).isVisible(), true);
    await page.keyboard.press('Escape');
    await page.getByTitle('Развернуть', { exact: true }).click();
    for (const width of [768, 1000, 1280, 1920]) {
      await page.setViewportSize({ width, height: 832 });
      await page.waitForFunction(() => {
        const scale = innerWidth > 1280 ? innerWidth / 1280 : 1;
        const expected = (innerWidth <= 1000 ? 64 : 206) * scale;
        return Math.abs(document.querySelector('.sidebar').getBoundingClientRect().width - expected) < 0.1;
      });
      await settleSidebar();
      avatar = await page.locator('.doctor-menu-trigger .nav-avatar').boundingBox();
      await page.locator('.doctor-menu-trigger').click();
      assert.deepEqual(await page.locator('.doctor-menu-card .nav-avatar').boundingBox(), avatar, `${width}: stationary avatar`);
      const popup = await page.locator('.doctor-menu-card').boundingBox();
      assert.ok(popup.y >= 0 && popup.y + popup.height <= 832, `${width}: menu within viewport`);
      await page.keyboard.press('Escape');
    }
    await page.setViewportSize({ width: 1280, height: 832 });
  });
  await check('a failed logout keeps the session and can be retried', async () => {
    logoutOffline = true;
    await page.locator('.doctor-menu-trigger').click();
    await page.getByRole('button', { name: 'Выйти', exact: true }).click();
    await page.getByText('Не удалось выйти. Попробуйте ещё раз.', { exact: true }).waitFor();
    assert.equal(await page.locator('.auth').count(), 0);
    assert.equal(signedIn, true);
    logoutOffline = false;
    await page.keyboard.press('Escape');
  });
  await check('keyboard logout ends the server session and opens authorization, including after reload', async () => {
    await page.locator('.doctor-menu-trigger').focus();
    await page.keyboard.press('Enter');
    await page.locator('.doctor-menu-card').waitFor();
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').innerText(), 'Выйти');
    await page.keyboard.press('Enter');
    await page.locator('.auth-submit:enabled').waitFor();
    assert.equal(signedIn, false);
    assert.equal(logoutCalls, 2);
    assert.equal(await page.locator('.sidebar').count(), 0);
    await page.reload(); await page.locator('.auth-submit:enabled').waitFor();
    assert.equal(await page.locator('.sidebar').count(), 0);
    await page.getByLabel('Логин', { exact: true }).fill('123');
    await page.getByLabel('Пароль', { exact: true }).fill('123');
    await page.getByRole('button', { name: 'Войти в систему' }).click();
    await page.locator('.dash-mapsvg').waitFor();
  });
  await check('expired server session returns to login', async () => {
    signedIn = false;
    await page.getByRole('link', { name: 'Входящие', exact: true }).click();
    await page.locator('.auth-submit:enabled').waitFor();
    assert.equal(await page.locator('.sidebar').count(), 0);
  });
  await check('layout remains usable at 390 / 768 / 1024 / 1280 / 1920', async () => {
    for (const width of [390, 768, 1024, 1280, 1920]) {
      await page.setViewportSize({ width, height: width === 1920 ? 1080 : 832 });
      await page.waitForFunction(() => Number(document.querySelector('.auth').style.getPropertyValue('--auth-scale')) === (innerWidth >= 900 ? innerWidth / 1280 : 1));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
      const b = await page.locator('.auth-submit').boundingBox();
      assert.ok(b.x >= 0 && b.x + b.width <= width && b.height >= 40, `${width}: submit accessible`);
      await page.getByLabel('Логин', { exact: true }).fill('123');
      assert.equal(await page.getByLabel('Логин', { exact: true }).inputValue(), '123');
    }
  });
  await check('network failure stays on the login page with a readable error', async () => {
    await page.route('**/api/auth/csrf', route => route.abort());
    await page.getByLabel('Пароль', { exact: true }).fill('123');
    await page.getByRole('button', { name: 'Войти в систему' }).click();
    await page.getByRole('alert').waitFor();
    assert.equal(await page.getByRole('alert').innerText(), 'Не удалось войти. Попробуйте ещё раз.');
    assert.equal(await page.locator('.sidebar').count(), 0);
  });
  await check('no browser JavaScript errors', async () => assert.deepEqual(errors, []));
} finally {
  await writeFile(resolve(out, 'auth-browser-results.json'), JSON.stringify({ results, errors }, null, 2));
  await browser.close();
}
if (results.some(result => !result.ok)) process.exitCode = 1;
