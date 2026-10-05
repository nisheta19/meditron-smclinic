import { useState } from 'react';
import { api } from '../api';
import { ATTR, attrValue, fmtDate, fmtDateTime, fmtStamp, REVIEW, NOT_TRIGGERED, flagLabel, targetDaysText } from '../lib/format';
import { useAction, useAsync } from '../lib/hooks';
import { CURRENT_DOCTOR } from '../config';
import { ArrowDown, CheckMark, Close } from './Icons';
import { Dialog, ErrorBox, ReasonDialog } from './ui';
import ProtocolText, { focusEvidence } from './ProtocolText';
import AddFindingDialog from './AddFindingDialog';
const list = v => Array.isArray(v) ? v.join(', ') : v;
const ORGAN = { PELVIS_FEMALE:'Органы малого таза', ABDOMEN:'Брюшная полость', BREAST:'Молочные железы', THYROID:'Щитовидная железа', PROSTATE:'Предстательная железа', LOWER_LIMB_VESSELS:'Сосуды нижних конечностей', KIDNEY:'Почки', SOFT_TISSUE:'Мягкие ткани' };

/** Clinical review is opened from a finding or a protocol in the new card. */
export default function ProtocolReview({ card, protocolId, routes = [], onChanged, onSave }) {
  const proto = useAsync(() => api.protocol(protocolId), [protocolId, card]);
  const refs = useAsync(() => api.dictionary(), []);
  const run = useAction();
  const [action, setAction] = useState(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const p = proto.data?.id === protocolId ? proto.data : null;
  const names = Object.fromEntries((refs.data ?? []).map(d => [d.code,d.name]));
  const protocols = [card.currentProtocol, ...(card.history?.protocols ?? [])].filter(Boolean);
  const superseded = p && protocols.some(other => other.externalId === p.externalId && other.version > p.version);
  const editable = p?.status === 'DONE' && !superseded && !proto.error && !proto.loading && !busy;
  const findings = (p?.findings ?? []).filter(f => f.status !== 'REMOVED');
  const act = async (fn, message) => {
    if (busy) return;
    setBusy(true);
    try { await run(fn, message, true); proto.reload(); onChanged(); }
    finally { setBusy(false); }
  };
  if (action?.type === 'add') return <AddFindingDialog studyType={p?.studyType} onClose={() => setAction(null)}
    onSubmit={body => act(() => api.addFinding(card.id, { ...body, protocolId, doctor: CURRENT_DOCTOR }), 'Находка добавлена')} />;
  if (action?.type === 'reject') return <ReasonDialog title={`Отклонить: ${action.f.name}`} label="Комментарий врача" action="Отклонить" onClose={() => setAction(null)}
    onSubmit={comment => act(() => api.updateFinding(action.f.id, { status:'REJECTED', comment, doctor:CURRENT_DOCTOR }), 'Находка отклонена')} />;
  if (action?.type === 'remove') return <ReasonDialog title={`Удалить: ${action.f.name}`} label="Причина" action="Удалить" danger onClose={() => setAction(null)}
    onSubmit={reason => act(() => api.removeFinding(action.f.id, reason || undefined), 'Находка удалена')} />;
  const save = async () => {
    if (!editable) return;
    setBusy(true); setSaveError(null);
    try {
      const pending = findings.filter(f => f.status === 'SUGGESTED').map(f => f.id);
      if (pending.length) await api.confirmFindings(card.id,{findingIds:pending,doctor:CURRENT_DOCTOR});
      proto.reload(); onChanged(); await onSave();
    } catch(e) { setSaveError(e.message); }
    finally { setBusy(false); }
  };
  return <div className="protocol-review">
    <div className="review-protocol-heading"><h2>Протокол исследования</h2>{p && <span className="review-date">{fmtStamp(p.receivedAt)}</span>}</div>
    {superseded && <p className="pc-empty">Протокол заменён новой версией. Доступен только просмотр.</p>}
    <div className="pc-protocol">{proto.error ? <ErrorBox error={proto.error} onRetry={proto.reload} /> : !p ? <p>Загружаем протокол…</p> :
      <ProtocolText text={p.text ?? p.conclusion} findings={findings} notTriggered={[]} names={names} />}</div>
    {p?.error && <p role="alert">{p.error.message} ({p.error.code})</p>}
    {p?.status === 'DONE' && !p.conclusionFound && <p>В протоколе не найдено заключение.</p>}
    {p?.flags?.length > 0 && <Flags flags={p.flags} />}
    <h2 className="review-findings-heading">Находки</h2>
    <FindingsTable findings={findings} protoById={Object.fromEntries(protocols.map(x => [x.id,x]))} fallbackStudy={p?.studyType} editable={editable}
      emptyText={!p || proto.error ? 'Результат пока недоступен.' : p.status === 'FAILED' ? 'Извлечь находки не удалось.' : p.status === 'ANNULLED' ? 'Протокол аннулирован.' : undefined}
      onConfirm={f => act(() => api.updateFinding(f.id, {status:'CONFIRMED', doctor:CURRENT_DOCTOR}), 'Находка подтверждена').catch(() => {})}
      onReject={f => setAction({type:'reject',f})} onRemove={f => setAction({type:'remove',f})} />
    <button className="pc-add" disabled={!editable} onClick={() => setAction({type:'add'})}>+ Добавить</button>
    {p?.notTriggered?.length > 0 && <details className="pc-nt"><summary>Почему не стало находкой ({p.notTriggered.length})</summary>
      <ul>{p.notTriggered.map((n,i) => <li key={i}><q>{n.evidence.text}</q><span>{n.name ?? names[n.code] ?? n.code}: {NOT_TRIGGERED[n.reason] ?? n.reason}</span></li>)}</ul></details>}
    <section className="review-routes"><h2>Маршрут</h2>
      <div className="review-route-head"><span>Специалист</span><span>Этап</span><span>Посетить до</span></div>
      {routes.map(r => <div className="review-route" key={r.id}>
        <div className="review-route-specialty"><ReadOnlyPill>{r.specialist}</ReadOnlyPill><ReadOnlyPill>{r.type}</ReadOnlyPill></div>
        <ReadOnlyPill>{r.stage}</ReadOnlyPill>
        <div className="review-route-date"><span>до</span><ReadOnlyPill>{r.due?.replace(/^до /,'') ?? '—'}</ReadOnlyPill></div>
        <span className="pc-actions"><button className="sq ok" disabled title="Маршрут формируется автоматически" aria-label="Подтвердить маршрут"><CheckMark size={24} /></button><button className="sq no" disabled title="Отмена маршрута недоступна" aria-label="Отклонить маршрут"><Close size={24} /></button></span>
      </div>)}
      {!routes.length && <p className="pc-empty">Маршрутов пока нет</p>}
      <button className="pc-add" disabled title="Маршруты создаются автоматически после проверки находок">+ Добавить</button>
    </section>
    {saveError && <p className="review-error" role="alert">{saveError}</p>}
    <button className="review-save" disabled={!editable || !findings.some(f => !['REJECTED','REMOVED'].includes(f.status))} onClick={save}>{busy ? 'Сохраняем…' : 'Сохранить и отправить уведомление'}</button>
  </div>;
}

function ReadOnlyPill({children}) {
  return <button className="review-pill" disabled title="Изменение маршрута вручную не поддерживается"><span>{children}</span><PillChevron /></button>;
}
function PillChevron() { return <svg width="12" height="8" viewBox="0 0 12 8" fill="none" aria-hidden="true"><path d="m1 1 5 5 5-5" stroke="currentColor" strokeWidth="1" /></svg>; }
/** Флаги качества (поле flags backend сверх контракта): расхождение, неполное описание, пересчёт TI-RADS и т. д. */
function Flags({ flags, className = '' }) {
  return (
    <ul className={`pc-flags ${className}`}>
      {flags.map((f) => (
        <li key={f.code}><b>{flagLabel(f)}</b>{f.note && <span>{f.note}</span>}<small>{f.setBy === 'BACKEND' ? 'правило сервера' : 'распознавание'}</small></li>
      ))}
    </ul>
  );
}

export function MoreDialog({ c, protocol: p, names, onClose }) {
  const rows = [
    ['ФИО', c.fullName], ['Дата рождения', [c.birthDate && fmtDate(c.birthDate), c.age != null && `${c.age} лет`].filter(Boolean).join(', ')], ['Пол', ({F:'Женский',M:'Мужской'})[c.sex]],
    ['Номер карты', c.cardNumber], ['ID в МИС', c.externalId], ['Статус проверки', REVIEW[c.reviewState]?.[0]],
    ['Последнее исследование', fmtDate(c.lastStudyDate)], ['Протокол поступил', fmtDateTime(c.receivedAt)],
    ['Ждут проверки', c.pendingFindings], ['Активные маршруты', c.activeRoutes],
    ['Хронические заболевания', list(c.chronicDiseases)], ['Препараты', list(c.medications)], ['Аллергии', list(c.allergies)],
  ].filter(([, v]) => v != null && v !== '' && (!Array.isArray(v) || v.length));
  return (
    <Dialog title="Данные пациента" onClose={onClose} actions={<button className="btn-main" onClick={onClose}>Закрыть</button>}>
      <dl className="pc-dl">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v ?? '—'}</dd></div>)}</dl>
      {c.banner && <p role="status">{c.banner}</p>}
      {p?.flags?.length > 0 && <Flags flags={p.flags} />}
      {p?.error && <p>{p.error.message} ({p.error.code})</p>}
      {p?.status === 'DONE' && !p.conclusionFound && <p>В протоколе не найдено заключение.</p>}
      {p && !p.text && p.conclusion && <p>Полный текст протокола не передан — показано заключение.</p>}
      {p?.notTriggered?.length > 0 && <details className="pc-nt">
        <summary>Почему не стало находкой ({p.notTriggered.length})</summary>
        <ul>{p.notTriggered.map((n, i) => <li key={i}><q>{n.evidence.text}</q><span>{n.name ?? names[n.code] ?? n.code}: {NOT_TRIGGERED[n.reason] ?? n.reason}</span></li>)}</ul>
      </details>}
    </Dialog>
  );
}

