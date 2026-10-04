// Заглушка backend: in-memory реализация openapi.yaml. Данные — сообщения MlResult из docs/ml-results,
// которые проходят ту же обработку, что описана для POST /api/integration/ml/results.
import samples from '../../../docs/ml-results/samples.json';
import demoResults from '../../../docs/ml-results/demo.json';
import queue from '../../../docs/ml-results/demo-queue.json';
import { DICTIONARY, TEMPLATES, SCENARIOS, LADDER } from './seed';
import { ApiError } from '../client';

const DAY = 864e5, H = 36e5;
const DICT_VERSION = 'dict-v3';
const COORDINATOR = 'Орлова Е. А., координатор';
const DOCTOR = 'Петрова И. В., врач УЗД';
const OPEN = ['ACTIVE', 'NOT_ENGAGED'];
// Поля, которые реальный backend отдаёт сверх openapi: level, flags, maxLevel, topFindings…
const levelOf = (e) => (e.urgent ? 'EMERGENCY' : e.targetDays <= 5 ? 'URGENT' : 'PLANNED');
const RANK = { EMERGENCY: 3, URGENT: 2, PLANNED: 1 };
const DONE = ['COMPLETED', 'SKIPPED', 'CANCELLED'];

let clock = Date.parse('2026-10-03T09:00:00+03:00');
let seq = 0;
const nextId = (p) => `${p}-${String(++seq).padStart(4, '0')}`;
const iso = (t = clock) => new Date(t).toISOString();
const day = (t = clock) => iso(t).slice(0, 10);

const db = {
  results: new Set(), patients: [], protocols: [], findings: [], routes: [], notifications: [],
  dictionary: structuredClone(DICTIONARY), templates: structuredClone(TEMPLATES),
};

const fail = (status, code, message) => { throw new ApiError(status, code, message); };
const byId = (list, id, what) => list.find((x) => x.id === id) ?? fail(404, `${what}_NOT_FOUND`, 'Объект не найден');
const dict = (code) => db.dictionary.find((d) => d.code === code);
const finding = (id) => db.findings.find((f) => f.id === id);
const current = (rt) => rt.steps.find((s) => s.id === rt.currentStepId);

// { minSizeMm: 10 } → attributes.sizeMm >= 10. Если атрибута нет, условие не блокирует находку.
const meets = (conditions = {}, attrs = {}) => Object.entries(conditions).every(([k, v]) => {
  const a = attrs[k.replace(/^min(.)/, (_, c) => c.toLowerCase())];
  return !k.startsWith('min') || a == null || a >= v;
});

const withOffsets = (ev, text) => {
  if (ev.start != null || !text) return { start: null, end: null, ...ev };
  const i = text.indexOf(ev.text);
  return { ...ev, start: i < 0 ? null : i, end: i < 0 ? null : i + ev.text.length };
};

