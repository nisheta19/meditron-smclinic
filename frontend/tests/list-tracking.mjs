// Synthetic real-API regression. Run after integration.py, with fresh frontend_fixtures.py.
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { readFile,writeFile,mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { signIn } from './auth-support.mjs';
const root=resolve(import.meta.dirname,'../..'),out=resolve(root,'.local/list-tracking');await mkdir(out,{recursive:true});
const fixture=JSON.parse(await readFile(resolve(root,'.local/frontend-fixtures.json'),'utf8'));
const base=process.env.FRONTEND_URL || 'http://127.0.0.1:13000';
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1920,height:1080}});await signIn(context,base);
const page=await context.newPage();page.setDefaultTimeout(15000);
const errors=[],results=[];page.on('pageerror',e=>errors.push(e.message));
const check=async(name,fn)=>{await fn();results.push(name);console.log('PASS '+name);};
const get=async path=>{const r=await context.request.get(base+path);assert.equal(r.status(),200,await r.text());return r.json();};
const post=async(path,data,status)=>{const token=await get('/api/auth/csrf');const r=await context.request.post(base+path,{data,headers:{[token.headerName]:token.token}});assert.equal(r.status(),status,await r.text());return r.json();};
const p=fixture.cases.positive;
const summary=async()=>{const data=await get('/api/patients?search='+encodeURIComponent(p.externalId));return data.items.find(x=>x.id===p.id);};
const open=async()=>{await page.goto(base+'/#/findings?q='+p.externalId);await page.reload();await page.locator('.row-card').waitFor();};
let route;
try{
  await check('unrouted finding and emergency never borrow another route or invent progress',async()=>{
    for(const c of [p,fixture.cases.emergency]){
      const data=await get('/api/patients?search='+encodeURIComponent(c.externalId));const row=data.items[0];
      assert.equal(row.tracking.routeId,null);assert.equal(row.tracking.progressPercent,null);
      assert.equal(row.tracking.notificationCount,0);assert.equal(row.tracking.lastNotifiedAt,null);
    }
    await open();assert.equal(await page.getByRole('progressbar').count(),0);
    assert.equal((await page.locator('.cell-notified').innerText()).trim(),'Не уведомлён\n0 уведомлений');
  });
  await check('confirmation creates a real route and list refresh picks up progress',async()=>{
    await post(`/api/patients/${p.id}/findings/confirm`,{findingIds:p.findings.map(f=>f.id)},200);
    route=(await get(`/api/patients/${p.id}/routes`)).find(r=>r.open);assert.ok(route);
    const s=(await summary()).tracking;assert.equal(s.routeId,route.id);assert.equal(s.stage,route.stage);
    assert.equal(s.progressPercent,10);
    await page.getByRole('progressbar').waitFor();assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'),'10');
  });
  await check('successful send changes stage, count and last notification in the row',async()=>{
    await post(`/api/routes/${route.id}/notifications`,{templateCode:'INITIAL',confirm:true},201);
    await page.getByText('20% пройдено',{exact:true}).waitFor();
    const s=(await summary()).tracking;
    assert.equal(s.stage,'NOTIFIED');assert.ok(s.lastNotifiedAt);assert.ok(s.notificationCount>=1);
    await page.locator('.cell-notified .s-main').filter({hasText:'Сегодня'}).waitFor();
    await page.screenshot({path:resolve(out,'live-list.png'),animations:'disabled'});
  });
  await check('failed delivery is excluded, READ remains counted once',async()=>{
    const n=await post(`/api/routes/${route.id}/notifications`,{templateCode:'REMINDER_24H',confirm:true},201);
    await post('/api/integration/crm/callbacks',{eventId:randomUUID(),messageId:n.id,status:'FAILED'},202);
    let notes=await get(`/api/patients/${p.id}/notifications`);
    let successes=notes.filter(x=>x.delivery!=='FAILED');
    let s=(await summary()).tracking;assert.equal(s.notificationCount,successes.length);
    assert.equal(s.lastNotifiedAt,successes.map(x=>x.sentAt).sort().at(-1));
    await post('/api/integration/crm/callbacks',{eventId:randomUUID(),messageId:successes[0].id,status:'READ'},202);
    s=(await summary()).tracking;assert.equal(s.notificationCount,successes.length);
  });
  await check('real booking and visit advance the bar; clinical completion reaches 100%',async()=>{
    const slot=(await get(`/api/schedule/slots?routeId=${route.id}`))[0];
    await post('/api/integration/route-events',{eventId:randomUUID(),routeId:route.id,type:'BOOKED',slotId:slot.id},202);
    await page.getByText('30% пройдено',{exact:true}).waitFor();
    await post('/api/integration/route-events',{eventId:randomUUID(),routeId:route.id,type:'VISIT_COMPLETED'},202);
    assert.equal((await summary()).tracking.progressPercent,40);
    await post('/api/integration/route-events',{eventId:randomUUID(),routeId:route.id,type:'TACTIC_SELECTED',tactic:'SURGERY_NOT_INDICATED'},202);
    await page.getByText('100% пройдено',{exact:true}).waitFor();
  });
  await check('stage and notified sort on the server before pagination, including nulls',async()=>{
    const search=fixture.cases.positive.externalId.replace(/-positive$/,'');
    for(const [key,label,field] of [['stage','Этап','progressPercent'],['notified','Уведомлён','lastNotifiedAt']]){
      for(const direction of ['asc','desc']){
        const data=await get(`/api/patients?search=${search}&sortBy=${key}&sortDirection=${direction}&size=200`);
        const vals=data.items.map(x=>x.tracking?.[field]??null);let seenNull=false;
        const known=[];for(const v of vals){if(v===null)seenNull=true;else{assert.equal(seenNull,false);known.push(v);}}
        assert.deepEqual(known,[...known].sort((a,b)=>(a<b?-1:a>b?1:0)*(direction==='asc'?1:-1)));
        const first=await get(`/api/patients?search=${search}&sortBy=${key}&sortDirection=${direction}&size=1`);
        assert.equal(first.items[0].id,data.items[0].id);
        const response=page.waitForResponse(r=>{const u=new URL(r.url());return u.pathname==='/api/patients'&&u.searchParams.get('sortBy')===key&&u.searchParams.get('sortDirection')===direction;});
        await page.locator('.rowlist-head').getByRole('button',{name:label,exact:true}).click();assert.equal((await response).status(),200);
      }
    }
  });
  assert.deepEqual(errors,[]);
}catch(e){process.exitCode=1;console.error(e);await page.screenshot({path:resolve(out,'failure.png'),fullPage:true});}
finally{await writeFile(resolve(out,'live-results.json'),JSON.stringify({results,errors,passed:!process.exitCode},null,2));await browser.close();}
