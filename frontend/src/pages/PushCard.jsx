// «Отправка пушей из находок» (макеты Untitled.fig → pushes.fig): карточка пациента, где вместо протокола —
// маршруты (строка на маршрут, раскрывается: находки, история этапов, решение врача, открытые задачи),
// уведомления по всем маршрутам (кому, когда отправлено и прочитано, записался ли) и находки со статусом.
// Открывается по строке из «Находок»: #/push/<patientId>/<routeId>.
import { useMemo, useState } from 'react';
import { api, caps } from '../api';
import { LEVEL, STEP, fmtStamp, now, stepLabel } from '../lib/format';
import { go, useAsync, useSort } from '../lib/hooks';
import { Chevron, CloseLg } from '../components/Icons';
import { SearchBar, SortHead } from '../components/kit';
import { ErrorBox } from '../components/ui';
import NotifyDialog from '../components/NotifyDialog';
import { History, MoreDialog, ORGAN, PatientInfo } from './PatientCard';

const RANK = { EMERGENCY: 0, URGENT: 1, PLANNED: 2 };
const OPEN = ['ACTIVE', 'NOT_ENGAGED'];
const dmy = (v) => (v ? new Date(v).toLocaleDateString('ru-RU') : '');
const dm = (v) => (v ? `${new Date(v).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })} · ${new Date(v).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}` : '');
const TYPE = { SURGICAL_STANDARD: 'Хирургический', CONSULTATION: 'Наблюдение', ONCOLOGY_FAST: 'Онкологический', URGENT_ESCALATION: 'Экстренный' };

/** Что видит врач в колонке «Этап» и в раскрытой строке маршрута */
export function routeView(r, findings) {
  const cur = r.steps.find((s) => s.id === r.currentStepId);
  const consult = r.steps.find((s) => s.type === 'SPECIALIST_CONSULTATION');
  const spec = findings[r.findingIds[0]]?.targetSpecialty ?? (consult ? stepLabel(consult.name) : 'Маршрут');
  const stage = r.status === 'COMPLETED' ? 'Маршрут завершён' : r.status === 'CANCELLED' ? 'Маршрут отменён' : !cur ? '—'
    : cur.type === 'SPECIALIST_CONSULTATION' ? { PENDING: 'Ждёт записи', NOTIFIED: 'Уведомлён, ждёт записи', BOOKED: 'Записан на консультацию', NO_SHOW: 'Неявка на консультацию' }[cur.status] ?? STEP[cur.status]?.[0]
    : cur.type === 'HOSPITALIZATION_REFERRAL' ? 'Направлен на госпитализацию'
    : cur.type === 'HOSPITALIZATION' ? (cur.status === 'BOOKED' ? 'Госпитализация назначена' : 'Ждёт госпитализации')
    : cur.type === 'FOLLOW_UP' ? 'Ждёт контрольного визита' : cur.type === 'BIOPSY' ? 'Ждёт биопсии'
    : cur.type === 'ESCALATION' ? 'Экстренная эскалация' : stepLabel(cur.name);
  const visited = r.steps.filter((s) => s.completedAt).map((s) => s.completedAt).sort().at(-1) ?? null;
  const overdue = OPEN.includes(r.status) && cur && cur.dueDate < new Date(now()).toISOString().slice(0, 10) && !['BOOKED', 'COMPLETED'].includes(cur.status);
  // Решение врача — по тому, куда маршрут пошёл после консультации
  const next = consult?.status === 'COMPLETED' ? r.steps[r.steps.indexOf(consult) + 1] : null;
  const decision = consult?.status !== 'COMPLETED' ? 'Ждёт консультации'
    : !next ? 'Маршрут завершён' : next.type === 'HOSPITALIZATION_REFERRAL' ? 'Оперативное лечение показано'
    : next.type === 'BIOPSY' ? 'Показана биопсия' : next.type === 'FOLLOW_UP' ? 'Динамическое наблюдение' : stepLabel(next.name);
  const TASK = { SPECIALIST_CONSULTATION: ['Записать на консультацию', 'координатор'], HOSPITALIZATION_REFERRAL: ['Оформить направление на госпитализацию', 'врач'],
    HOSPITALIZATION: ['Назначить дату госпитализации', 'менеджер'], FOLLOW_UP: ['Записать на контрольный визит', 'координатор'],
    BIOPSY: ['Назначить биопсию', 'врач'], ESCALATION: ['Связаться с пациентом срочно', 'дежурный врач'] };
  const task = OPEN.includes(r.status) && cur && TASK[cur.type] ? `${TASK[cur.type][0]} — ${TASK[cur.type][1]}, до ${dmy(cur.dueDate).slice(0, 5)}` : 'Нет';
  return { cur, spec, type: TYPE[r.templateCode] ?? r.templateCode, stage, visited, overdue, decision, task };
}

