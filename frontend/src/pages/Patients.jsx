import { useState } from 'react';
import { api } from '../api';
import { PAGE_SIZE } from '../config';
import { REVIEW, STUDY, ageText, fmtDate, fmtStamp, shortName, targetDaysText } from '../lib/format';
import { go, hashParam, useAsync, useSelection } from '../lib/hooks';
import { Checkbox, ChipRow, RowList, SearchBar, Stack } from '../components/kit';
import { DateField, ErrorBox, Select } from '../components/ui';

const BOOKING_STUB = 'Заглушка: сведения о записи пока не передаются';
const CHIPS = [
  { key: 'all', label: 'Все', query: {} },
  { key: 'new', label: 'Новые', query: { reviewState: 'PENDING' } },
  { key: 'overdue', label: 'Просрочена запись', disabled: true, title: BOOKING_STUB },
  { key: 'emergency', label: 'Экстренные', query: { maxLevel: 'EMERGENCY' } },
  { key: 'unbooked', label: 'Без записи', disabled: true, title: BOOKING_STUB },
  { key: 'attention', label: 'Требует внимания', query: { reviewState: 'ATTENTION' } },
  { key: 'ok', label: 'Проверено', query: { reviewState: 'OK' } },
];
const EMPTY = { studyType: '', reviewState: '', dateFrom: '', dateTo: '' };
const COLS = [
  { key: 'patient', label: 'Пациент', width: 'minmax(0, 226fr)',
    cell: (p) => <Stack main={<span title={p.fullName}>{/^Пациент(?:\s|$)/iu.test(p.fullName) ? p.fullName : shortName(p.fullName)}</span>}
      sub={ageText(p.age)}
      faint={fmtDate(p.birthDate)} /> },
  { key: 'finding', label: 'Находка', width: 'minmax(0, 213fr)',
    cell: (p) => <Stack main={p.topFindings?.[0]?.name ?? '—'}
      sub={STUDY[p.studyType] ?? p.studyType} faint={fmtStamp(p.receivedAt)} /> },
  { key: 'stage', label: 'Этап', width: 'minmax(0, 199fr)',
    cell: () => <div className="progress stage-stub" title="Заглушка: этап и прогресс не передаются">
      <span className="p-name">—</span>
      <span className="s-cap">—</span><span className="bar" aria-hidden="true" />
    </div> },
  { key: 'due', label: 'Срок записи', width: 'minmax(0, 187fr)',
    cell: (p) => <div title="Рекомендованный срок из справочника; дата записи пока не назначена">
      <Stack main={targetDaysText(p.topFindings?.[0]?.targetDays) ?? '—'} warn={p.maxLevel === 'EMERGENCY'} />
    </div> },
  { key: 'notified', label: 'Уведомлён', width: 'minmax(0, 132fr)',
    cell: () => <div title="Заглушка: сведения об уведомлениях пока не передаются"><Stack main="—" sub="—" /></div> },
];

export default function Patients({ preset }) {
  const chips = preset === 'inbox' ? CHIPS.filter((c) => ['new', 'attention'].includes(c.key))
    : preset === 'archive' ? CHIPS.filter((c) => !c.disabled) : CHIPS.slice(0, 5);
  const [search, setSearch] = useState(() => preset === 'findings' ? hashParam('q') : '');
  const [chip, setChip] = useState(preset === 'inbox' ? 'new' : 'all');
  const [filters, setFilters] = useState(EMPTY);
  const [filterReset, setFilterReset] = useState(0);
  const [page, setPage] = useState(0);
  const selection = useSelection();
  const query = { search, ...filters };
  const stateQuery = chips.find((c) => c.key === chip)?.query ?? {};
  const requestKey = JSON.stringify({ ...query, ...stateQuery, page });
  const list = useAsync(async () => {
    if (filters.dateFrom && filters.dateTo && filters.dateFrom > filters.dateTo) throw new Error('Дата начала должна быть не позже даты окончания');
    const [result, ...totals] = await Promise.all([
      api.patients({ ...query, ...stateQuery, page, size: PAGE_SIZE }),
      ...chips.map((c) => c.disabled ? Promise.resolve({ total: 0 }) : api.patients({ ...query, ...c.query, size: 1 })),
    ]);
    return { result, counts: Object.fromEntries(chips.map((c, i) => [c.key, totals[i].total])) };
  }, [requestKey], { refreshMs: 5000 });
  const change = (setter, value) => { setter(value); setPage(0); selection.clear(); };
  const setFilter = (key, value) => change(setFilters, { ...filters, [key]: value });
  const resetFilters = () => { change(setFilters, EMPTY); setFilterReset((v) => v + 1); };
  const result = list.data?.result;
  const pages = Math.max(1, Math.ceil((result?.total ?? 0) / PAGE_SIZE));
  const ids = (result?.items ?? []).map((p) => p.id);
  const all = ids.length > 0 && ids.every((id) => selection.sel.has(id));

  return <>
    <SearchBar value={search} onSearch={(v) => change(setSearch, v)} placeholder="Поиск" ariaLabel="Поиск по ФИО или ID в МИС"
      filtersActive={Object.values(filters).filter(Boolean).length} onReset={resetFilters}
      filters={<>
        <Select neutral label="Исследование" value={filters.studyType} onChange={(v) => setFilter('studyType', v)} options={STUDY} />
        <Select neutral label="Проверка находок" value={filters.reviewState} onChange={(v) => setFilter('reviewState', v)} options={REVIEW} />
        <DateField key={`from-${filterReset}`} label="Дата исследования с" value={filters.dateFrom} onChange={(value) => setFilter('dateFrom', value)} />
        <DateField key={`to-${filterReset}`} label="Дата исследования по" value={filters.dateTo} onChange={(value) => setFilter('dateTo', value)} />
      </>} />
    <ChipRow value={chip} onChange={(v) => change(setChip, v)} items={chips.map((c) => ({ ...c, count: list.data?.counts[c.key] ?? (c.disabled ? 0 : undefined) }))}
      selectAll={<Checkbox size="all" label="Выбрать всех на странице" checked={all} mixed={!all && ids.some((id) => selection.sel.has(id))} onChange={() => selection.setAll(ids, !all)} />} />
    {list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : <>
      <RowList className="patients-list" decorativeSort cols={COLS} rows={list.loading ? [] : result?.items ?? []} rowKey={(p) => p.id} selection={selection}
        onRow={(p) => go(`patients/${p.id}`)} loading={list.loading} empty="Пациентов не найдено." />
      {pages > 1 && <div className="pagination" aria-label="Страницы пациентов">
        <button className="chip" disabled={list.loading || page === 0} onClick={() => { setPage((v) => v - 1); selection.clear(); }}>Назад</button>
        <span>Страница {page + 1} из {pages} · Всего пациентов: {result?.total ?? '…'}</span>
        <button className="chip" disabled={list.loading || page + 1 >= pages} onClick={() => { setPage((v) => v + 1); selection.clear(); }}>Далее</button>
      </div>}
      {!list.loading && !result?.items.length && <button className="link" onClick={() => { setSearch(''); resetFilters(); setChip(chips[0].key); }}>Сбросить поиск и фильтры</button>}
    </>}
  </>;
}
