import { useState } from 'react';
import { api, caps } from '../api';
import { LEVEL, STUDY } from '../lib/format';
import { useAction, useAsync, useSort } from '../lib/hooks';
import { Dialog, DialogActions, ErrorBox, Field, Select } from '../components/ui';
import { ChipRow, RowList, SearchBar, Stack } from '../components/kit';
import Dropdown from '../components/Dropdown';

const COND = { minSizeMm: 'размер от {} мм', minLevel: 'категория от {}', minStenosisPct: 'стеноз от {}%', minVolumeMl: 'объём от {} мл' };
const condText = (c = {}) => Object.entries(c).map(([k, v]) => (COND[k] ?? `${k}: {}`).replace('{}', v)).join(', ');

export default function Dictionary() {
  const [q, setQ] = useState('');
  const [chip, setChip] = useState('all');
  const [studyType, setStudyType] = useState('');
  const [edit, setEdit] = useState(null);
  const { data, error, loading, reload } = useAsync(() => api.dictionary({ studyType, q }), [studyType, q]);
  const templates = useAsync(() => api.routeTemplates(), []);
  const tpl = Object.fromEntries((templates.data ?? []).map((t) => [t.code, t.name]));
  const CHIPS = [['all', 'Все', () => true], ['urgent', 'Экстренные', (d) => d.urgent], ['off', 'Выключены', (d) => !d.active]];

  const cols = [
    { key: 'name', label: 'Тип находки', width: 'minmax(0, 226fr)', sort: (d) => d.name, cell: (d) => <Stack main={d.name} sub={d.code} faint={d.synonyms.slice(0, 2).join(', ')} /> },
    { key: 'study', label: 'Исследования', width: 'minmax(0, 213fr)', sort: (d) => d.studyTypes.join(), cell: (d) => <Stack main={d.studyTypes.map((s) => STUDY[s]).join(', ') || '—'} /> },
    { key: 'spec', label: 'Специалист', width: 'minmax(0, 199fr)', sort: (d) => d.targetSpecialty, cell: (d) => <Stack main={d.targetSpecialty} sub={tpl[d.routeTemplateCode] ?? d.routeTemplateCode} /> },
    { key: 'days', label: 'Срочность', width: 'minmax(0, 187fr)', sort: (d) => ['EMERGENCY', 'URGENT', 'PLANNED'].indexOf(d.level ?? (d.urgent ? 'EMERGENCY' : 'PLANNED')),
      cell: (d) => {
        const level = d.level ?? (d.urgent ? 'EMERGENCY' : 'PLANNED');   // level / maxLevel — поля backend сверх контракта
        return <Stack main={LEVEL[level][0]} warn={level === 'EMERGENCY'} sub={d.targetDays != null ? `${d.targetDays} дн. до консультации` : null}
          faint={d.maxLevel && d.maxLevel !== level ? `по правилам до: ${LEVEL[d.maxLevel][0].toLowerCase()}` : null} />;
      } },
    { key: 'cond', label: 'Порог', width: 'minmax(0, 132fr)', sort: (d) => condText(d.conditions), cell: (d) => <Stack main={condText(d.conditions) || 'Любая'} sub={d.active ? 'Активна' : 'Выключена'} /> },
  ];
  const fn = CHIPS.find(([k]) => k === chip)[2];
  const { sorted, sort, toggle } = useSort((data ?? []).filter(fn), cols.map((c) => ({ key: c.key, get: c.sort })), { key: 'name', dir: 1 });

  return (
    <>
      <SearchBar value={q} onSearch={setQ} placeholder="Поиск по названию, коду или синониму" filtersActive={studyType ? 1 : 0}
        filters={<Select label="Исследование" value={studyType} onChange={setStudyType} options={STUDY} />} />
      <ChipRow value={chip} onChange={setChip} items={CHIPS.map(([key, label, f]) => ({ key, label, count: (data ?? []).filter(f).length }))}
        extra={caps.dictionaryWrite && <button className="btn-main" onClick={() => setEdit({})}>Добавить тип находки</button>} />
      {error ? <ErrorBox error={error} onRetry={reload} /> : (
        <RowList cols={cols} rows={sorted} rowKey={(d) => d.code} sort={sort} onSort={toggle} onRow={caps.dictionaryWrite ? setEdit : undefined} loading={loading} empty="Ничего не найдено." />
      )}
      {edit && <EntryDialog entry={edit} templates={templates.data ?? []} onClose={() => setEdit(null)} onSaved={reload} />}
    </>
  );
}

