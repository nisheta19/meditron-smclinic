// «Отправка пушей из находок» (макет Untitled.fig): та же карточка пациента, но вместо протокола —
// маршрут (кто и когда должен посетить), уведомления (отправлено / прочитано / записался) и находки со статусом.
// Открывается по строке из «Находок»: #/push/<patientId>/<routeId>.
import { useMemo, useState } from 'react';
import { api, caps } from '../api';
import { LEVEL, fmtStamp, now, nWord, stepLabel, DAYS } from '../lib/format';
import { go, useAsync } from '../lib/hooks';
import { ArrowDown, CloseLg } from '../components/Icons';
import { SearchBar } from '../components/kit';
import { ErrorBox } from '../components/ui';
import NotifyDialog from '../components/NotifyDialog';
import { History, MoreDialog, ORGAN, PatientInfo, longDate } from './PatientCard';

const RANK = { EMERGENCY: 0, URGENT: 1, PLANNED: 2 };
const longStamp = (v) => `${longDate(v)} · ${new Date(v).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`;

export default function PushCard({ id, routeId }) {
  const card = useAsync(() => api.patient(id), [id]);
  const [dialog, setDialog] = useState(null);
  const c = card.data;
  const routes = c ? [...c.routes, ...c.history.routes] : [];
  const route = routes.find((r) => r.id === routeId) ?? c?.routes[0] ?? null;
  const notes = useAsync(() => (route && caps.notifications ? api.notifications(route.id) : Promise.resolve([])), [route?.id, card.data]);

  if (card.error) return <ErrorBox error={card.error} onRetry={card.reload} />;
  if (!c) return <p className="state">Загружаем карточку пациента…</p>;

  const protocols = [c.currentProtocol, ...c.history.protocols].filter(Boolean);
  const allFindings = Object.fromEntries([...c.currentFindings, ...c.history.findings].map((f) => [f.id, f]));
  const findings = c.currentFindings.filter((f) => ['SUGGESTED', 'CONFIRMED'].includes(f.status));
  const protoById = Object.fromEntries(protocols.map((p) => [p.id, p]));
  const urgent = route?.steps.find((s) => s.id === route.currentStepId)?.type === 'ESCALATION';
  const canNotify = route && ['ACTIVE', 'NOT_ENGAGED'].includes(route.status) && !urgent;

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
          {route ? <RouteSteps route={route} /> : <p className="pc-empty">{caps.routes ? 'Маршрут по пациенту ещё не составлен.' : 'Сервер пока не поддерживает маршруты.'}</p>}

          <h2 className="pc-subtitle">Уведомления</h2>
          {route && <NotesTable notes={notes.data ?? []} route={route} loading={notes.loading} />}
          {urgent && <p className="callout red pc-note">Экстренная находка: пациенту сообщения не отправляются, задача передана дежурному врачу.</p>}
          <button className="btn-main push-send" disabled={!canNotify} onClick={() => setDialog('notify')}
            title={canNotify ? undefined : 'Нет активного маршрута для уведомления'}>Отправить уведомление</button>

          <h2 className="pc-subtitle">Находки</h2>
          <FindingsTable findings={findings} protoById={protoById} fallbackStudy={c.currentProtocol?.studyType} />
        </section>
        <span className="pc-vline" aria-hidden="true" />
        <History c={c} protocols={protocols} findings={allFindings} onOpenProtocol={() => go(`patients/${c.id}`)} />
      </div>

      {dialog === 'more' && <MoreDialog c={c} onClose={() => setDialog(null)} />}
      {dialog === 'notify' && <NotifyDialog routeIds={[route.id]} onClose={() => setDialog(null)} onDone={() => { card.reload(); notes.reload(); }} />}
    </>
  );
}