// ---------- Приём результата ML ----------
function ingest(r, at = clock) {
  if (db.results.has(r.resultId)) return null;
  db.results.add(r.resultId);
  let p = db.patients.find((x) => x.externalId === r.patient.externalId);
  if (!p) db.patients.push(p = { id: nextId('pat'), ...r.patient, cardNumber: `АК-${r.patient.externalId.replace(/\D/g, '')}` });
  let pr = db.protocols.find((x) => x.externalId === r.protocol.externalId);
  if (pr && pr.version >= r.protocol.version) return p.id;

  if (r.status === 'ANNULLED') {
    if (!pr) return p.id;
    Object.assign(pr, { status: 'ANNULLED', version: r.protocol.version, receivedAt: iso(at) });
    db.findings.filter((f) => f.protocolId === pr.id && f.status !== 'REMOVED').forEach((f) => {
      Object.assign(f, { status: 'REMOVED', comment: 'Протокол аннулирован' });
      if (f.routeId) cancel(byId(db.routes, f.routeId), 'PROTOCOL_ANNULLED');
    });
    return p.id;
  }

  if (!pr) db.protocols.push(pr = { id: nextId('prt'), patientId: p.id, externalId: r.protocol.externalId });
  const old = db.findings.filter((f) => f.protocolId === pr.id && f.source === 'ML' && f.status !== 'REMOVED');
  const kept = new Set();
  Object.assign(pr, {
    ...r.protocol, status: r.status, text: r.text ?? null, conclusion: r.conclusion ?? '', conclusionFound: !!r.conclusionFound,
    modelVersion: r.modelVersion, error: r.error ?? null, receivedAt: iso(at),
    notTriggered: (r.notTriggered ?? []).map((n) => ({ ...n, evidence: withOffsets(n.evidence, r.text) })),
  });

  for (const c of r.findings ?? []) {
    const e = dict(c.code), evidence = withOffsets(c.evidence, r.text);
    if (!e?.active) { pr.notTriggered.push({ code: c.code, evidence, reason: 'OUT_OF_SCOPE' }); continue; }
    if (!meets(e.conditions, c.attributes)) { pr.notTriggered.push({ code: c.code, evidence, reason: 'BELOW_THRESHOLD' }); continue; }
    const same = old.find((f) => f.code === c.code && !kept.has(f));
    const data = { evidence, attributes: c.attributes ?? {}, confidence: c.confidence ?? null, modelVersion: r.modelVersion };
    if (same) { kept.add(same); Object.assign(same, data); continue; } // новая версия протокола — без дублей
    db.findings.push({
      id: nextId('fnd'), patientId: p.id, protocolId: pr.id, code: c.code, name: e.name, status: 'SUGGESTED', source: 'ML',
      ...data, ruleVersion: DICT_VERSION, targetSpecialty: e.targetSpecialty, targetDays: e.targetDays, level: levelOf(e), flags: [],
      routeId: null, reviewedBy: null, reviewedAt: null, comment: null,
    });
  }
  old.filter((f) => !kept.has(f)).forEach((f) => {
    Object.assign(f, { status: 'REMOVED', comment: `Нет в версии ${pr.version} протокола` });
    if (f.routeId) cancel(byId(db.routes, f.routeId), 'PROTOCOL_UPDATED');
  });
  return p.id;
}

// ---------- Маршруты и уведомления ----------
function cancel(rt, reason) {
  if (!OPEN.includes(rt.status)) return;
  Object.assign(rt, { status: 'CANCELLED', cancelReason: reason, currentStepId: null });
  rt.steps.filter((s) => !DONE.includes(s.status)).forEach((s) => { s.status = 'CANCELLED'; });
}

function advance(rt) {
  const next = rt.steps.find((s) => !DONE.includes(s.status));
  rt.currentStepId = next?.id ?? null;
  if (!next && rt.status !== 'CANCELLED') rt.status = 'COMPLETED';
}

function buildRoutes(patientId, body = {}, at = clock) {
  byId(db.patients, patientId, 'PATIENT');
  const list = db.findings.filter((f) => f.patientId === patientId && f.status === 'CONFIRMED' && !f.routeId
    && (!body.findingIds?.length || body.findingIds.includes(f.id)));
  if (!list.length) fail(409, 'NO_CONFIRMED_FINDINGS', 'Нет подтверждённых находок без маршрута');
  return list.map((f) => {
    const e = dict(f.code);
    const tpl = db.templates.find((t) => t.code === (body.templateCode || e.routeTemplateCode)) ?? fail(400, 'TEMPLATE_NOT_FOUND', 'Шаблон маршрута не найден');
    const steps = tpl.steps.map((s) => {
      const consult = s.type === 'SPECIALIST_CONSULTATION';
      return { id: nextId('stp'), type: s.type, name: consult ? `Консультация: ${e.targetSpecialty.toLowerCase()}` : s.name,
        status: 'PENDING', dueDate: day(at + (consult ? e.targetDays ?? s.dueInDays : s.dueInDays) * DAY), completedAt: null };
    });
    const rt = { id: nextId('rte'), patientId, findingIds: [f.id], templateCode: tpl.code, status: 'ACTIVE', cancelReason: null,
      createdAt: iso(at), currentStepId: steps[0].id, steps };
    f.routeId = rt.id;
    db.routes.push(rt);
    return rt;
  });
}

function defaultText(rt, st, channel) {
  if (channel === 'SMS') return 'СМ-Клиника: для вас новое сообщение в личном кабинете. Открыть: sm.example/r/…';
  const spec = finding(rt.findingIds[0])?.targetSpecialty.toLowerCase();
  if (st.type === 'SPECIALIST_CONSULTATION') return `Ваш результат УЗИ готов. В исследовании описаны изменения, по которым рекомендуется консультация специалиста (${spec}) для определения дальнейшей тактики. Записаться очно или онлайн: sm.example/r/…`;
  if (st.type === 'FOLLOW_UP') return 'Вам рекомендован контрольный приём. Выберите удобное время в личном кабинете.';
  return `По вашему плану лечения запланирован этап «${st.name}». Подробности в личном кабинете.`;
}

