import { useState } from 'react';
import { api } from '../api';
import { STUDY } from '../lib/format';
import { useAsync } from '../lib/hooks';
import { Dialog, DialogActions, Field, TextArea } from './ui';
import Dropdown from './Dropdown';

/** Врач добавляет находку вручную: тип из словаря + атрибуты */
export default function AddFindingDialog({ studyType, onSubmit, onClose }) {
  const [onlyStudy, setOnlyStudy] = useState(!!studyType);
  const [q, setQ] = useState('');
  const [code, setCode] = useState('');
  const [attrs, setAttrs] = useState({ sizeMm: '', side: '', category: '' });
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const { data: entries = [] } = useAsync(() => api.dictionary({ studyType: onlyStudy ? studyType : undefined, q }), [onlyStudy, q]);

  const submit = async () => {
    setBusy(true);
    const attributes = Object.fromEntries(Object.entries(attrs).filter(([, v]) => v !== '').map(([k, v]) => [k, k === 'sizeMm' ? +v : v]));
    try { await onSubmit({ code, attributes, comment: comment.trim() || undefined }); onClose(); } catch { setBusy(false); }
  };
  const set = (k) => (e) => setAttrs((a) => ({ ...a, [k]: e.target.value }));

  return (
    <Dialog title="Добавить находку" wide onClose={onClose} actions={
      <DialogActions onCancel={onClose}>
        <button className="btn-main" disabled={!code || busy} onClick={submit}>Добавить находку</button>
      </DialogActions>}>
      <div className="row">
        <Field label="Поиск в словаре" grow><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Название или синоним" autoFocus /></Field>
        {studyType && <label className="check-label"><input type="checkbox" checked={onlyStudy} onChange={(e) => setOnlyStudy(e.target.checked)} />Только {STUDY[studyType]}</label>}
      </div>
      <div className="pick-list" role="listbox" aria-label="Тип находки">
        {(entries ?? []).filter((e) => e.active).map((e) => (
          <button key={e.code} role="option" aria-selected={code === e.code} className="pick" onClick={() => setCode(e.code)}>
            <b>{e.name}</b><small>{e.targetSpecialty}{e.urgent ? ', экстренная' : ''}</small>
          </button>
        ))}
        {entries && !entries.length && <p className="muted">В словаре нет подходящих типов.</p>}
      </div>
      <div className="row">
        <Field label="Размер, мм"><input type="number" min="0" step="0.1" value={attrs.sizeMm} onChange={set('sizeMm')} /></Field>
        <Dropdown label="Сторона" value={attrs.side} onChange={(v) => setAttrs((a) => ({ ...a, side: v }))}
          all="Не указана" options={{ left: 'Слева', right: 'Справа', both: 'С обеих сторон' }} />
        <Field label="Категория" grow><input value={attrs.category} onChange={set('category')} placeholder="Например, BI-RADS 4" /></Field>
      </div>
      <Field label="Комментарий"><TextArea value={comment} onChange={setComment} /></Field>
    </Dialog>
  );
}