/** Таблица макета: заголовки со стрелками сортировки и серые строки 52 px */
function SortTable({ cols, rows, initial, rowKey, className, empty }) {
  const [sort, setSort] = useState(initial);
  const sorted = useMemo(() => {
    const col = cols.find((c) => c.key === sort.key);
    return [...rows].sort((a, b) => { const x = col.get(a), y = col.get(b); return (typeof x === 'string' ? x.localeCompare(y, 'ru') : x - y) * sort.dir; });
  }, [rows, cols, sort]);
  return (
    <div className={`pt ${className}`}>
      <div className="pt-head">
        {cols.map((c) => (
          <button key={c.key} className={`col-head${sort.key === c.key ? ' active' : ''}`} onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? -s.dir : 1 }))}>
            {c.label}<ArrowDown size={12} className={sort.key === c.key && sort.dir > 0 ? 'asc' : undefined} />
          </button>
        ))}
      </div>
      {sorted.map((r) => <div key={rowKey(r)} className="pt-row">{cols.map((c) => <span key={c.key} className={`pt-${c.key}`}>{c.cell(r)}</span>)}</div>)}
      {!rows.length && <p className="pc-empty">{empty}</p>}
    </div>
  );
}

function RouteSteps({ route }) {
  const today = new Date(now()).toISOString().slice(0, 10);
  const steps = route.steps.map((s, i) => ({ ...s, n: i + 1 }));
  const visit = (s) => {
    if (s.completedAt) return [longStamp(s.completedAt), ''];
    if (s.status === 'BOOKED') return ['Записан', 'muted'];
    if (s.status === 'NO_SHOW') return ['Неявка', 'alarm'];
    if (['SKIPPED', 'CANCELLED'].includes(s.status)) return ['Пропущен', 'muted'];
    const late = Math.round((Date.parse(today) - Date.parse(s.dueDate)) / 864e5);
    return late > 0 ? [`Просрочен на ${nWord(late, DAYS)}`, 'alarm'] : ['Ожидает', 'muted'];
  };
  const cols = [
    { key: 'n', label: '№', get: (s) => s.n, cell: (s) => `${s.n}.` },
    { key: 'spec', label: 'Специалист', get: (s) => stepLabel(s.name), cell: (s) => stepLabel(s.name) },
    { key: 'due', label: 'Должен посетить', get: (s) => s.dueDate, cell: (s) => <><i>до</i> {longDate(s.dueDate)}</> },
    { key: 'visit', label: 'Дата посещения', get: (s) => s.completedAt ?? s.dueDate, cell: (s) => { const [t, cls] = visit(s); return <em className={cls}>{t}</em>; } },
  ];
  return <SortTable className="pt-route" cols={cols} rows={steps} initial={{ key: 'n', dir: 1 }} rowKey={(s) => s.id} />;
}

function NotesTable({ notes, route, loading }) {
  const consult = route.steps.find((s) => s.type === 'SPECIALIST_CONSULTATION');
  const booked = ['BOOKED', 'COMPLETED'].includes(consult?.status);
  const lastId = [...notes].sort((a, b) => a.sentAt.localeCompare(b.sentAt)).at(-1)?.id;
  const read = (n) => (n.readAt === undefined ? null : n.readAt && Date.parse(n.readAt) <= now() ? n.readAt : false);
  const cols = [
    { key: 'text', label: 'Сообщение', get: (n) => n.text, cell: (n) => <span className="pt-msg" title={n.text}>{n.text}</span> },
    { key: 'sent', label: 'Дата отправки', get: (n) => n.sentAt, cell: (n) => fmtStamp(n.sentAt) },
    { key: 'read', label: 'Дата прочтения', get: (n) => read(n) || '', cell: (n) => { const r = read(n); return r ? longStamp(r) : <em className="muted">{r === null ? '—' : 'Не прочитано'}</em>; } },
    // «Запись»: после последнего уведомления пациент записался — галочка; иначе крестик
    { key: 'booked', label: 'Запись', get: (n) => +(booked && n.id === lastId), cell: (n) => (booked && n.id === lastId
      ? <svg className="pt-yes" width="24" height="24" viewBox="0 0 24 24" aria-label="Записался"><path d="M6 12.5l4 4 8-8" /></svg>
      : <svg className="pt-no" width="24" height="24" viewBox="0 0 24 24" aria-label="Не записался"><path d="M8 8l8 8M16 8l-8 8" /></svg>) },
  ];
  return <SortTable className="pt-notes" cols={cols} rows={notes} initial={{ key: 'sent', dir: 1 }} rowKey={(n) => n.id}
    empty={loading ? 'Загружаем…' : caps.notifications ? 'Уведомлений ещё не было.' : 'Сервер пока не отдаёт уведомления.'} />;
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
