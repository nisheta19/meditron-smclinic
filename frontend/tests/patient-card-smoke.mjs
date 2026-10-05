// Read-only smoke check of the working Docker stack; no patient mutations.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {signIn} from './auth-support.mjs';
const base=process.env.FRONTEND_URL || 'http://127.0.0.1:3000';
const out=resolve(import.meta.dirname,'../../.local/patient-card');await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1280,height:1000}});
await signIn(context,base);
const page=await context.newPage();page.setDefaultTimeout(10000);
const errors=[],bad=[];page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400)bad.push(r.status());});
try {
  const list=await (await context.request.get(`${base}/api/patients?size=50`)).json();
  const p=list.items.find(x=>x.externalId?.startsWith('demo-')) ?? list.items[0];assert.ok(p);
  await page.goto(`${base}/#/patients/${p.id}`); await page.locator('.npc-card').waitFor(); await page.evaluate(()=>document.fonts.ready);
  await page.waitForFunction(()=>!document.querySelector('.npc-notifications').textContent.includes('Загружаем'));
  assert.equal(await page.locator('.npc-notifications .error-box').count(),0);
  assert.deepEqual(await page.locator('.nav .nav-item').allTextContents(),['Дашборд','Входящие','Находки']);
  await page.screenshot({path:resolve(out,'working-card.png'),fullPage:true});
  await page.locator('.npc-event').filter({hasText:'Исследование'}).first().click(); await page.locator('.protocol-text').waitFor();
  assert.deepEqual(errors,[]);assert.deepEqual(bad,[]);
  await writeFile(resolve(out,'working-smoke.json'),JSON.stringify({passed:true,base,patientId:p.id,errors,bad},null,2));
  console.log('PASS working Docker: card, notifications, original protocol, navigation, no HTTP or browser errors');
} finally {await browser.close();}