function EntryDialog({ entry, templates, onClose, onSaved }) {
  const run = useAction();
  const isNew = !entry.code;
  const [e, setE] = useState({ code: '', name: '', targetSpecialty: '', routeTemplateCode: templates[0]?.code ?? '', targetDays: 14,
    studyTypes: [], urgent: false, active: true, ...entry, synonyms: (entry.synonyms ?? []).join(', '), conditions: JSON.stringify(entry.conditions ?? {}) });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setE((s) => ({ ...s, [k]: v }));
  const input = (k, label, props) => <Field label={label}><input value={e[k]} onChange={(ev) => set(k, ev.target.value)} {...props} /></Field>;
  let conditions = null;
  try { conditions = JSON.parse(e.conditions || '{}'); } catch { /* покажем ошибку ниже */ }
  const valid = e.code && e.name && e.targetSpecialty && conditions;

  const save = async () => {
    setBusy(true);
    const body = { ...e, code: e.code.trim().toUpperCase(), targetDays: +e.targetDays, conditions,
      synonyms: e.synonyms.split(',').map((s) => s.trim()).filter(Boolean) };
    try {
      await run(() => (isNew ? api.createDictionaryEntry(body) : api.updateDictionaryEntry(entry.code, body)), isNew ? 'Тип находки добавлен' : 'Изменения сохранены', true);
      onSaved(); onClose();
    } catch (err) {
      setBusy(false);
      if (err.notImplemented) { caps.dictionaryWrite = false; onSaved(); onClose(); }   // сервер словарь не меняет — прячем правку
    }
  };

  return (
    <Dialog title={isNew ? 'Новый тип находки' : e.name} wide onClose={onClose} actions={
      <DialogActions onCancel={onClose}>
        <button className="btn-main" disabled={!valid || busy} onClick={save}>{isNew ? 'Добавить' : 'Сохранить'}</button>
      </DialogActions>}>
      <div className="form-grid">
        {input('code', 'Код', { disabled: !isNew, placeholder: 'GALLBLADDER_POLYP' })}
        {input('name', 'Название', { placeholder: 'Полип желчного пузыря' })}
        {input('targetSpecialty', 'Специалист', { placeholder: 'Хирург' })}
        <Dropdown label="Шаблон маршрута" value={e.routeTemplateCode} onChange={(v) => set('routeTemplateCode', v)}
          options={templates.map((t) => [t.code, t.name])} />
        {input('targetDays', 'Срок до консультации, дн.', { type: 'number', min: 0 })}
        {input('synonyms', 'Синонимы через запятую')}
      </div>
      <Field as="div" label="Исследования">
        <div className="chips wrap">
          {Object.entries(STUDY).map(([k, l]) => (
            <label key={k} className="chip"><input type="checkbox" checked={e.studyTypes.includes(k)}
              onChange={() => set('studyTypes', e.studyTypes.includes(k) ? e.studyTypes.filter((s) => s !== k) : [...e.studyTypes, k])} />{l}</label>
          ))}
        </div>
      </Field>
      <Field label="Порог срабатывания (JSON): minSizeMm, minLevel, minStenosisPct…">
        <input className="mono" value={e.conditions} onChange={(ev) => set('conditions', ev.target.value)} placeholder='{"minSizeMm": 10}' aria-invalid={!conditions} />
      </Field>
      {!conditions && <p className="error">Порог должен быть корректным JSON-объектом.</p>}
      <div className="chips wrap">
        <label className="chip"><input type="checkbox" checked={e.urgent} onChange={(ev) => set('urgent', ev.target.checked)} />Экстренная: только эскалация персоналу</label>
        <label className="chip"><input type="checkbox" checked={e.active} onChange={(ev) => set('active', ev.target.checked)} />Активна</label>
      </div>
    </Dialog>
  );
}
