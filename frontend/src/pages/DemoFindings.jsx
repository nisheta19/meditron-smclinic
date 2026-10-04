// «Находки» — главный экран макета: все маршруты, где сейчас пациент и сколько осталось до срока
import { useMemo, useState } from 'react';
import { api, caps } from '../api';
import { ROUTE, STUDY, stepLabel, shortName, ageText, daysAgo, deadlineText, fmtDate, fmtStamp, notesText, now } from '../lib/format';
import { go, hashParam, useAsync, useSelection, useSort } from '../lib/hooks';
import { routeInfo, useCards, useNoteCounts } from '../lib/enrich';
import { ChipRow, Checkbox, Progress, RowList, SearchBar, Stack } from '../components/kit';
import { ErrorBox } from '../components/ui';
import PatientFilters from '../components/PatientFilters';
import { EMPTY_FILTERS, activeCount, matchFilters, urgencyOf } from '../lib/patientFilters';
import NotifyDialog from '../components/NotifyDialog';

const OPEN = ['ACTIVE', 'NOT_ENGAGED'];
const DAY = 864e5;

const CHIPS = [
  ['all', 'Все', () => true],
  ['new', 'Новые', (r) => r.isNew ?? (!r.lastNotificationAt && r.stepType !== 'ESCALATION')],
  ['overdue', 'Просрочена запись', (r) => r.overdue],
  ['urgent', 'Экстренные', (r) => r.stepType === 'ESCALATION'],
  ['unbooked', 'Без записи', (r) => r.stepType === 'SPECIALIST_CONSULTATION' && !['BOOKED', 'COMPLETED'].includes(r.currentStepStatus)],
];

const COLS = [
  { key: 'patient', label: 'Пациент', width: 'minmax(0, 226fr)', sort: (r) => r.patientName,
    cell: (r) => <Stack main={shortName(r.patientName)} sub={ageText(r.card?.age)} faint={r.card && fmtDate(r.card.birthDate)} /> },
  { key: 'finding', label: 'Находка', width: 'minmax(0, 213fr)', sort: (r) => r.findingName,
    cell: (r) => <Stack main={r.findingName} sub={r.protocol && STUDY[r.protocol.studyType]} faint={r.protocol && fmtStamp(r.protocol.receivedAt)} /> },
  { key: 'stage', label: 'Этап', width: 'minmax(0, 199fr)', sort: (r) => r.progress ?? -1,
    cell: (r) => (r.progress == null ? null : <Progress value={r.progress} name={r.currentStepName ? stepLabel(r.currentStepName) : ROUTE[r.routeStatus]?.[0]} />) },
  { key: 'due', label: 'Срок записи', width: 'minmax(0, 187fr)', sort: (r) => r.dueDate ?? '9999',
    cell: (r) => { const [text, tone] = deadlineText(r, r.stepType); return <Stack main={text} tone={tone} />; } },
  { key: 'notified', label: 'Уведомлён', width: 'minmax(0, 132fr)', sort: (r) => r.lastNotificationAt ?? '',
    cell: (r) => <Stack main={daysAgo(r.lastNotificationAt)} sub={r.notes != null && notesText(r.notes)} /> },
];