export default function PushCard({ id, routeId }) {
  const card = useAsync(() => api.patient(id), [id]);
  const [dialog, setDialog] = useState(null);
  const c = card.data;
  const routes = useMemo(() => (c ? [...c.routes, ...c.history.routes] : []), [c]);
  const notes = useAsync(async () => (caps.notifications
    ? (await Promise.all(routes.map((r) => api.notifications(r.id).then((l) => l.map((n) => ({ ...n, routeId: n.routeId ?? r.id }))).catch(() => [])))).flat()
    : []), [routes]);

  if (card.error) return <ErrorBox error={card.error} onRetry={card.reload} />;
  if (!c) return <p className="state">Загружаем карточку пациента…</p>;

  const protocols = [c.currentProtocol, ...c.history.protocols].filter(Boolean);
  const allFindings = Object.fromEntries([...c.currentFindings, ...c.history.findings].map((f) => [f.id, f]));
  const findings = c.currentFindings.filter((f) => ['SUGGESTED', 'CONFIRMED'].includes(f.status));
  const protoById = Object.fromEntries(protocols.map((p) => [p.id, p]));
  const views = Object.fromEntries(routes.map((r) => [r.id, routeView(r, allFindings)]));
  // Кому можно написать: открытые маршруты без экстренной эскалации; выбранный в «Находках» — первым
  const targets = routes.filter((r) => OPEN.includes(r.status) && views[r.id].cur?.type !== 'ESCALATION')
    .sort((a, b) => (b.id === routeId) - (a.id === routeId))
    .map((r) => ({ routeId: r.id, specialist: views[r.id].spec, label: `${views[r.id].spec} · ${views[r.id].type}` }));
  const reload = () => { card.reload(); notes.reload(); };

  return (
    <>
      <SearchBar value="" onSearch={(q) => q && go(`findings?q=${encodeURIComponent(q)}`)} placeholder="Поиск" />
      <div className="pc-top">
        <button className="pc-close" aria-label="Закрыть карточку" title="Закрыть" onClick={() => (history.length > 1 ? history.back() : go('findings'))}>
          <CloseLg size={22} />
        </button>
      </div>

      <div className="pc-grid">
        <section className="pc-main push">
          <PatientInfo c={c} onMore={() => setDialog('more')} />

          <h2 className="pc-subtitle">Маршрут</h2>
          {routes.length ? <RoutesTable routes={routes} views={views} findings={allFindings} notes={notes.data ?? []} focus={routeId} />
            : <p className="pc-empty">{caps.routes ? 'Маршрут по пациенту ещё не составлен.' : 'Сервер пока не поддерживает маршруты.'}</p>}

          <h2 className="pc-subtitle">Уведомления</h2>
          <NotesTable notes={notes.data ?? []} routes={routes} views={views} loading={notes.loading} />
          <button className="btn-main push-send" disabled={!targets.length} onClick={() => setDialog('notify')}
            title={targets.length ? undefined : 'Нет открытого маршрута, по которому можно написать пациенту'}>Отправить уведомление</button>

          <h2 className="pc-subtitle">Находки</h2>
          <FindingsTable findings={findings} protoById={protoById} fallbackStudy={c.currentProtocol?.studyType} />
        </section>
        <span className="pc-vline" aria-hidden="true" />
        <History c={c} protocols={protocols} findings={allFindings} onOpenProtocol={() => go(`patients/${c.id}`)} />
      </div>

      {dialog === 'more' && <MoreDialog c={c} onClose={() => setDialog(null)} />}
      {dialog === 'notify' && <NotifyDialog targets={targets} onClose={() => setDialog(null)} onDone={reload} />}
    </>
  );
}

