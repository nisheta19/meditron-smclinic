import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {patients} from './design-fixtures.mjs';
const base=process.env.FRONTEND_URL || 'http://127.0.0.1:13000';
const out=resolve('../.local/list-tracking');await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1248}});page.setDefaultTimeout(12000);
const errors=[],requests=[],results=[];page.on('pageerror',e=>errors.push(e.message));
const today=Date.now(),ago=d=>new Date(today-d*864e5).toISOString();
const rows=patients.map((p,i)=>({...p,tracking:{routeId:'r'+i,stage:'BOOKED',stageTitle:'Записан',progressPercent:[10,40,80,100][i],lastNotifiedAt:ago([6,19,5,14][i]),notificationCount:[2,10,1,5][i]}}));
let failed=false,missing=false;
await page.route('**/api/**',r=>{
  const path=new URL(r.request().url()).pathname;if(!path.startsWith('/api/'))return r.continue();
  requests.push(path);assert.equal(r.request().method(),'GET');
  if(path==='/api/auth/me')return r.fulfill({json:{login:'123',roles:['DOCTOR']}});
  if(path==='/api/patients')return failed?r.fulfill({status:503,json:{message:'Проверка недоступности списка'}}):r.fulfill({json:{items:missing?rows.map((p,i)=>({...p,tracking:i?{routeId:null,stage:null,progressPercent:null,notificationCount:0,lastNotifiedAt:null}:null})):rows,total:4,page:0,size:50}});
  return r.fulfill({json:[]});
});
const check=async(name,fn)=>{await fn();results.push(name);console.log('PASS '+name);};
try{
  await page.goto(base);await page.locator('.row-card').first().waitFor();await page.evaluate(()=>document.fonts.ready);
  await check('bar precedes percent and uses actual 10/40/80/100 values',async()=>{
    assert.deepEqual(await page.locator('.cell-stage .s-cap').allTextContents(),['10% пройдено','40% пройдено','80% пройдено','100% пройдено']);
    const values=await page.getByRole('progressbar').evaluateAll(es=>es.map(e=>({value:Number(e.getAttribute('aria-valuenow')),ratio:e.firstElementChild.getBoundingClientRect().width/e.getBoundingClientRect().width,barY:e.getBoundingClientRect().y,labelY:e.nextElementSibling.getBoundingClientRect().y})));
    for(const v of values){assert.ok(Math.abs(v.ratio-v.value/100)<.01);assert.ok(v.barY<v.labelY);}
    assert.equal(await page.locator('.cell-stage .p-name').count(),0);
    await page.screenshot({path:resolve(out,'design-1920.png'),animations:'disabled'});
  });
  await check('last successful date and plural notification counts match source data',async()=>{
    assert.deepEqual(await page.locator('.cell-notified .s-main').allTextContents(),['6 дней назад','19 дней назад','5 дней назад','14 дней назад']);
    assert.deepEqual(await page.locator('.cell-notified .s-sub').allTextContents(),['2 уведомления','10 уведомлений','1 уведомление','5 уведомлений']);
  });
  await check('large and narrow layouts keep progress and notification columns readable',async()=>{
    for(const width of [1280,768,390]){
      await page.setViewportSize({width,height:1000});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await page.screenshot({path:resolve(out,`design-${width}.png`),animations:'disabled'});
    }
  });
  await check('unknown tracking differs from known zero messages and no route',async()=>{
    missing=true;await page.reload();await page.locator('.row-card').first().waitFor();
    assert.equal(await page.getByRole('progressbar').count(),0);
    assert.equal((await page.locator('.cell-notified').first().innerText()).trim(),'—\n—');
    assert.equal((await page.locator('.cell-notified').nth(1).innerText()).trim(),'Не уведомлён\n0 уведомлений');
  });
  await check('API failure is visible and never replaced with fabricated zero values',async()=>{
    failed=true;await page.reload();await page.locator('.error-box').waitFor();assert.equal(await page.locator('.row-card').count(),0);
    failed=false;await page.getByRole('button',{name:'Повторить',exact:true}).click();await page.locator('.row-card').first().waitFor();
    assert.ok(!requests.some(p=>/\/patients\/.+/.test(p)||p.includes('notifications')||p.includes('routes')),'List must not fetch individual cards or notifications');
  });
  assert.deepEqual(errors,[]);
}catch(e){process.exitCode=1;console.error(e);await page.screenshot({path:resolve(out,'visual-failure.png'),fullPage:true});}
finally{await writeFile(resolve(out,'visual-results.json'),JSON.stringify({results,errors,passed:!process.exitCode},null,2));await browser.close();}