export default function Findings() {
  const [search, setSearch] = useState(() => hashParam('q'));  // поиск из шапки карточки пациента
  const [chip, setChip] = useState('all');
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [notifyIds, setNotifyIds] = useState(null);
  const sel = useSelection();

  // С маршрутами строка = маршрут (TrackingItem). Если backend маршрутов ещё не умеет — строка = находка пациента
  const byRoutes = caps.routes;
  const list = useAsync(() => (byRoutes ? api.routes({ size: 500 }) : api.patients({ size: 500 })), [byRoutes]);
  const dictionary = useAsync(() => api.dictionary(), []);
  const dict = useMemo(() => Object.fromEntries((dictionary.data ?? []).map((d) => [d.code, d])), [dictionary.data]);
  const items = list.data?.items ?? [];
  const cards = useCards(items.map((r) => (byRoutes ? r.patientId : r.id)));
  const notes = useNoteCounts(byRoutes ? items.map((r) => r.routeId) : []);

  // Строка = TrackingItem + данные из карточки пациента
  const rows = useMemo(() => (!byRoutes ? findingRows(items, cards.data, dict) : items.map((r) => {
    const card = cards.data?.[r.patientId];
    const info = routeInfo(card, r.routeId);
    const code = info?.finding?.code;
    return { ...r, card, protocol: info?.protocol, progress: info?.progress, stepType: info?.step?.type, notes: notes.data?.[r.routeId],
      sex: card?.sex, age: card?.age, codes: code ? [code] : [], urgency: urgencyOf(info?.finding?.level ? info.finding : dict[code]) };
  })), [byRoutes, items, cards.data, notes.data, dict]);

  const open = rows.filter((r) => OPEN.includes(r.routeStatus));
  const pathologies = [...new Map(open.flatMap((r) => r.codes.map((c) => [c, dict[c]?.name ?? r.findingName]))).entries()]
    .sort((a, b) => a[1].localeCompare(b[1], 'ru'));
  const scoped = open.filter((r) => matchFilters(filters, r)
    && (!search || `${r.patientName} ${r.findingName} ${r.card?.cardNumber ?? ''}`.toLowerCase().includes(search.toLowerCase())));
  const chipFn = CHIPS.find(([k]) => k === chip)[2];
  const visible = scoped.filter(chipFn);
  const { sorted, sort, toggle } = useSort(visible, COLS.map((c) => ({ key: c.key, get: c.sort })), { key: 'due', dir: 1 });

  const ids = sorted.map((r) => r.routeId);
  const all = ids.length > 0 && ids.every((id) => sel.sel.has(id));
  const recent = [...sel.sel].filter((id) => { const r = rows.find((x) => x.routeId === id); return r?.lastNotificationAt && now() - Date.parse(r.lastNotificationAt) < DAY; }).length;

  return (
    <>
      <SearchBar value={search} onSearch={setSearch} placeholder="Поиск по ФИО, карте или находке"
        filtersActive={activeCount(filters)} onReset={() => setFilters(EMPTY_FILTERS)}
        filters={<PatientFilters value={filters} onChange={setFilters} pathologies={pathologies} />} />
      <ChipRow value={chip} onChange={setChip}
        items={CHIPS.map(([key, label, fn]) => ({ key, label, count: scoped.filter(fn).length }))}
        selectAll={caps.notifications && <Checkbox size="all" checked={all} mixed={!all && ids.some((id) => sel.sel.has(id))} label="Выбрать всех"
          onChange={() => sel.setAll(ids, !all)} />} />
      {!byRoutes && <p className="mode-note">Сервер пока не поддерживает маршруты: показаны находки пациентов. Срок записи считается от поступления протокола по сроку из словаря.</p>}
      {list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : (
        <RowList cols={COLS} rows={sorted} rowKey={(r) => r.routeId} sort={sort} onSort={toggle} selection={caps.notifications ? sel : null}
          onRow={(r) => go(`patients/${r.patientId}`)} loading={list.loading || cards.loading}
          empty={byRoutes ? 'Под выбранные условия маршрутов нет.' : 'Под выбранные условия находок нет.'} />
      )}

      {sel.sel.size > 0 && (
        <div className="bulkbar" role="region" aria-label="Действия с выбранными">
          <span>Выбрано: <b>{sel.sel.size}</b></span>
          <button className="chip" onClick={sel.clear}>Снять выделение</button>
          <button className="btn-main" onClick={() => setNotifyIds([...sel.sel])}>Отправить уведомление</button>
        </div>
      )}
      {notifyIds && <NotifyDialog routeIds={notifyIds} recent={recent} onClose={() => setNotifyIds(null)}
        onDone={() => { sel.clear(); list.reload(); }} />}
    </>
  );
}

/** Строки «Находок» без маршрутов: каждая подтверждённая или предложенная находка из карточки пациента */
function findingRows(patients, cards, dict) {
  const today = new Date(now()).toISOString().slice(0, 10);
  return patients.flatMap((p) => {
    const card = cards?.[p.id];
    if (!card) return [];
    const proto = card.currentProtocol;
    return card.currentFindings.filter((f) => ['SUGGESTED', 'CONFIRMED'].includes(f.status)).map((f) => {
      const entry = dict[f.code] ?? {};
      const days = f.targetDays ?? entry.targetDays;
      const urgent = f.level ? f.level === 'EMERGENCY' : f.urgent ?? entry.urgent;   // level — поле backend сверх контракта
      const from = proto?.receivedAt ?? proto?.studyDate;
      const dueDate = from && days != null ? new Date(Date.parse(from) + days * DAY).toISOString().slice(0, 10) : null;
      return {
        routeId: f.id, patientId: p.id, patientName: p.fullName, findingName: f.name ?? entry.name ?? f.code, card, protocol: proto,
        progress: 0, currentStepName: f.status === 'SUGGESTED' ? 'Проверка врачом' : 'Маршрут не составлен',
        stepType: urgent ? 'ESCALATION' : 'SPECIALIST_CONSULTATION', currentStepStatus: 'PENDING', routeStatus: 'ACTIVE',
        dueDate, overdue: !!dueDate && dueDate < today, lastNotificationAt: null, notes: null, isNew: f.status === 'SUGGESTED',
        sex: p.sex, age: p.age, codes: [f.code], urgency: urgencyOf(f.level ? f : { urgent, targetDays: days }),
      };
    });
  });
}