const pushNote = (rt, st, channel, text, at, sentBy) => {
  const n = { id: nextId('ntf'), routeId: rt.id, stepId: st.id, channel, text, sentAt: iso(at), sentBy };
  db.notifications.push(n);
  return n;
};

function notify(routeId, body = {}, at = clock, by = COORDINATOR) {
  const rt = byId(db.routes, routeId, 'ROUTE');
  if (!OPEN.includes(rt.status)) fail(409, 'ROUTE_CLOSED', 'Маршрут закрыт');
  const st = current(rt);
  if (st.type === 'ESCALATION') fail(409, 'URGENT_ESCALATION_ONLY', 'Экстренная находка: пациенту сообщения не отправляются, только эскалация персоналу');
  const last = db.notifications.filter((n) => n.routeId === routeId).reduce((m, n) => Math.max(m, Date.parse(n.sentAt)), 0);
  if (at - last < DAY) fail(429, 'TOO_FREQUENT', 'Не чаще одного уведомления в 24 часа по маршруту');
  const channel = body.channel ?? 'PERSONAL_ACCOUNT';
  const n = pushNote(rt, st, channel, body.text || defaultText(rt, st, channel), at, by);
  if (['PENDING', 'NO_SHOW'].includes(st.status)) st.status = 'NOTIFIED';
  rt.status = 'ACTIVE';
  return n;
}

function updateStep(routeId, stepId, { status, comment }, at = clock) {
  const rt = byId(db.routes, routeId, 'ROUTE');
  const st = rt.steps.find((s) => s.id === stepId) ?? fail(404, 'STEP_NOT_FOUND', 'Этап не найден');
  Object.assign(st, { status, comment: comment ?? st.comment ?? null, completedAt: ['COMPLETED', 'SKIPPED'].includes(status) ? iso(at) : null });
  if (rt.status === 'NOT_ENGAGED' && ['BOOKED', 'COMPLETED'].includes(status)) rt.status = 'ACTIVE';
  advance(rt);
  return rt;
}

// Модельное время: автонапоминания 1/3/14 дней и статус «не вовлечён» через 30 дней без записи
function tick(at = clock) {
  for (const rt of db.routes.filter((r) => r.status === 'ACTIVE')) {
    const st = current(rt);
    if (st !== rt.steps[0] || !['PENDING', 'NOTIFIED'].includes(st.status)) continue;
    const notes = db.notifications.filter((n) => n.routeId === rt.id);
    if (!notes.length) continue;
    const t0 = Math.min(...notes.map((n) => Date.parse(n.sentAt)));
    LADDER.forEach(([d, text]) => {
      const t = t0 + d * DAY;
      if (t <= at && !notes.some((n) => n._ladder === d)) Object.assign(pushNote(rt, st, 'PUSH', text, t, 'SYSTEM'), { _ladder: d });
    });
    if (at - t0 >= 30 * DAY) rt.status = 'NOT_ENGAGED';
  }
}

// ---------- Представления по схемам API ----------
const protocolsOf = (pid) => db.protocols.filter((p) => p.patientId === pid)
  .sort((a, b) => b.studyDate.localeCompare(a.studyDate) || b.receivedAt.localeCompare(a.receivedAt));
const ageOf = (birth) => {
  const b = new Date(birth), n = new Date(clock);
  return n.getFullYear() - b.getFullYear() - (n.getMonth() < b.getMonth() || (n.getMonth() === b.getMonth() && n.getDate() < b.getDate()) ? 1 : 0);
};
const lastNoteAt = (rid) => db.notifications.filter((n) => n.routeId === rid).map((n) => n.sentAt).sort().at(-1) ?? null;
const isOverdue = (rt) => {
  const st = current(rt);
  return OPEN.includes(rt.status) && !!st && st.dueDate < day() && !['BOOKED', 'COMPLETED'].includes(st.status);
};

function protocolShort(pr) {
  const { id, externalId, version, status, studyType, studyDate, conclusion, conclusionFound, receivedAt } = pr;
  const findingsCount = db.findings.filter((f) => f.protocolId === pr.id && ['SUGGESTED', 'CONFIRMED'].includes(f.status)).length;
  return { id, externalId, version, status, studyType, studyDate, conclusion, conclusionFound, findingsCount, receivedAt };
}

