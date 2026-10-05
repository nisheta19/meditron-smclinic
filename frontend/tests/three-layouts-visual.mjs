// Supplied design content, only in the visual harness. No patient writes.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const out=resolve(import.meta.dirname,'../../.local/three-layouts');await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1280,height:1625},deviceScaleFactor:1,timezoneId:'Europe/Moscow'});
const text=`ЩИТОВИДНАЯ ЖЕЛЕЗА
РАСПОЛОЖЕНИЕ: обычно
КОНТУРЫ: ровные, четкие
РАЗМЕРЫ:
ПРАВАЯ ДОЛЯ щитовидной железы: 25х24х41 мм. Объем доли 12,9 см куб.
ЛЕВАЯ ДОЛЯ щитовидной железы: 19,3х18,5х43,8 мм. Объем доли 8,2 см куб.
ПЕРЕШЕЕК ЖЕЛЕЗЫ толщиной до 4,0 мм.
ОБЩИЙ ОБЪЕМ ЖЕЛЕЗЫ 21,1 см. куб. (N женщины 4,4–18 см. куб., беременные 5–20 см. куб., мужчины 8–25 см. куб.)
ЭХОСТРУКТУРА: умеренно диффузно неоднородная
УЗЛОВЫЕ ОБРАЗОВАНИЯ:
В ПРАВОЙ ДОЛЕ: достоверно не выявлены.
В ЛЕВОЙ ДОЛЕ: визуализируются гетерогенные узлы, с перинодулярным кровотоком, размерами до 6,6х3,9мм (ближе к области перешейка) и 6,7х3,8мм (в центральной части), так же, анэхогенный, аваскулярный узел 9,4х6мм (в нижнем полюсе)
ЭХОГЕННОСТЬ: смешанная, преимущественно снижена.
СОСУДИСТЫЙ РИСУНОК ПАРЕНХИМЫ: умеренный
РЕГИОНАРНЫЕ ЛИМФОУЗЛЫ: не изменены
ЗАКЛЮЧЕНИЕ:
Ультразвуковые признаки узлов левой доли, на фоне умеренных диффузных изменений щитовидной железы
Ti-rads-2`;
const findings=['визуализируются гетерогенные узлы','Ультразвуковые признаки узлов левой доли'].map((quote,i)=>({id:'vf-'+i,name:'Полип яичника',status:'SUGGESTED',level:i?'URGENT':'EMERGENCY',protocolId:'visual-protocol',evidence:{text:quote,start:text.indexOf(quote),end:text.indexOf(quote)+quote.length}}));
await page.route('**/api/**',r=>{
  const path=new URL(r.request().url()).pathname;
  if(!path.startsWith('/api/')) return r.continue();
  assert.equal(r.request().method(),'GET');
  const body=path.includes('/protocols/')?{id:'visual-protocol',receivedAt:'2026-07-13T10:14:00Z',studyType:'THYROID',status:'DONE',conclusionFound:true,text,findings}:
    path.endsWith('/notification-templates')?[{code:'REMINDER_24H',title:'Напоминание о записи',manual:true},{code:'NO_SHOW',title:'После неявки',manual:true},{code:'SECOND',title:'После неявки',manual:true}]:
    path.endsWith('/notification-preview')?{templateCode:'REMINDER_24H',fullText:'Напоминание: по результату УЗИ Вам рекомендована консультация хирурга. Консультация нужна, чтобы уточнить результат исследования. Вы можете выбрать удобный формат — очно: [ссылка]'}:[];
  return r.fulfill({json:body});
});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const geometry={};
try {
  for(const mode of ['overview','review','notify']) {
    await page.setViewportSize({width:1280,height:mode==='review'?1697:1625});
    await page.goto('http://127.0.0.1:5173/tests/patient-card-visual.html?mode='+mode);
    await page.locator('.npc-card').waitFor();
    if(mode==='review') await page.locator('.protocol-text').waitFor();
    if(mode==='notify') await page.getByText(/Напоминание: по результату/).waitFor();
    await page.evaluate(()=>document.fonts.ready);
    await page.screenshot({path:resolve(out,mode+'.png'),fullPage:true,animations:'disabled'});
    geometry[mode]=await page.evaluate(()=>Object.fromEntries(['.npc-card','.pc-protocol','.review-findings-heading','.review-routes','.review-save','.clinical-notify'].filter(s=>document.querySelector(s)).map(s=>{const {x,y,width,height}=document.querySelector(s).getBoundingClientRect();return [s,{x,y,width,height}]})));
    const near=(actual,expected)=>assert.ok(Math.abs(actual-expected)<2,`${mode}: ${actual} != ${expected}`);
    if(mode==='review') {
      near(geometry[mode]['.pc-protocol'].y,485); near(geometry[mode]['.pc-protocol'].height,478);
      near(geometry[mode]['.review-save'].y,1589); near(geometry[mode]['.npc-card'].height,1504);
    }
    if(mode==='notify') for(const [key,value] of Object.entries({x:330,y:466,width:621,height:600})) near(geometry[mode]['.clinical-notify'][key],value);
    for(const width of [390,768,1024,1920]) {
      await page.setViewportSize({width,height:1000});
      await page.locator('main').evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished)));
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${mode} overflow ${width}`);
      if(width===1920) {
        assert.equal(await page.locator('.layout').evaluate(el=>Number(getComputedStyle(el).zoom)),1.5);
        if(mode==='overview') await page.screenshot({path:resolve(out,'overview-large.png'),fullPage:true,animations:'disabled'});
      }
    }
  }
  assert.deepEqual(errors,[]);
  await writeFile(resolve(out,'geometry.json'),JSON.stringify(geometry,null,2));
  console.log('PASS three mockups, no browser errors, responsive overflow at four widths');
} finally {await browser.close();}
