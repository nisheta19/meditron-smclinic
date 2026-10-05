// Regression checks for the 14 supplied design comments. Fictional API responses only.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {patients,patientCard,protocol} from './design-fixtures.mjs';
const base=process.env.FRONTEND_URL || 'http://127.0.0.1:5173';
const out=resolve('../.local/ui-review'); await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1280,height:832},timezoneId:'Europe/Moscow'});
const results=[],errors=[];let authenticated=false,smallHistory=false;
const route={id:'review-route',protocolId:protocol.id,open:true,specialty:'Эндокринолог',routeType:'OBSERVATION',chainType:'OBSERVATION',stage:'OBSERVATION_WAITING_US',dueAt:'2026-12-01T09:00:00Z',stageHistory:[],findings:[],openTasks:[]};
const reviewedProtocol={...protocol,flags:[{code:'REVIEW_TEST',note:'Контрольный флаг'}],notTriggered:[{code:'THYROID_NODULE',reason:'NEGATED',evidence:{text:'узлов нет'}}]};
const templates=[{code:'REMINDER_24H',title:'Напоминание о записи',manual:true},{code:'NO_SHOW',title:'После неявки',manual:true},{code:'FIRST_MESSAGE',title:'Результат готов',manual:true}];
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/**',r=>{
  const req=r.request(),u=new URL(req.url()),path=u.pathname;
  if(!path.startsWith('/api/')) return r.continue();
  if(path==='/api/auth/me') return r.fulfill({status:authenticated?200:401,json:authenticated?{login:'123',roles:['DOCTOR']}:{code:'UNAUTHORIZED'}});
  assert.equal(req.method(),'GET','UI checks must not mutate patient data');
  const body=path==='/api/patients'?{items:Array.from({length:12},(_,i)=>({...patients[i%4],id:'list-'+i})),total:12,page:0,size:50}:
    path==='/api/notification-templates'?templates:
    path.endsWith('/notification-preview')?{templateCode:u.searchParams.get('templateCode'),fullText:'Напоминание: по результату УЗИ Вам рекомендована консультация эндокринолога.'}:
    path.endsWith('/notifications')?[{id:'message',routeId:route.id,fullText:'Результат учебного исследования готов.',sentAt:'2026-10-05T09:00:00Z',readAt:'2026-10-05T10:00:00Z',bookedAfter:true}]:
    path.startsWith('/api/patients/')?{...patientCard,clinicalRoutes:[route],history:smallHistory?{protocols:[],findings:[],routes:[]}:patientCard.history}:
    path.startsWith('/api/protocols/')?{...reviewedProtocol,id:path.split('/').at(-1)}:
    path==='/api/dictionary/findings'?(u.searchParams.get('full')==='true'?{findings:[{code:'THYROID_NODULE',name:'Узел щитовидной железы',active:true,attributes:['sizeMm'],studyTypes:['THYROID']}]}:[{code:'THYROID_NODULE',name:'Узел щитовидной железы',active:true}]):[];
  return r.fulfill({json:body});
});
const check=async(name,fn)=>{await fn();results.push({name,passed:true});console.log('PASS '+name);};
const ready=async()=>{await page.evaluate(()=>document.fonts.ready);await page.locator('main').evaluate(el=>Promise.all(el.getAnimations({subtree:true}).map(a=>a.finished)));};
const gray=async locator=>{
  await locator.focus();
  const s=await locator.evaluate(el=>{const s=getComputedStyle(el);return {outline:s.outlineColor,border:s.borderColor,shadow:s.boxShadow,width:s.outlineWidth};});
  assert.ok(![s.outline,s.border,s.shadow].some(v=>v.includes('19, 171, 123')),JSON.stringify(s));
  assert.equal(s.shadow,'none');
};
try{
  await page.goto(base);await page.locator('.auth-submit:enabled').waitFor();await page.evaluate(()=>document.fonts.ready);
  await check('01 login logo retains the supplied position',async()=>{const b=await page.locator('.auth-logo').boundingBox();assert.deepEqual([b.x,b.y,b.width,b.height],[213,89,395,63]);});
  await check('02 login fields have no green focus ring',async()=>{await gray(page.getByLabel('Логин',{exact:true}));await gray(page.getByLabel('Пароль',{exact:true}));await page.screenshot({path:resolve(out,'login-focus.png'),animations:'disabled'});});
  authenticated=true;await page.reload();await page.locator('.row-card').first().waitFor();await ready();
  await check('03 profile has no hover background or redundant name tooltip',async()=>{
    const p=page.locator('.doctor-menu-trigger');const before=await p.evaluate(el=>getComputedStyle(el).backgroundColor);await p.hover();
    assert.equal(await p.evaluate(el=>getComputedStyle(el).backgroundColor),before);assert.equal(await p.getAttribute('title'),null);await gray(p);
  });
  await check('13 long lists end with a small bottom margin',async()=>{await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));const b=await page.locator('.row-card').last().boundingBox();assert.ok(832-b.y-b.height<40);});
  await check('14 pending findings are not colored red',async()=>{for(const el of await page.locator('.cell-finding .s-main').all())assert.equal(await el.evaluate(e=>getComputedStyle(e).color),'rgb(0, 0, 0)');});
  await page.goto(base+'/#/patients/design-0');await page.locator('.npc-card').waitFor();await ready();
  await check('04 patient name uses three separate lines',async()=>assert.deepEqual(await page.locator('.npc-person h1 > span').allTextContents(),['Фамилия','Имя','Отчество']));
  await check('05 history arrows point right',async()=>assert.equal(await page.locator('.npc-event .npc-chevron').first().evaluate(e=>getComputedStyle(e).transform),'none'));
  await check('06 route keeps its columns and rotates only its expand arrow',async()=>{
    const row=page.locator('.npc-route-row');await gray(row);const before=await row.boundingBox();await row.click();
    assert.equal(await row.getAttribute('aria-expanded'),'true');assert.equal(await row.locator('svg').evaluate(e=>getComputedStyle(e).transform),'matrix(0, 1, -1, 0, 0, 0)');
    assert.deepEqual(await row.boundingBox(),before);await row.click();assert.equal(await row.getAttribute('aria-expanded'),'false');
  });
  await check('07 notification header columns align with row columns',async()=>{const h=await page.locator('.npc-notification-head > *').all();const cells=await page.locator('.npc-notification-row > span').all();for(let i=0;i<h.length;i++)assert.ok(Math.abs((await h[i].boundingBox()).x-(await cells[i].boundingBox()).x)<1);});
  await check('08 notification route selection stays gray and message stays in place',async()=>{
    await page.locator('.npc-notify').click();await page.getByText(/^Напоминание: по результату/).waitFor();
    const select=page.getByRole('combobox',{name:'Маршрут',exact:true});await gray(select);await select.press('Space');await page.keyboard.press('Enter');
    const b=await page.locator('.notify-preview > p').boundingBox();const modal=await page.locator('.clinical-notify').boundingBox();assert.ok(b.x>=modal.x && b.x+b.width<=modal.x+modal.width);
    await page.screenshot({path:resolve(out,'notification-focus.png'),animations:'disabled'});await page.getByRole('button',{name:'Отмена',exact:true}).click();
  });
  await check('09 sorting headings and rows have gray keyboard focus',async()=>{await gray(page.locator('.npc-findings .npc-colhead').last());await gray(page.locator('.npc-finding-row').first());});
  await check('11 history uses ten real response items and More reveals the rest',async()=>{assert.equal(await page.locator('.npc-event').count(),10);await page.locator('.npc-history-more').click();assert.equal(await page.locator('.npc-event').count(),11);});
  await page.locator('.npc-event').first().click();await page.locator('.protocol-text').waitFor();await ready();
  await check('10 no sort is preselected in the protocol',async()=>{
    assert.equal(await page.locator('.protocol-review .col-head.active').count(),0);assert.equal(await page.locator('.protocol-review .col-head .asc').count(),0);
    await page.locator('.protocol-review .col-head').nth(1).click();assert.equal(await page.locator('.protocol-review .col-head.active').count(),1);await gray(page.locator('.pc-row-main').first());
  });
  await check('12 add controls follow design; extra explanations are inside More',async()=>{
    for(const b of await page.locator('.protocol-review .pc-add').all())assert.equal(await b.evaluate(e=>getComputedStyle(e).borderTopStyle),'dotted');
    assert.equal(await page.locator('.protocol-review > .pc-nt, .protocol-review > .pc-flags').count(),0);
    await page.locator('.npc-more').click();await page.getByText('Контрольный флаг').waitFor();await page.getByText('Почему не стало находкой (1)').waitFor();
    await page.getByRole('button',{name:'Закрыть',exact:true}).first().click();
    await page.locator('.protocol-review > .pc-add').click();await page.locator('textarea').waitFor();await gray(page.locator('textarea'));
    await page.screenshot({path:resolve(out,'finding-form-focus.png'),animations:'disabled'});await page.getByRole('button',{name:'Отмена',exact:true}).click();
  });
  smallHistory=true;await page.reload();await page.locator('.npc-card').waitFor();assert.equal(await page.locator('.npc-event').count(),1);assert.ok(await page.locator('.npc-history-more').isDisabled());
  for(const width of [390,768,1024,1280,1920]){await page.setViewportSize({width,height:900});await ready();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
  assert.deepEqual(errors,[]);
}finally{await writeFile(resolve(out,'results.json'),JSON.stringify({results,errors},null,2));await browser.close();}