function patientShort(p) {
  const all = protocolsOf(p.id), last = all.find((x) => x.status !== 'ANNULLED') ?? all[0];
  const pending = db.findings.filter((f) => f.patientId === p.id && f.status === 'SUGGESTED').length;
  const { id, externalId, fullName, birthDate, sex, cardNumber } = p;
  const clean = (part) => part?.trim().replace(/\s+/gu, ' ') || null;
  const legacy = clean(fullName)?.split(' ') ?? [];
  const [lastName, firstName, middleName] = clean(p.lastName) || clean(p.firstName)
    ? [clean(p.lastName), clean(p.firstName), clean(p.middleName)]
    : [legacy[0] || null, legacy[1] || null, legacy.slice(2).join(' ') || null];
  const initial = (part) => part ? `${[...part][0]}.` : null;
  const shortName = [lastName, initial(firstName), initial(middleName)].filter(Boolean).join(' ');
  return {
    id, externalId, fullName: [lastName, firstName, middleName].filter(Boolean).join(' '),
    lastName, firstName, middleName, shortName, birthDate, sex, cardNumber, age: ageOf(birthDate),
    reviewState: last && (last.status === 'FAILED' || !last.conclusionFound) ? 'ATTENTION' : pending ? 'PENDING' : 'OK',
    needsRouteReview: all.some((pr) => pr.status === 'FAILED' || pr.status === 'DONE' && !pr.conclusionFound
      && !db.findings.some((f) => f.protocolId === pr.id && f.status === 'CONFIRMED')),
    receivedAt: all.map((x) => x.receivedAt).sort().at(-1), pendingFindings: pending,
    activeRoutes: db.routes.filter((r) => r.patientId === p.id && OPEN.includes(r.status)).length,
    lastStudyDate: last?.studyDate,
    ...topOf(p.id, last),
  };
}

function topOf(pid, cur) {
  const active = db.findings.filter((f) => f.patientId === pid && ['SUGGESTED', 'CONFIRMED'].includes(f.status) && (!f.protocolId || f.protocolId === cur?.id))
    .sort((a, b) => (RANK[b.level] ?? 0) - (RANK[a.level] ?? 0) || (a.targetDays ?? 1e9) - (b.targetDays ?? 1e9));
  return {
    studyType: cur?.studyType ?? null, maxLevel: active[0]?.level ?? null, activeFindings: active.length,
    topFindings: active.slice(0, 2).map(({ id, code, name, status, level, targetSpecialty, targetDays }) => ({ id, code, name, status, level, targetSpecialty, targetDays })),
  };
}

function patientCard(pid) {
  const p = byId(db.patients, pid, 'PATIENT');
  const all = protocolsOf(pid), cur = all.find((x) => x.status !== 'ANNULLED') ?? all[0];
  const fs = db.findings.filter((f) => f.patientId === pid);
  const rts = db.routes.filter((r) => r.patientId === pid);
  return {
    ...patientShort(p),
    currentProtocol: cur ? protocolShort(cur) : null,
    currentFindings: fs.filter((f) => f.protocolId === cur?.id || f.protocolId == null),
    routes: rts.filter((r) => OPEN.includes(r.status)),
    history: {
      protocols: all.filter((x) => x !== cur).map(protocolShort),
      findings: fs.filter((f) => f.protocolId && f.protocolId !== cur?.id),
      routes: rts.filter((r) => !OPEN.includes(r.status)),
    },
  };
}

function trackingItem(rt) {
  const st = current(rt), p = byId(db.patients, rt.patientId);
  return {
    routeId: rt.id, patientId: p.id, patientName: p.fullName,
    findingName: rt.findingIds.map((id) => finding(id)?.name).join(', '),
    routeStatus: rt.status, currentStepName: st?.name ?? null, currentStepStatus: st?.status ?? null,
    dueDate: st?.dueDate ?? null, overdue: isOverdue(rt), lastNotificationAt: lastNoteAt(rt.id),
  };
}

const page = (items, { page: n = 0, size = 20 } = {}) =>
  ({ items: items.slice(n * size, n * size + size), page: +n, size: +size, total: items.length });
const has = (s, q) => s?.toLowerCase().includes(q.trim().toLowerCase());

function review(f, patch, doctor = DOCTOR, at = clock) {
  Object.assign(f, patch, { reviewedBy: doctor, reviewedAt: iso(at) });
  return f;
}

