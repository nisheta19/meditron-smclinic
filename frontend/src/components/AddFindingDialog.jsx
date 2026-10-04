import { useState } from 'react';
import { api, USE_MOCK } from '../api';
import { ATTR } from '../lib/format';
import { useAsync } from '../lib/hooks';
import { fieldType, parseAttributes } from '../lib/findingFields';
import { Dialog, ErrorBox } from './ui';

export default function AddFindingDialog({ studyType, onSubmit, onClose }) {
  const [q, setQ] = useState('');
  const [code, setCode] = useState('');
  const [values, setValues] = useState({});
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const data = useAsync(() => api.dictionary({ studyType, full: !USE_MOCK }), [studyType]);
  const entries = (Array.isArray(data.data) ? data.data : data.data?.findings ?? []).filter((e) => e.active);
  const entry = entries.find((e) => e.code === code);
  const filtered = entries.filter((e) => `${e.name} ${e.code} ${JSON.stringify(e.synonyms)}`.toLowerCase().includes(q.toLowerCase()));
  let attributes = {}, error = null;
  try { if (entry) attributes = parseAttributes(entry, values); } catch (e) { error = e.message; }
  const set = (key, value) => setValues((v) => ({ ...v, [key]: value }));
  const submit = async () => {
    if (!entry || error || busy) return;
    setBusy(true);
    try { await onSubmit({ code, attributes, comment: comment.trim() || undefined }); onClose(); }
    catch { setBusy(false); }
  };
  return <Dialog title="Добавить находку" wide onClose={onClose} actions={<>
    <button className="btn ghost" onClick={onClose}>Отмена</button>
    <button className="btn primary" disabled={!entry || !!error || busy || data.loading} onClick={submit}>Добавить находку</button>
  </>}>
    <label className="field"><span>Поиск в словаре</span><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Название, код или синоним" autoFocus /></label>
    {data.error ? <ErrorBox error={data.error} onRetry={data.reload} /> : <div className="pick-list" role="listbox" aria-label="Тип находки">
      {filtered.map((e) => <button key={e.code} role="option" aria-selected={code === e.code} className="pick"
        onClick={() => { setCode(e.code); setValues({}); }}><b>{e.name}</b><small>{e.code}</small></button>)}
      {!filtered.length && <p className="muted">{data.loading ? 'Загружаем справочник…' : 'В словаре нет подходящих типов.'}</p>}
    </div>}
    {entry && <div className="form-grid">{(entry.attributes ?? []).map((key) => {
      const type = fieldType(entry, key);
      return <label className="field" key={key}><span>{ATTR[key] ?? key}</span>
        {type === 'boolean' || key === 'side'
          ? <select aria-label={ATTR[key] ?? key} value={values[key] ?? ''} onChange={(e) => set(key, e.target.value)}>
              <option value="">Не указано</option>
              {Object.entries(key === 'side' ? { left: 'Слева', right: 'Справа', both: 'С обеих сторон' } : { true: 'Да', false: 'Нет' })
                .map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            </select>
          : <input aria-label={ATTR[key] ?? key} type={type} min={type === 'number' ? 0 : undefined} step="any" value={values[key] ?? ''} onChange={(e) => set(key, e.target.value)} />}
      </label>;
    })}</div>}
    {error && <p className="error">{error}</p>}
    <label className="field"><span>Комментарий</span><textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} /></label>
  </Dialog>;
}
