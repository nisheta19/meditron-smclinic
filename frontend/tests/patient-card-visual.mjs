import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const base=process.env.FRONTEND_URL || 'http://127.0.0.1:5173';
const out=resolve(import.meta.dirname,'../../.local/patient-card');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true,args:['--disable-lcd-text','--font-render-hinting=none']});
const page=await browser.newPage({viewport:{width:1280,height:1625},deviceScaleFactor:2});
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.setDefaultTimeout(10000);
try {
  await page.goto(`${base}/tests/patient-card-visual.html`); await page.locator('.npc-card').waitFor(); await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:resolve(out,'reference-render.png'),fullPage:true});
  const geometry=await page.evaluate(()=>Object.fromEntries(['.npc-search','.npc-card','.npc-route-row','.npc-route-details','.npc-notification-row','.npc-notify','.npc-finding-row','.npc-history'].map(s=>{const {x,y,width,height}=document.querySelector(s).getBoundingClientRect();return [s,{x,y,width,height}]})));
  await writeFile(resolve(out,'geometry.json'),JSON.stringify(geometry,null,2));
  assert.equal(geometry['.npc-card'].x,212); assert.equal(geometry['.npc-card'].width,1052);
  assert.equal(geometry['.npc-card'].y,169); assert.equal(geometry['.npc-card'].height,1431);
  for(const [s,y,h] of [['.npc-route-row',498,78],['.npc-route-details',661,231],['.npc-notification-row',1074,79],['.npc-notify',1252,48],['.npc-finding-row',1395,52]]) {
    assert.equal(geometry[s].y,y,`${s} y`); assert.equal(geometry[s].height,h,`${s} height`);
  }
  await page.getByRole('button',{name:'Маршрут: Эндокринолог',exact:true}).click(); assert.equal(await page.locator('.npc-route-details').count(),0);
  await page.keyboard.press('Enter'); assert.equal(await page.locator('.npc-route-details').count(),1);
  for(const label of ['Этап','Посетить до','Дата посещения','Сообщение','Маршрут','Дата отправки','Прочитано','Запись','Орган','Находка','Статус']) {
    await page.getByRole('button',{name:`Сортировать: ${label}`,exact:true}).click();
    await page.getByRole('button',{name:`Сортировать: ${label}`,exact:true}).click();
  }
  for(const width of [390,768,1024,1280,1920]) {
    await page.setViewportSize({width,height:1000});
    await page.locator('main').evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished)));
    const overflow=await page.evaluate(()=>({width:document.documentElement.scrollWidth,nodes:[...document.querySelectorAll('main *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1 && getComputedStyle(e).overflowX!=='auto').map(e=>[e.className,e.getBoundingClientRect().x,e.getBoundingClientRect().width]).slice(0,20)}));
    assert.ok(overflow.width<=width+1,`Overflow ${width}: ${JSON.stringify(overflow)}`);
    await page.screenshot({path:resolve(out,`reference-${width}.png`),fullPage:true});
  }
  assert.deepEqual(errors,[]); console.log('PASS reference geometry, route expansion, all sort headers, 5 responsive widths');
} finally {await browser.close();}
