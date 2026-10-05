import test from 'node:test';
import assert from 'node:assert/strict';
import { fromFinalPatient } from '../src/components/patient-card/fromFinalPatient.js';
import { sortRows } from '../src/components/patient-card/sortRows.js';

test('clinical routes preserve server specialty, stage, tasks and booked appointment', () => {
  const r = {id:'r',open:true,specialty:'Эндокринолог',routeType:'OBSERVATION',stage:'BOOKED',stageTitle:'Записан',
    dueAt:'2026-10-10T21:00:00Z',controlAt:'2026-10-01T09:00:00Z',overdueDays:null,appointment:{status:'BOOKED',dateTime:'2026-10-09T10:21:00Z'},
    stageHistory:[{stage:'CREATED',at:'2026-10-01T07:00:00Z'}],findings:[{id:'f',name:'Узел'}],
    openTasks:[{text:'Связаться',role:'MANAGER',dueAt:'2026-10-10T09:00:00Z'}],tactic:'OBSERVATION'};
  const p=fromFinalPatient({clinicalRoutes:[r],currentFindings:[],history:{protocols:[{id:'old',studyType:'THYROID'}],findings:[{id:'f',protocolId:'old',name:'Узел',status:'CONFIRMED'}]}});
  assert.equal(p.routes[0].specialist,'Эндокринолог'); assert.equal(p.routes[0].type,'Наблюдение');
  assert.equal(p.routes[0].due,'до 11.10.2026'); assert.equal(p.routes[0].visit,'09.10.2026 · 13:21');
  assert.deepEqual(p.routes[0].details.stages,['01.10 · 10:00 Создан']);
  assert.deepEqual(p.routes[0].details.findings,['Узел · Щитовидная железа']);
  assert.equal(p.findings[0].id,'f'); assert.match(p.routes[0].details.task,/менеджер/);
  r.appointment.status='CANCELLED'; r.overdueDays=2;
  const updated=fromFinalPatient({clinicalRoutes:[r]});
  assert.equal(updated.routes[0].visit,null); assert.equal(updated.routes[0].overdue,true);
});

test('closed routes are history and notifications use real read and booking fields', () => {
  const closed={id:'old-route',open:false,specialty:'Хирург',stage:'CLOSED',stageTitle:'Закрыт: отказ пациента',closedAt:'2026-10-01T09:00:00Z'};
  const p=fromFinalPatient({clinicalRoutes:[],history:{clinicalRoutes:[closed]}},{notifications:[{id:'n',routeId:closed.id,fullText:'Текст',shortText:'Коротко',sentAt:'2026-09-01T09:00:00Z',readAt:'2026-09-02T09:00:00Z',bookedAfter:false}]});
  assert.deepEqual(p.routes,[]); assert.equal(p.history[0].kind,'route'); assert.match(p.history[0].subtitle,/отказ/);
  assert.equal(p.notifications[0].message,'Текст'); assert.equal(p.notifications[0].route,'Хирург');
  assert.equal(p.notifications[0].read,'02.09.2026 · 12:00'); assert.equal(p.notifications[0].booked,false);
});

test('rejected emergency finding is not presented as an active emergency', () => {
  const p=fromFinalPatient({currentFindings:[{id:'f',status:'REJECTED',level:'EMERGENCY'}]});
  assert.equal(p.findings[0].status,'Отклонена'); assert.equal(p.findings[0].urgent,false);
});

test('nested and flattened API responses produce the same view', () => {
  const p = {externalId:'MIS-3',lastName:'Иванова-Петрова',firstName:'Анна Мария',middleName:null,birthDate:'1966-02-10',sex:'F'};
  assert.deepEqual(fromFinalPatient({patient:p,routes:[]}),fromFinalPatient({...p,routes:[]}));
  assert.deepEqual(fromFinalPatient(p).name,['Иванова-Петрова','Анна Мария']);
  assert.equal(fromFinalPatient(p).birthDate,'10.02.1966');
});
test('missing API values never fall back to the screenshot fixture', () => {
  const p = fromFinalPatient({id:'internal-1',fullName:'Тестовый пациент'});
  for (const key of ['id','age','sex','blood','bmi','height','weight','email','phone','snils']) assert.equal(p[key],null);
  for (const key of ['routes','notifications','findings','history']) assert.deepEqual(p[key],[]);
  assert.equal(fromFinalPatient(null),null);
});
test('finding level is displayed directly without recalculating medical urgency', () => {
  const p = fromFinalPatient({currentProtocol:{id:'p',studyType:'THYROID'},currentFindings:[
    {id:'a',protocolId:'p',level:'PLANNED',targetDays:0,status:'CONFIRMED'},
    {id:'b',protocolId:'missing',level:'EMERGENCY',status:'SUGGESTED'},
    {id:'c',protocolId:'p',level:'URGENT',status:'REMOVED'}
  ]});
  assert.equal(p.findings.length,2);
  assert.equal(p.findings[0].status,'Планово'); assert.equal(p.findings[0].urgent,false);
  assert.equal(p.findings[0].organ,'Щитовидная железа');
  assert.equal(p.findings[1].urgent,true); assert.equal(p.findings[1].organ,null);
});
test('no read receipt or appointment is invented from notification sentAt', () => {
  const p = fromFinalPatient({}, {notifications:[{id:'n',text:'Сообщение',sentAt:'2026-10-09T10:21:00Z'}]});
  assert.equal(p.notifications[0].sent,'09.10.2026 · 13:21');
  assert.equal(p.notifications[0].read,null); assert.equal(p.notifications[0].booked,null);
});
test('history shows actual protocol status and newest first, preserving source IDs', () => {
  const p = fromFinalPatient({currentProtocol:{id:'b',receivedAt:'2026-07-13T10:14:00Z',status:'FAILED'},history:{protocols:[{id:'a',receivedAt:'2026-06-01T10:00:00Z',status:'DONE'}]}});
  assert.deepEqual(p.history.map(x=>[x.id,x.subtitle]),[['b','Ошибка обработки'],['a','Результат']]);
  assert.equal(p.history[0].source.id,'b');
});
test('date columns sort chronologically across months; unknown values stay last', () => {
  const rows=[{date:'до 09.11.2026'},{date:'до 10.10.2026'},{date:null}];
  assert.deepEqual(sortRows(rows,{key:'date',direction:1}).map(x=>x.date),['до 10.10.2026','до 09.11.2026',null]);
  assert.deepEqual(sortRows(rows,{key:'date',direction:-1}).map(x=>x.date),['до 09.11.2026','до 10.10.2026',null]);
  assert.equal(rows[0].date,'до 09.11.2026');
});
