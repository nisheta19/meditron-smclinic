// Requires isolated verification backend and fictional frontend_fixtures.py data.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import {signIn} from './auth-support.mjs';
const root=resolve(import.meta.dirname,'../..');
const fixture=JSON.parse(await readFile(resolve(root,'.local/frontend-fixtures.json'),'utf8'));
const base=process.env.FRONTEND_URL || 'http://127.0.0.1:13000';
const out=resolve(root,'.local/patient-card'); await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1280,height:1625},timezoneId:'Europe/Moscow',permissions:['clipboard-read','clipboard-write']});
await signIn(context,base);
const page=await context.newPage(); page.setDefaultTimeout(12000);
const results=[],errors=[]; page.on('pageerror',e=>errors.push(e.message));
const pid=fixture.cases.positive.id;
const get=async path=>{const r=await context.request.get(base+path); assert.equal(r.status(),200);return r.json();};
const post=async(path,data,status=202)=>{const t=await get('/api/auth/csrf');const r=await context.request.post(base+path,{data,headers:{[t.headerName]:t.token}});assert.equal(r.status(),status,await r.text());return r.json();};
const check=async(name,fn)=>{await fn();results.push(name);console.log('PASS '+name);};
const open=async()=>{await page.goto(`${base}/#/patients/${pid}`);await page.reload();await page.locator('.npc-card').waitFor();};
const close=async()=>page.getByRole('dialog').getByRole('button',{name:'Закрыть',exact:true}).first().click();
let route;
try {
  await check('confirmed findings create the actual route displayed in the new card',async()=>{
    const card=await get(`/api/patients/${pid}`);
    await post(`/api/patients/${pid}/findings/confirm`,{findingIds:card.currentFindings.map(f=>f.id)},200);
    route=(await get(`/api/patients/${pid}/routes`)).find(r=>r.open); assert.ok(route);
    await open();
    assert.equal(await page.locator('.npc-route-row').count(),card.clinicalRoutes.length || 1);
    assert.ok((await page.locator('.npc-route-row').first().innerText()).includes(route.specialty));
    await page.locator('.npc-route-row').first().click();
    await page.locator('.npc-route-details').waitFor();
    assert.ok((await page.locator('.npc-route-findings').innerText()).includes(route.findings[0].name));
    await page.getByRole('button',{name:'Скопировать ID пациента'}).click();
    assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),fixture.cases.positive.externalId);
  });
  await check('full-page protocol review opens the server message preview without sending',async()=>{
    const before=await get(`/api/patients/${pid}/notifications`);
    await page.locator('.npc-event').filter({hasText:'Исследование'}).first().click();
    await page.locator('.protocol-review .protocol-text').waitFor();
    await page.getByRole('button',{name:'Сохранить и отправить уведомление',exact:true}).click();
    await page.locator('.notify-preview > p').filter({hasText:'Напоминание:'}).waitFor();
    assert.ok((await page.locator('.notify-preview').textContent()).includes('Напоминание'));
    assert.equal((await get(`/api/patients/${pid}/notifications`)).length,before.length);
    await close(); await page.getByRole('button',{name:'Закрыть карточку'}).click();
  });
  await check('manual template, CSRF and explicit repeat confirmation persist a notification',async()=>{
    const before=await get(`/api/patients/${pid}/notifications`);
    // Ensure a recent message exists so the browser must handle CONFIRM_REQUIRED.
    await post(`/api/routes/${route.id}/notifications`,{templateCode:'REMINDER_24H',confirm:true},201);
    await open(); await page.getByRole('button',{name:'Отправить уведомление',exact:true}).click();
    await page.getByRole('radio',{name:'Напоминание через 24 часа',exact:true}).check();
    const templates=await get('/api/notification-templates');
    assert.equal(await page.getByRole('radio').count(),templates.filter(t=>t.manual).length);
    await page.locator('.notify-preview > p').filter({hasText:'Напоминание:'}).waitFor();
    const previewText=await page.locator('.notify-preview > p').textContent();
    await page.getByRole('dialog').getByRole('button',{name:'Отправить уведомление',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'24 часа'}).waitFor();
    assert.equal((await get(`/api/patients/${pid}/notifications`)).length,before.length+1);
    await page.getByRole('button',{name:'Отправить повторно',exact:true}).click();
    await page.getByRole('status').filter({hasText:'передано в CRM'}).waitFor();
    await page.getByRole('button',{name:'Готово',exact:true}).click();
    const messages=await get(`/api/patients/${pid}/notifications`); assert.equal(messages.length,before.length+2);
    assert.equal(messages[0].manual,true); assert.equal(messages[0].delivery,'SENT');
    assert.equal(messages[0].fullText,previewText);
    assert.equal(await page.locator('.npc-notification-row').count(),messages.length);
    await page.locator('.npc-message').first().click();
    assert.ok((await page.getByRole('dialog').innerText()).includes(messages[0].fullText));
    await close();
  });
  await check('CRM read receipt and real booking appear without invented timestamps',async()=>{
    const messages=await get(`/api/patients/${pid}/notifications`);
    await post('/api/integration/crm/callbacks',{eventId:randomUUID(),messageId:messages[0].id,status:'READ'});
    const slot=(await get(`/api/schedule/slots?routeId=${route.id}`))[0];
    await post('/api/integration/route-events',{eventId:randomUUID(),type:'BOOKED',routeId:route.id,slotId:slot.id});
    await open();
    await page.locator('.npc-notification-row').first().waitFor();
    assert.ok((await page.locator('.npc-route-row').first().innerText()).includes('Записан'));
    assert.ok(!(await page.locator('.npc-notification-row > span').nth(3).innerText()).includes('—'));
    assert.equal(await page.locator('.npc-notification-row').first().getByLabel('Записан',{exact:true}).count(),1);
    await page.locator('.npc-route-row').first().click();
    await page.screenshot({path:resolve(out,'live-card.png'),fullPage:true});
    for(const width of [390,768,1024,1280,1920]) {
      await page.setViewportSize({width,height:1000}); await page.locator('main').evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished)));
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Overflow ${width}`);
      if(width===390) await page.screenshot({path:resolve(out,'live-mobile.png'),fullPage:true});
    }
  });
  await check('closed route moves to actual history and cannot send messages',async()=>{
    await post('/api/integration/route-events',{eventId:randomUUID(),type:'VISIT_COMPLETED',routeId:route.id});
    await post('/api/integration/route-events',{eventId:randomUUID(),type:'TACTIC_SELECTED',routeId:route.id,tactic:'SURGERY_NOT_INDICATED'});
    await open(); assert.equal(await page.locator('.npc-route-row').count(),0);
    assert.ok(await page.getByRole('button',{name:'Отправить уведомление',exact:true}).isDisabled());
    await page.locator('.npc-event').filter({hasText:'Закрыт:'}).click();
    assert.ok((await page.getByRole('dialog').innerText()).includes('операция не показана')); await close();
  });
  await check('notification load error is visible, retry restores history; emergency send is disabled',async()=>{
    const pattern=`**/api/patients/${pid}/notifications`;
    await page.route(pattern,r=>r.fulfill({status:503,json:{message:'Тестовая ошибка уведомлений'}}));
    await open(); await page.locator('.npc-notifications .error-box').waitFor();
    assert.equal(await page.getByText('Уведомлений пока нет',{exact:true}).count(),0);
    await page.unroute(pattern); await page.getByRole('button',{name:'Повторить',exact:true}).click();
    await page.locator('.npc-notification-row').first().waitFor();
    await page.goto(`${base}/#/patients/${fixture.cases.emergency.id}`); await page.locator('.npc-card').waitFor();
    assert.ok(await page.getByRole('button',{name:'Отправить уведомление',exact:true}).isDisabled());
  });
  await check('a manual finding without a protocol opens its own details and can be removed',async()=>{
    const f=await post(`/api/patients/${pid}/findings`,{code:'THYROID_NODULE',attributes:{sizeMm:12,tirads:3},doctor:'Тестовый врач'},201);
    assert.equal(f.protocolId,null); await open();
    await page.locator('.npc-finding-row').filter({hasText:f.name}).click();
    await page.getByText('Находка добавлена отдельно от протокола.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Удалить находку',exact:true}).click();
    await page.getByLabel('Причина',{exact:true}).fill('Завершение синтетического теста');
    await page.getByRole('button',{name:'Удалить',exact:true}).click();
    await page.getByRole('dialog').waitFor({state:'hidden'});
    assert.ok(!(await get(`/api/patients/${pid}`)).currentFindings.some(x=>x.id===f.id));
  });
  assert.deepEqual(errors,[]);
} catch(e) {process.exitCode=1;console.error(e);await page.screenshot({path:resolve(out,'live-failure.png'),fullPage:true});}
finally {await writeFile(resolve(out,'live-results.json'),JSON.stringify({results,errors},null,2));await browser.close();}