// ---------- Эндпоинты (те же имена, что в httpApi) ----------
// Ответ — глубокая копия без служебных полей (начинаются с «_»), с имитацией сети
const reply = (fn) => new Promise((resolve, reject) => setTimeout(() => {
  try { resolve(JSON.parse(JSON.stringify(fn() ?? null, (k, v) => (k.startsWith('_') ? undefined : v)))); } catch (e) { reject(e); }
}, 150));

function patientOrder(q) {
  const value = (p) => ({ patient: p.fullName, finding: p.topFindings?.[0]?.name,
    due: p.topFindings?.[0]?.targetDays, receivedAt: p.receivedAt, studyDate: p.lastStudyDate })[q.sortBy];
  return (a, b) => {
    if (!q.sortBy || q.sortBy === 'default') return (RANK[b.maxLevel] ?? 0) - (RANK[a.maxLevel] ?? 0)
      || (b.receivedAt ?? '').localeCompare(a.receivedAt ?? '') || a.id.localeCompare(b.id);
    const x = value(a), y = value(b);
    if (x == null || y == null) return (x == null ? 1 : 0) - (y == null ? 1 : 0) || a.id.localeCompare(b.id);
    const cmp = typeof x === 'number' ? x - y : String(x).localeCompare(String(y), 'ru', { sensitivity: 'accent' });
    return cmp * (q.sortDirection === 'desc' ? -1 : 1) || a.id.localeCompare(b.id);
  };
}

export const mockApi = {
  patients: (q = {}) => reply(() => page(db.patients.map(patientShort).filter((p) =>
    (!q.search || has(p.fullName, q.search) || has(p.cardNumber, q.search) || has(p.externalId, q.search))
    && (!q.reviewState || p.reviewState === q.reviewState)
    && (q.needsRouteReview == null || p.needsRouteReview === q.needsRouteReview)
    && (!q.maxLevel || p.maxLevel === q.maxLevel)
    && (!q.studyType || db.protocols.some((x) => x.patientId === p.id && x.studyType === q.studyType))
    && (!q.dateFrom || p.lastStudyDate >= q.dateFrom) && (!q.dateTo || p.lastStudyDate <= q.dateTo))
    .sort(patientOrder(q)), q)),
  patient: (id) => reply(() => patientCard(id)),
  protocol: (id) => reply(() => {
    const pr = byId(db.protocols, id, 'PROTOCOL');
    const { patientId, text, modelVersion, error, notTriggered } = pr;
    return { ...protocolShort(pr), patientId, text, modelVersion, error, notTriggered, findings: db.findings.filter((f) => f.protocolId === id) };
  }),

  findings: (pid, status) => reply(() => db.findings.filter((f) => f.patientId === pid && (!status || f.status === status))),
  addFinding: (pid, { code, protocolId = null, attributes = {}, comment = null, doctor } = {}) => reply(() => {
    byId(db.patients, pid, 'PATIENT');
    const e = dict(code) ?? fail(400, 'UNKNOWN_CODE', 'Такого типа находки нет в словаре');
    const f = { id: nextId('fnd'), patientId: pid, protocolId, code, name: e.name, status: 'CONFIRMED', source: 'MANUAL',
      evidence: null, attributes, confidence: null, modelVersion: null, ruleVersion: DICT_VERSION, targetSpecialty: e.targetSpecialty,
      targetDays: e.targetDays, level: levelOf(e), flags: [],
      routeId: null, comment };
    db.findings.push(review(f, {}, doctor));
    return f;
  }),
  confirmFindings: (pid, { findingIds = [], doctor } = {}) => reply(() => db.findings
    .filter((f) => f.patientId === pid && findingIds.includes(f.id) && f.status === 'SUGGESTED')
    .map((f) => review(f, { status: 'CONFIRMED' }, doctor))),
  updateFinding: (id, { status, code, attributes, comment, doctor } = {}) => reply(() => {
    const f = byId(db.findings, id, 'FINDING');
    const e = code ? dict(code) ?? fail(400, 'UNKNOWN_CODE', 'Такого типа находки нет в словаре') : null;
    return review(f, { ...(status && { status }), ...(e && { code, name: e.name, targetSpecialty: e.targetSpecialty }),
      ...(attributes && { attributes }), ...(comment != null && { comment }) }, doctor);
  }),
  removeFinding: (id, reason) => reply(() => {
    const f = byId(db.findings, id, 'FINDING');
    Object.assign(f, { status: 'REMOVED', comment: reason ?? f.comment });
    if (f.routeId) cancel(byId(db.routes, f.routeId), 'FINDING_REMOVED');
  }),

  dictionary: ({ studyType, q } = {}) => reply(() => db.dictionary.filter((d) =>
    (!studyType || d.studyTypes.includes(studyType)) && (!q || [d.code, d.name, ...d.synonyms].some((s) => has(s, q))))),
  createDictionaryEntry: (body) => reply(() => {
    if (!body.code || !body.name || !body.targetSpecialty) fail(400, 'VALIDATION', 'Заполните код, название и специалиста');
    if (dict(body.code)) fail(400, 'DUPLICATE_CODE', `Код ${body.code} уже есть в словаре`);
    const e = { synonyms: [], studyTypes: [], conditions: {}, urgent: false, active: true, ...body };
    db.dictionary.push(e);
    return e;
  }),
  updateDictionaryEntry: (code, body) => reply(() => {
    const e = dict(code) ?? fail(404, 'DICTIONARY_NOT_FOUND', 'Тип находки не найден');
    return Object.assign(e, body, { code });
  }),

  routeTemplates: () => reply(() => db.templates),
  patientRoutes: (pid) => reply(() => db.routes.filter((r) => r.patientId === pid)),
  buildRoutes: (pid, body) => reply(() => buildRoutes(pid, body)),
  routes: (q = {}) => reply(() => page(db.routes.filter((rt) => {
    const st = current(rt), p = byId(db.patients, rt.patientId);
    return (!q.status || rt.status === q.status) && (!q.stepType || st?.type === q.stepType) && (!q.overdue || isOverdue(rt))
      && (!q.search || has(p.fullName, q.search) || has(p.cardNumber, q.search) || rt.findingIds.some((id) => has(finding(id)?.name, q.search)));
  }).map(trackingItem).sort((a, b) => b.overdue - a.overdue || (a.dueDate ?? '9').localeCompare(b.dueDate ?? '9')), q)),
  route: (id) => reply(() => byId(db.routes, id, 'ROUTE')),
  cancelRoute: (id, reason) => reply(() => { cancel(byId(db.routes, id, 'ROUTE'), reason || 'MANUAL'); }),
  updateStep: (rid, sid, body) => reply(() => updateStep(rid, sid, body)),

  notifications: (rid) => reply(() => db.notifications.filter((n) => n.routeId === rid).sort((a, b) => a.sentAt.localeCompare(b.sentAt))),
  notify: (rid, body) => reply(() => notify(rid, body)),
};

