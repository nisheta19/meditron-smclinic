// Real API + browser: header clicks, both directions, missing values and test labels.
import assert from 'node:assert/strict';
import { signIn } from './auth-support.mjs';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const base = process.env.FRONTEND_URL || 'http://127.0.0.1:13000';
const prefix = process.env.SCENARIO_PREFIX || 'demo-scenario-v1';
const browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'msedge' });
const page = await browser.newPage({ viewport: { width: 1280, height: 832 } });
const errors = [], results = [];
page.on('pageerror', e => errors.push(e.message));
try {
  await signIn(page.context(), base);
  await page.goto(`${base}/#/findings?q=${prefix}`);
  await page.locator('.row-card').first().waitFor();
  for (const [key, label] of [['patient', 'Пациент'], ['finding', 'Находка'], ['due', 'Срок записи']]) {
    for (const direction of ['asc', 'desc']) {
      const response = page.waitForResponse(r => {
        const u = new URL(r.url());
        return u.pathname === '/api/patients' && u.searchParams.get('sortBy') === key && u.searchParams.get('sortDirection') === direction;
      });
      await page.getByRole('button', { name: label, exact: true }).click();
      const expected = (await (await response).json()).items;
      assert.ok(expected.length >= 5, 'Expected the seeded scenario patients');
      const expectedNames = expected.map(p => p.shortName || p.fullName);
      await page.waitForFunction(names => JSON.stringify([...document.querySelectorAll('.row-card .cell-patient .s-main')].map(e => e.textContent)) === JSON.stringify(names), expectedNames);
      assert.equal(await page.getByRole('button', { name: label, exact: true }).getAttribute('aria-sort'), direction === 'asc' ? 'ascending' : 'descending');
      assert.ok(expectedNames.every(name => name.includes('[ТЕСТ ')));
      if (key === 'due') {
        const values = expected.map(p => p.topFindings?.[0]?.targetDays ?? null);
        const ordered = values.filter(v => v !== null).sort((a, b) => direction === 'asc' ? a - b : b - a);
        assert.deepEqual(values, [...ordered, ...values.filter(v => v === null)]);
      }
      results.push({ key, direction, passed: true });
    }
  }
  assert.equal(await page.locator('.mobile-sort').count(), 0);
  assert.ok((await page.getByText('Этап', { exact: true }).getAttribute('title')).includes('недоступна'));
  assert.equal(await page.locator('.urgency-badge').count(), 0);
  assert.deepEqual(errors, []);
  await mkdir(resolve(import.meta.dirname, '../../.local'), { recursive: true });
  await page.screenshot({ path: resolve(import.meta.dirname, '../../.local/scenarios-sorting.png'), fullPage: true });
  await writeFile(resolve(import.meta.dirname, '../../.local/scenarios-sorting.json'), JSON.stringify({ results, errors }, null, 2));
  console.log(`PASS ${results.length} browser sorting checks; no design additions`);
} finally { await browser.close(); }