export function StandaloneFindingReview({ finding:f, onChanged, onClose }) {
  const run = useAction();
  const [remove,setRemove] = useState(false);
  if (remove) return <ReasonDialog title={`Удалить: ${f.name}`} label="Причина" action="Удалить" danger onClose={() => setRemove(false)}
    onSubmit={async reason => {await run(() => api.removeFinding(f.id,reason || undefined),'Находка удалена',true);onChanged();onClose();}} />;
  return <Dialog title={f.name} onClose={onClose} actions={<>
    {f.status === 'CONFIRMED' && <button className="btn danger" onClick={() => setRemove(true)}>Удалить находку</button>}
    <button className="btn primary" onClick={onClose}>Закрыть</button>
  </>}>
    <p>Находка добавлена отдельно от протокола.</p>
    <dl className="attrs">{Object.entries(f.attributes ?? {}).map(([k,v]) => <div key={k}><dt>{ATTR[k] ?? k}</dt><dd>{attrValue(k,v)}</dd></div>)}</dl>
    <p>Направить: {f.targetSpecialty ?? '—'}{f.targetDays != null && ` · ${targetDaysText(f.targetDays)}`}</p>
    {f.comment && <p>{f.comment}</p>}
  </Dialog>;
}

/* ---------- Находки ---------- */
function FindingsTable({ findings, protoById, fallbackStudy, editable, emptyText, onConfirm, onReject, onRemove }) {
  const [sort, setSort] = useState({ key: 'organ', dir: 1 });
  const [open, setOpen] = useState(null);
  const organ = (f) => ORGAN[protoById[f.protocolId]?.studyType ?? fallbackStudy] ?? '—';
  const levelName = f => f.status === 'REJECTED' ? 'Отклонена' : ({EMERGENCY:'Экстренно',URGENT:'Срочно',PLANNED:'Планово'})[f.level] ?? '—';
  const rows = [...findings].sort((a, b) => (sort.key === 'organ' ? organ(a).localeCompare(organ(b), 'ru') : sort.key === 'level' ? levelName(a).localeCompare(levelName(b),'ru') : a.name.localeCompare(b.name, 'ru')) * sort.dir);
  const head = (key, label) => (
    <button className={`col-head${sort.key === key ? ' active' : ''}`} onClick={() => setSort((s) => ({ key, dir: s.key === key ? -s.dir : 1 }))}>
      {label}<ArrowDown size={12} className={sort.key === key && sort.dir < 0 ? 'asc' : undefined} />
    </button>
  );
  if (!findings.length) return <p className="pc-empty">{emptyText ?? '—'}</p>;

  return (
    <div className="pc-table findings-table">
      <div className="pc-thead f-cols">{head('organ', 'Орган')}{head('name', 'Находка')}{head('level','Статус')}<span /></div>
      {rows.map((f) => {
        const isOpen = open === f.id;
        const attrs = Object.entries(f.attributes ?? {}).filter(([k]) => k !== 'level');
        return (
          <div key={f.id} data-finding-id={f.id} className={`pc-row ${f.status.toLowerCase()}${isOpen ? ' open' : ''}`}>
            <div className="f-cols pc-row-main" role="button" tabIndex={0} aria-expanded={isOpen}
              onClick={() => { setOpen(isOpen ? null : f.id); if (!isOpen && f.evidence?.text) focusEvidence(`ev-${f.id}`); }}
              onKeyDown={(e) => e.key === 'Enter' && e.target === e.currentTarget && e.currentTarget.click()}>
              <span>{organ(f)}</span>
              <span className="pc-fname">{f.name}</span>
              <span className="review-level"><button disabled title="Срочность рассчитывается по справочнику" className={`review-pill${f.level === 'EMERGENCY' && f.status !== 'REJECTED' ? ' npc-danger' : ''}`}><span>{levelName(f)}</span><PillChevron /></button></span>
              {editable && (
                <span className="pc-actions" onClick={(e) => e.stopPropagation()}>
                  {f.status === 'SUGGESTED' && <>
                    <button className="sq ok" aria-label={`Подтвердить: ${f.name}`} title="Подтвердить" onClick={() => onConfirm(f)}><CheckMark size={24} /></button>
                    <button className="sq no" aria-label={`Отклонить: ${f.name}`} title="Отклонить" onClick={() => onReject(f)}><Close size={24} /></button>
                  </>}
                  {f.status === 'CONFIRMED' && <>
                    <span className="sq ok static" title="Подтверждена"><CheckMark size={24} /></span>
                    <button className="sq no" aria-label={`Удалить: ${f.name}`} title="Удалить находку" onClick={() => onRemove(f)}><Close size={24} /></button>
                  </>}
                </span>
              )}
            </div>
            {isOpen && (
              <div className="pc-detail">
                {f.evidence?.text && <button className="quote" onClick={() => focusEvidence(`ev-${f.id}`)}>«{f.evidence.text}»</button>}
                {attrs.length > 0 && <dl className="attrs">{attrs.map(([k, v]) => <div key={k}><dt>{ATTR[k] ?? k}</dt><dd>{attrValue(k, v)}</dd></div>)}</dl>}
                <p className="meta">Направить: {f.targetSpecialty ?? '—'}{f.targetDays != null && ` · ${targetDaysText(f.targetDays)}`}</p>
                {(f.reviewedBy || f.comment) && <p className="meta">{f.reviewedBy && `${f.reviewedBy}, ${fmtDateTime(f.reviewedAt)}. `}{f.comment}</p>}
                {f.flags?.length > 0 && <Flags flags={f.flags} />}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