// ---------- Наполнение демо-данными: события в хронологическом порядке ----------
function runScenario(r, action, arg, at) {
  const pr = db.protocols.find((x) => x.externalId === r.protocol.externalId);
  const route = () => db.routes.filter((rt) => rt.findingIds.some((id) => finding(id)?.protocolId === pr.id)).at(-1);
  if (action === 'confirm') db.findings.filter((f) => f.protocolId === pr.id && f.status === 'SUGGESTED').forEach((f) => review(f, { status: 'CONFIRMED' }, DOCTOR, at));
  if (action === 'route') buildRoutes(pr.patientId, {}, at);
  if (action === 'notify') notify(route().id, { channel: arg }, at);
  if (action === 'step') updateStep(route().id, route().currentStepId, { status: arg }, at);
  if (action === 'finish') {
    const rt = route();
    rt.steps.filter((s) => !DONE.includes(s.status)).forEach((s) => Object.assign(s, { status: 'SKIPPED', completedAt: iso(at) }));
    advance(rt);
  }
}

[...samples, ...demoResults]
  .flatMap((r) => {
    const t0 = Date.parse(r.processedAt);
    return [[t0, () => ingest(r, t0)], ...(SCENARIOS[r.resultId] ?? []).map(([d, a, arg]) => [t0 + d * DAY, () => runScenario(r, a, arg, t0 + d * DAY)])];
  })
  .sort((a, b) => a[0] - b[0])
  .forEach(([, fn]) => fn());
tick();

// ---------- Управление демо-режимом (только мок) ----------
let queued = 0;
export const demo = {
  now: () => iso(),
  advance(hours) { clock += hours * H; tick(); },
  queueLeft: () => queue.length - queued,
  /** Имитирует поступление нового протокола из МИС через ML. Возвращает id пациента. */
  receiveNext: () => (queued < queue.length ? ingest(queue[queued++], clock) : null),
};