/** Маршруты: строка на маршрут, по стрелке раскрывается подробная карточка */
function RoutesTable({ routes, views, findings, notes, focus }) {
  const [open, setOpen] = useState(() => new Set(focus ? [focus] : []));
  const cols = [
    { key: 'spec', label: 'Специалист и тип', get: (r) => views[r.id].spec },
    { key: 'stage', label: 'Этап', get: (r) => views[r.id].stage },
    { key: 'due', label: 'Посетить до', get: (r) => views[r.id].cur?.dueDate ?? '9999' },
    { key: 'visit', label: 'Дата посещения', get: (r) => views[r.id].visited ?? '' },
    { key: 'more', label: '' },
  ];
  const { sorted, sort, toggle: onSort } = useSort(routes, cols, { key: 'due', dir: 1 });
  const toggle = (id) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  return (
    <div className="pt pt-routes">
      <SortHead className="pt-head" cols={cols} sort={sort} onSort={onSort} />
      {sorted.map((r) => {
        const v = views[r.id], isOpen = open.has(r.id);
        const history = [
          [r.createdAt, 'Маршрут создан'],
          ...notes.filter((n) => n.routeId === r.id).map((n) => [n.sentAt, 'Уведомлён']),
          ...r.steps.filter((s) => s.completedAt).map((s) => [s.completedAt, `${stepLabel(s.name)}: ${STEP[s.status][0].toLowerCase()}`]),
        ].sort((a, b) => String(a[0]).localeCompare(String(b[0])));
        return (
          <div key={r.id} className={`pt-route${isOpen ? ' open' : ''}${r.id === focus ? ' focus' : ''}`}>
            <button className="pt-row" aria-expanded={isOpen} onClick={() => toggle(r.id)}>
              <span><b>{v.spec}</b><small>{v.type}</small></span>
              <span>{v.stage}</span>
              <span className={v.overdue ? 'alarm' : ''}>{v.cur ? `до ${dmy(v.cur.dueDate)}` : '—'}</span>
              <span>{v.visited ? fmtStamp(v.visited) : '—'}</span>
              <Chevron size={12} className="pt-chev" />
            </button>
            {isOpen && (
              <div className="pt-more">
                <div><small>Находки маршрута</small>
                  <ul>{r.findingIds.map((fid) => findings[fid]).filter(Boolean).map((f) => <li key={f.id}>{f.name}</li>)}</ul></div>
                <div><small>История этапов</small>
                  <ul>{history.map(([at, what], i) => <li key={i}><time>{dm(at)}</time> {what}</li>)}</ul></div>
                <div><small>Решение врача</small><p>{v.decision}</p></div>
                <div><small>Открытые задачи</small><p>{v.task}</p></div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Уведомления по всем маршрутам пациента */
function NotesTable({ notes, routes, views, loading }) {
  const byRoute = Object.fromEntries(routes.map((r) => [r.id, r]));
  // «Запись»: после последнего уведомления по маршруту пациент записался на консультацию
  const lastByRoute = {};
  notes.forEach((n) => { if (!lastByRoute[n.routeId] || n.sentAt > lastByRoute[n.routeId].sentAt) lastByRoute[n.routeId] = n; });
  const booked = (n) => {
    const consult = byRoute[n.routeId]?.steps.find((s) => s.type === 'SPECIALIST_CONSULTATION');
    return ['BOOKED', 'COMPLETED'].includes(consult?.status) && lastByRoute[n.routeId]?.id === n.id;
  };
  const read = (n) => (n.readAt === undefined ? null : n.readAt && Date.parse(n.readAt) <= now() ? n.readAt : false);
  const cols = [
    { key: 'text', label: 'Сообщение', get: (n) => n.text },
    { key: 'route', label: 'Маршрут', get: (n) => views[n.routeId]?.spec ?? '' },
    { key: 'sent', label: 'Дата отправки', get: (n) => n.sentAt },
    { key: 'read', label: 'Прочитано', get: (n) => read(n) || '' },
    { key: 'booked', label: 'Запись', get: (n) => +booked(n) },
  ];
  const { sorted: rows, sort, toggle } = useSort(notes, cols, { key: 'sent', dir: -1 });
  return (
    <div className="pt pt-notes">
      <SortHead className="pt-head" cols={cols} sort={sort} onSort={toggle} />
      {rows.map((n) => {
        const r = read(n);
        return (
          <div key={n.id} className="pt-row">
            <span className="pt-msg" title={n.text}>{n.text}</span>
            <span>{views[n.routeId]?.spec ?? '—'}</span>
            <span>{fmtStamp(n.sentAt)}</span>
            <span>{r ? fmtStamp(r) : <em className="muted">{r === null ? '—' : 'Не прочитано'}</em>}</span>
            <span className="pt-booked">{booked(n)
              ? <svg className="pt-yes" width="24" height="24" viewBox="0 0 24 24" aria-label="Записался"><path d="M6 12.5l4 4 8-8" /></svg>
              : <svg className="pt-no" width="24" height="24" viewBox="0 0 24 24" aria-label="Не записался"><path d="M8 8l8 8M16 8l-8 8" /></svg>}</span>
          </div>
        );
      })}
      {!notes.length && <p className="pc-empty">{loading ? 'Загружаем…' : caps.notifications ? 'Уведомлений ещё не было.' : 'Сервер пока не отдаёт уведомления.'}</p>}
    </div>
  );
}

/** Таблица макета: заголовки со стрелками сортировки и серые строки 52 px */
function SortTable({ cols, rows, initial, rowKey, className, empty }) {
  const { sorted, sort, toggle } = useSort(rows, cols, initial);
  return (
    <div className={`pt ${className}`}>
      <SortHead className="pt-head" cols={cols} sort={sort} onSort={toggle} />
      {sorted.map((r) => <div key={rowKey(r)} className="pt-row">{cols.map((c) => <span key={c.key} className={`pt-${c.key}`}>{c.cell(r)}</span>)}</div>)}
      {!rows.length && <p className="pc-empty">{empty}</p>}
    </div>
  );
}

function FindingsTable({ findings, protoById, fallbackStudy }) {
  const organ = (f) => ORGAN[protoById[f.protocolId]?.studyType ?? fallbackStudy] ?? 'Не указан';
  const cols = [
    { key: 'organ', label: 'Орган', get: organ, cell: organ },
    { key: 'name', label: 'Находка', get: (f) => f.name, cell: (f) => f.name },
    { key: 'level', label: 'Статус', get: (f) => RANK[f.level] ?? 3, cell: (f) => <em className={f.level === 'EMERGENCY' ? 'alarm' : ''}>{f.level ? LEVEL[f.level][0] : '—'}</em> },
  ];
  return <SortTable className="pt-findings" cols={cols} rows={findings} initial={{ key: 'level', dir: 1 }} rowKey={(f) => f.id} empty="Активных находок нет." />;
}
