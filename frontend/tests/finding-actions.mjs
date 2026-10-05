// Regression for the four comments in the supplied Word document. Fictional data only.
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { patients, patientCard, protocol, findings } from './design-fixtures.mjs';
const base = process.env.FRONTEND_URL || 'http://127.0.0.1:13000';
const out = resolve('../.local/finding-actions'); await mkdir(out, { recursive:true });
const browser = await chromium.launch({ channel:process.env.BROWSER_CHANNEL || 'msedge', headless:true });
const context = await browser.newContext({ viewport:{width:1280,height:1000} });
const page = await context.newPage(); page.setDefaultTimeout(12000);
const results = [], errors = [];
page.on('pageerror', e => errors.push(e.message));
const fs = [
  {...findings[0], level:'EMERGENCY'},
  {...findings[1], level:'URGENT'},
  {...findings[1], id:'confirmed-finding', status:'CONFIRMED', level:'URGENT'},
];
await page.route('**/api/**', r => {
  const req = r.request(), path = new URL(req.url()).pathname;
  if (!path.startsWith('/api/')) return r.continue();
  assert.equal(req.method(), 'GET', 'Visual checks must not write patient data');
  const body = path === '/api/auth/me' ? {login:'123',roles:['DOCTOR']} :
    path === '/api/patients' ? {items:patients,total:patients.length,page:0,size:50} :
    path.endsWith('/notifications') || path.endsWith('/routes') ? [] :
    path.startsWith('/api/patients/') ? {...patientCard,currentFindings:fs,currentProtocol:{...protocol,findings:fs}} :
    path.startsWith('/api/protocols/') ? {...protocol,findings:fs} : [];
  return r.fulfill({json:body});
});
const check = async (name, fn) => { await fn(); results.push(name); console.log('PASS '+name); };
const openProtocol = async () => {
  await page.goto(base+'/#/patients/design-0'); await page.reload();
  await page.locator('.npc-event').first().click();
  await page.locator('.pc-row.confirmed').waitFor();
  await page.evaluate(() => document.fonts.ready);
};
try {
  await openProtocol();
  const row = page.locator('[data-finding-id="confirmed-finding"]');
  const trigger = row.getByRole('button', {name:/^Действия:/});
  await check('confirmed row has plain status and only an ellipsis action', async () => {
    assert.equal(await row.locator('.review-level button,.sq').count(), 0);
    assert.equal((await row.locator('.review-level').innerText()).trim(), 'Срочно');
    assert.equal(await trigger.count(), 1);
    assert.equal(await page.locator('.pc-row.suggested .sq').count(), 4);
    assert.equal(await page.locator('.pc-row.suggested .review-pill').count(), 2);
  });
  await check('header and all row columns align without approval sublabels', async () => {
    const heads = await page.locator('.pc-thead > *').evaluateAll(es => es.map(e => e.getBoundingClientRect().left));
    for (const r of await page.locator('.pc-row-main').all()) {
      const cells = await r.locator(':scope > span').evaluateAll(es => es.map(e => e.getBoundingClientRect().left));
      for (let i=0;i<3;i++) assert.ok(Math.abs(cells[i]-heads[i])<1);
      assert.ok(!(await r.innerText()).toLowerCase().includes('подтверждена'));
    }
  });
  await check('menu opens without expanding the finding; Escape restores trigger focus', async () => {
    await trigger.click(); await page.getByRole('menu').waitFor();
    assert.equal(await row.locator('.pc-row-main').getAttribute('aria-expanded'), 'false');
    assert.deepEqual(await page.getByRole('menuitem').allTextContents(), ['Редактировать','Удалить']);
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.getByRole('menuitem',{name:'Удалить',exact:true}).evaluate(e=>e===document.activeElement),true);
    await page.keyboard.press('Escape');
    assert.equal(await page.getByRole('menu').count(),0);
    assert.equal(await trigger.evaluate(e=>e===document.activeElement),true);
    await trigger.click(); await page.locator('.review-findings-heading').click();
    assert.equal(await page.getByRole('menu').count(),0);
  });
  await check('menu matches the larger workspace scale and stays visible on narrow screens', async () => {
    for (const width of [1280,1920,390]) {
      await page.setViewportSize({width,height:1000});
      await trigger.click(); await page.getByRole('menu').waitFor();
      const b = await page.getByRole('menu').boundingBox();
      assert.ok(b.x>=0 && b.x+b.width<=width+1 && b.y>=0 && b.y+b.height<=1001,JSON.stringify(b));
      assert.equal(await page.getByRole('menu').evaluate(e=>getComputedStyle(e).fontSize),`${14*(width>1280?width/1280:1)}px`);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await page.screenshot({path:resolve(out,`menu-${width}.png`)});
      await page.keyboard.press('Escape');
    }
  });
  await check('working dashboard, inbox, findings and patient card never show Demo', async () => {
    await page.setViewportSize({width:1280,height:1000});
    for (const section of ['dashboard','inbox','findings','patients/design-0']) {
      await page.goto(base+'/#/'+section); await page.locator('main').waitFor();
      assert.equal(await page.locator('.demo').count(),0);
    }
  });
  await check('selection count is regular; panel insets and inter-button gaps match', async () => {
    await page.goto(base+'/?mock=1#/findings');
    await page.locator('.row-card').first().getByRole('checkbox').click();
    const bar = page.getByRole('region',{name:'Действия с выбранными'});
    await bar.waitFor();
    const s = await bar.evaluate(e=>{const c=getComputedStyle(e);return {gap:c.gap,left:c.paddingLeft,right:c.paddingRight,weight:getComputedStyle(e.firstElementChild).fontWeight};});
    assert.deepEqual(s,{gap:'12px',left:'12px',right:'12px',weight:'400'});
    assert.equal(await bar.locator('b,strong').count(),0);
    await page.screenshot({path:resolve(out,'selection.png'),animations:'disabled'});
    await bar.getByRole('button',{name:'Снять выделение',exact:true}).click();
    assert.equal(await bar.count(),0);
  });
  assert.deepEqual(errors,[]);
} catch(e) { process.exitCode=1; console.error(e); await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}); }
finally { await writeFile(resolve(out,'results.json'),JSON.stringify({results,errors,passed:!process.exitCode},null,2)); await browser.close(); }
