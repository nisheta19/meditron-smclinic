// «Входящие» (протоколы, ждущие врача) и «Картотека» (все пациенты) — один список с разными пресетами
import { useMemo, useState } from 'react';
import { api } from '../api';
import { REVIEW, STUDY, shortName, ageText, fmtDate, fmtStamp, nWord } from '../lib/format';
import { go, useAsync, useSort } from '../lib/hooks';
import { useCards } from '../lib/enrich';
import { ChipRow, RowList, SearchBar, Stack } from '../components/kit';
import { ErrorBox } from '../components/ui';
import PatientFilters from '../components/PatientFilters';
import { EMPTY_FILTERS, LEVEL_TO_URGENCY, activeCount, matchFilters, topUrgency } from '../lib/patientFilters';

const PRESETS = {
  // «Входящие» берёт сервер: needsRouteReview=true — случаи без определённого направления
  inbox: [['all', 'Все входящие', () => true], ['PENDING', 'Новые находки'], ['ATTENTION', 'Нужна проверка']],
  archive: [['all', 'Все', () => true], ['PENDING', 'Новые находки'], ['ATTENTION', 'Нужна проверка'], ['OK', 'Проверено']],
};
const REVIEW_TEXT = { PENDING: 'Ждут подтверждения врача', ATTENTION: 'Протокол не прочитан', OK: 'Проверено' };

const COLS = [
  { key: 'patient', label: 'Пациент', width: 'minmax(0, 226fr)', sort: (p) => p.fullName,
    cell: (p) => <Stack main={p.shortName ?? shortName(p.fullName)} sub={ageText(p.age)} faint={fmtDate(p.birthDate)} /> },
  { key: 'study', label: 'Исследование', width: 'minmax(0, 213fr)', sort: (p) => p.receivedAt,
    cell: (p) => <Stack main={STUDY[p.studyType ?? p.card?.currentProtocol?.studyType] ?? 'Исследование'} sub={p.cardNumber ?? `ID ${p.externalId}`} faint={fmtStamp(p.receivedAt)} /> },
  { key: 'findings', label: 'Находки', width: 'minmax(0, 199fr)', sort: (p) => p.pendingFindings,
    // topFindings / activeFindings / maxLevel — поля backend сверх контракта: самые срочные находки без догрузки карточки
    cell: (p) => (p.topFindings ? <Stack main={p.topFindings.map((f) => f.name).join(', ') || 'Нет активных'} warn={p.maxLevel === 'EMERGENCY'}
      sub={`${nWord(p.activeFindings, ['активная', 'активные', 'активных'])}${p.pendingFindings ? `, ждут проверки: ${p.pendingFindings}` : ''}`} /> : <Stack main={p.pendingFindings ? nWord(p.pendingFindings, ['ждёт проверки', 'ждут проверки', 'ждут проверки']) : 'Нет новых'}
      sub={p.card && nWord(p.card.currentFindings.filter((f) => f.status === 'CONFIRMED').length, ['подтверждена', 'подтверждены', 'подтверждено'])} />) },
  { key: 'routes', label: 'Маршруты', width: 'minmax(0, 187fr)', sort: (p) => p.activeRoutes,
    cell: (p) => <Stack main={p.activeRoutes ? nWord(p.activeRoutes, ['активный', 'активных', 'активных']) : 'Нет активных'} /> },
  { key: 'review', label: 'Проверка', width: 'minmax(0, 132fr)', sort: (p) => ['ATTENTION', 'PENDING', 'OK'].indexOf(p.reviewState),
    cell: (p) => <Stack main={REVIEW[p.reviewState][0]} sub={REVIEW_TEXT[p.reviewState]} />   /* красный — только для экстренных */ },
];

export default function Patients({ preset }) {
  const chips = PRESETS[preset];
  const [search, setSearch] = useState('');
  const [chip, setChip] = useState('all');
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const list = useAsync(() => api.patients({ search, size: 200 }), [search]);
  const dictionary = useAsync(() => api.dictionary(), []);
  const dict = useMemo(() => Object.fromEntries((dictionary.data ?? []).map((d) => [d.code, d])), [dictionary.data]);
  const cards = useCards((list.data?.items ?? []).map((p) => p.id));
  const rows = useMemo(() => (list.data?.items ?? []).map((p) => {
    const card = cards.data?.[p.id];
    // Патологии пациента — все находки, кроме отклонённых и удалённых
    const codes = [...new Set([...(card?.currentFindings ?? p.topFindings ?? []), ...(card?.history.findings ?? [])]
      .filter((x) => ['SUGGESTED', 'CONFIRMED'].includes(x.status)).map((x) => x.code))];
    return { ...p, card, codes, urgency: p.maxLevel !== undefined ? LEVEL_TO_URGENCY[p.maxLevel] ?? null : topUrgency(codes, dict) };
  }), [list.data, cards.data, dict]);
  const fn = (key) => chips.find(([k]) => k === key)?.[2] ?? ((p) => p.reviewState === key);
  const scoped = rows.filter((p) => fn('all')(p) && matchFilters(filters, p));
  const pathologies = [...new Set(rows.flatMap((p) => p.codes))].map((c) => [c, dict[c]?.name ?? c]).sort((a, b) => a[1].localeCompare(b[1], 'ru'));
  const { sorted, sort, toggle } = useSort(scoped.filter(fn(chip)), COLS.map((c) => ({ key: c.key, get: c.sort })), { key: 'study', dir: -1 });

  return (
    <>
      <SearchBar value={search} onSearch={setSearch} placeholder="Поиск по ФИО, номеру карты или ID в МИС"
        filtersActive={activeCount(filters)} onReset={() => setFilters(EMPTY_FILTERS)}
        filters={<PatientFilters value={filters} onChange={setFilters} pathologies={pathologies} />} />
      <ChipRow value={chip} onChange={setChip} items={chips.map(([key, label]) => ({ key, label, count: scoped.filter(fn(key)).length }))} />
      {list.error ? <ErrorBox error={list.error} onRetry={list.reload} /> : (
        <RowList cols={COLS} rows={sorted} rowKey={(p) => p.id} sort={sort} onSort={toggle} onRow={(p) => go(`patients/${p.id}`)}
          loading={list.loading} empty={preset === 'inbox' ? 'Входящих нет: все протоколы проверены.' : 'Пациенты не найдены.'} />
      )}
    </>
  );
}
