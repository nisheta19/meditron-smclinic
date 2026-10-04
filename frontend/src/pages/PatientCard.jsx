// Карточка пациента по макету Figma «Сеч_Хакатон_Вёрстка»: слева карточка (данные, протокол, находки, маршрут),
// справа «История приёмов». Данные — PatientCard и Protocol из openapi; поля, которых в API пока нет
// (контакты, СНИЛС, рост, вес и т. д.), показываются, если backend их пришлёт, иначе — «нет данных».
import { useMemo, useState } from 'react';
import { api, caps } from '../api';
import { CANCEL_REASON, NOT_TRIGGERED, REVIEW, ROUTE, STEP, STUDY, ATTR, attrValue, fmtDate, fmtDateTime, fmtStamp, now, stepLabel, flagLabel, targetDaysText } from '../lib/format';
import { go, useAction, useAsync, useToast } from '../lib/hooks';
import { CURRENT_DOCTOR } from '../config';
import { ArrowDown, ArrowLeft, CheckMark, Chevron, Close, Copy, FileIcon, Mail, Phone } from '../components/Icons';
import { SearchBar } from '../components/kit';
import { Dialog, ErrorBox, ReasonDialog } from '../components/ui';
import ProtocolText, { focusEvidence } from '../components/ProtocolText';
import AddFindingDialog from '../components/AddFindingDialog';
import NotifyDialog from '../components/NotifyDialog';
import Dropdown from '../components/Dropdown';

const ORGAN = {
  PELVIS_FEMALE: 'Органы малого таза', ABDOMEN: 'Брюшная полость', BREAST: 'Молочные железы',
  THYROID: 'Щитовидная железа', PROSTATE: 'Предстательная железа', LOWER_LIMB_VESSELS: 'Сосуды нижних конечностей',
  KIDNEY: 'Почки', SOFT_TISSUE: 'Мягкие ткани',
};
const longDate = (v) => (v ? new Date(v).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).replace(/\s?г\.$/, '') : '');
const stamp = fmtStamp;   // «13.07.2026 · 13:14»
const list = (v) => (Array.isArray(v) ? v.join(', ') : v);

export default function PatientCard({ id }) {
  const run = useAction();
  const card = useAsync(() => api.patient(id), [id]);
  const refs = useAsync(() => api.dictionary(), []);
  const [selected, setSelected] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);

  const c = card.data;
  const protocols = c ? [c.currentProtocol, ...c.history.protocols].filter(Boolean) : [];
  const protocolId = selected ?? c?.currentProtocol?.id;
  const proto = useAsync(() => (protocolId ? api.protocol(protocolId) : Promise.resolve(null)), [protocolId, card.data]);
  const names = useMemo(() => Object.fromEntries((refs.data ?? []).map((d) => [d.code, d.name])), [refs.data]);

  if (card.error) return <ErrorBox error={card.error} onRetry={card.reload} />;
  if (!c) return <p className="state">Загружаем карточку пациента…</p>;

  const p = proto.data?.id === protocolId ? proto.data : null;
  const isCurrent = protocolId === c.currentProtocol?.id;
  const findings = (isCurrent ? c.currentFindings : p?.findings ?? []).filter((f) => f.status !== 'REMOVED');
  const suggested = findings.filter((f) => f.status === 'SUGGESTED');
  const routable = c.currentFindings.filter((f) => f.status === 'CONFIRMED' && !f.routeId);
  const allFindings = Object.fromEntries([...c.currentFindings, ...c.history.findings].map((f) => [f.id, f]));
  const protoById = Object.fromEntries(protocols.map((x) => [x.id, x]));
  const superseded = p && protocols.some((other) => other.externalId === p.externalId && other.version > p.version);
  const editable = p?.status === 'DONE' && !superseded && !proto.error && !card.loading && !proto.loading && !busy;
  const act = async (fn, msg, rethrow) => {
    if (busy) return;
    setBusy(true);
    try { await run(fn, msg, rethrow); card.reload(); } finally { setBusy(false); }
  };

  return (
    <>
      <SearchBar value="" onSearch={(q) => q && go(`findings?q=${encodeURIComponent(q)}`)} placeholder="Поиск" stubFilters />
      <div className="pc-toolbar"><button className="pc-close" onClick={() => go('findings')} aria-label="Закрыть карточку" title="Вернуться к списку"><Close size={22} /></button></div>

      <div className="pc-grid">
        <section className="pc-main">
          <PatientInfo c={c} onMore={() => setDialog({ type: 'more' })} />

          <div className="pc-head">
            <h2>Протокол исследования</h2>
            {p && <span className="pc-chip">{stamp(p.receivedAt)}</span>}
          </div>
          <div className="pc-protocol">
            {proto.error ? <ErrorBox error={proto.error} onRetry={proto.reload} />
              : !protocolId ? <p className="muted">Протоколов пока нет.</p>
              : !p ? <p className="muted">Загружаем протокол…</p>
              : <>
                <ProtocolText text={p.text ?? p.conclusion} findings={findings.filter((f) => f.protocolId === p.id)}
                  notTriggered={[]} names={names} />
              </>}
          </div>

          <h2 className="pc-subtitle">Находки</h2>
          <FindingsTable findings={findings} protoById={protoById} fallbackStudy={p?.studyType} editable={editable}
            emptyText={!p || proto.error ? 'Результат пока недоступен.' : p.status === 'FAILED' ? 'Извлечь находки не удалось.' : p.status === 'ANNULLED' ? 'Протокол аннулирован.' : undefined}
            onConfirm={(f) => act(() => api.updateFinding(f.id, { status: 'CONFIRMED', doctor: CURRENT_DOCTOR }), 'Находка подтверждена')}
            onReject={(f) => setDialog({ type: 'reject', f })} onRemove={(f) => setDialog({ type: 'remove', f })} />
          <button className="pc-add" disabled={!editable} onClick={() => setDialog({ type: 'add' })}>+ Добавить</button>

          <h2 className="pc-subtitle pc-route-title">Маршрут</h2>
          {!caps.routes && <RoutePlaceholder findings={findings} needsReview={c.needsRouteReview} />}
          {c.routes.map((r) => (
            <RouteBlock key={r.id} route={r} findings={allFindings} onChanged={card.reload}
              onNotify={() => setDialog({ type: 'notify', r })} onCancel={() => setDialog({ type: 'cancel', r })} />
          ))}
          {!caps.routes
            ? null
            : routable.length > 0
            ? <button className="pc-add" onClick={() => act(() => api.buildRoutes(c.id), 'Маршрут составлен')}>+ Составить маршрут ({routable.length})</button>
            : <p className="pc-add disabled">{suggested.length ? 'Подтвердите находки, чтобы составить маршрут' : c.routes.length ? 'Все подтверждённые находки уже в маршруте' : 'Нет подтверждённых находок для маршрута'}</p>}
        </section>

        <History c={c} protocols={protocols} findings={allFindings} onOpenProtocol={(pid) => { setSelected(pid); window.scrollTo({ top: 0, behavior: 'smooth' }); }} />
      </div>

      {dialog?.type === 'more' && <MoreDialog c={c} protocol={p} names={names} onClose={() => setDialog(null)} />}
      {dialog?.type === 'add' && <AddFindingDialog studyType={p?.studyType} onClose={() => setDialog(null)}
        onSubmit={(body) => act(() => api.addFinding(c.id, { ...body, protocolId: p?.id, doctor: CURRENT_DOCTOR }), 'Находка добавлена', true)} />}
      {dialog?.type === 'reject' && <ReasonDialog title={`Отклонить: ${dialog.f.name}`} label="Комментарий врача" action="Отклонить" onClose={() => setDialog(null)}
        onSubmit={(comment) => act(() => api.updateFinding(dialog.f.id, { status: 'REJECTED', comment, doctor: CURRENT_DOCTOR }), 'Находка отклонена', true)} />}
      {dialog?.type === 'remove' && <ReasonDialog title={`Удалить: ${dialog.f.name}`} action="Удалить" danger onClose={() => setDialog(null)}
        label={dialog.f.routeId ? 'Причина (маршрут по находке будет отменён)' : 'Причина'}
        onSubmit={(reason) => act(() => api.removeFinding(dialog.f.id, reason || undefined), 'Находка удалена', true)} />}
      {dialog?.type === 'notify' && <NotifyDialog routeIds={[dialog.r.id]} onClose={() => setDialog(null)} onDone={card.reload} />}
      {dialog?.type === 'cancel' && <ReasonDialog title="Отменить маршрут" action="Отменить маршрут" danger onClose={() => setDialog(null)}
        onSubmit={(reason) => act(() => api.cancelRoute(dialog.r.id, reason || undefined), 'Маршрут отменён', true)} />}
    </>
  );
}

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

/* ---------- Данные пациента ---------- */
function PatientInfo({ c, onMore }) {
  const toast = useToast();
  const none = <span className="pc-none" title="Данные не переданы">—</span>;
  const val = (v, unit = '') => (v == null || v === '' || (Array.isArray(v) && !v.length) ? none : `${list(v)}${unit}`);
  const bmi = c.heightCm && c.weightKg ? (c.weightKg / (c.heightCm / 100) ** 2).toFixed(1).replace('.', ',') : null;
  const copy = async () => {
    try { if (!navigator.clipboard) throw new Error(); await navigator.clipboard.writeText(c.externalId); toast('ID скопирован'); }
    catch { toast('Не удалось скопировать', 'error'); }
  };
  const Stat = ({ label, children }) => <div className="pc-stat"><span>{label}</span><b>{children}</b></div>;
  const nameParts = [c.lastName, c.firstName, c.middleName].filter(Boolean);

  return (
    <div className="pc-info">
      <div className="pc-person">
        <h3>{(nameParts.length ? nameParts : [c.fullName || '—']).map((part, i) => <span key={i}>{part}{' '}</span>)}</h3>
        <ul className="pc-contacts">
          <li><Mail size={12} />{c.email ?? '—'}</li>
          <li><Phone size={12} />{c.phone ?? '—'}</li>
          <li><FileIcon size={12} />{c.snils ? `СНИЛС ${c.snils}` : c.cardNumber ? `Карта ${c.cardNumber}` : 'СНИЛС —'}</li>
        </ul>
        <button className="pc-id" onClick={copy} title="Скопировать ID пациента в МИС">id {c.externalId}<Copy size={10} /></button>
      </div>
      <span className="pc-divider" aria-hidden="true" />
      <div className="pc-stats">
        <div>
          <Stat label="Возраст">{c.age}</Stat>
          <Stat label="Дата рождения">{fmtDate(c.birthDate)}</Stat>
          <Stat label="Пол">{{ F: 'Женский', M: 'Мужской' }[c.sex] ?? 'Не указан'}</Stat>
        </div>
        <div>
          <Stat label="Рост">{val(c.heightCm, ' см')}</Stat>
          <Stat label="Вес">{val(c.weightKg, ' кг')}</Stat>
          <Stat label="ИМТ">{bmi ?? none}</Stat>
        </div>
        <div>
          <Stat label="Группа крови">{val(c.bloodType)}</Stat>
          <button className="pc-more" onClick={onMore}>Подробнее<ArrowLeft size={16} className="flip" /></button>
        </div>
      </div>
    </div>
  );
}

function MoreDialog({ c, protocol: p, names, onClose }) {
  const rows = [
    ['ФИО', c.fullName], ['Дата рождения', `${fmtDate(c.birthDate)}, ${c.age} лет`], ['Пол', c.sex === 'F' ? 'Женский' : 'Мужской'],
    ['Номер карты', c.cardNumber], ['ID в МИС', c.externalId], ['Статус проверки', REVIEW[c.reviewState]?.[0]],
    ['Последнее исследование', fmtDate(c.lastStudyDate)], ['Протокол поступил', fmtDateTime(c.receivedAt)],
    ['Ждут проверки', c.pendingFindings], ['Активные маршруты', c.activeRoutes],
    ['Хронические заболевания', list(c.chronicDiseases)], ['Препараты', list(c.medications)], ['Аллергии', list(c.allergies)],
  ].filter(([, v]) => v != null && v !== '' && (!Array.isArray(v) || v.length));
  return (
    <Dialog title="Данные пациента" onClose={onClose} actions={<button className="btn-main" onClick={onClose}>Закрыть</button>}>
      <dl className="pc-dl">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v ?? '—'}</dd></div>)}</dl>
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

/* ---------- Находки ---------- */
function FindingsTable({ findings, protoById, fallbackStudy, editable, emptyText, onConfirm, onReject, onRemove }) {
  const [sort, setSort] = useState({ key: 'organ', dir: 1 });
  const [open, setOpen] = useState(null);
  const organ = (f) => ORGAN[protoById[f.protocolId]?.studyType ?? fallbackStudy] ?? '—';
  const rows = [...findings].sort((a, b) => (sort.key === 'organ' ? organ(a).localeCompare(organ(b), 'ru') : a.name.localeCompare(b.name, 'ru')) * sort.dir);
  const head = (key, label) => (
    <button className={`col-head${sort.key === key ? ' active' : ''}`} onClick={() => setSort((s) => ({ key, dir: s.key === key ? -s.dir : 1 }))}>
      {label}<ArrowDown size={12} className={sort.key === key && sort.dir < 0 ? 'asc' : undefined} />
    </button>
  );
  if (!findings.length) return <p className="pc-empty">{emptyText ?? '—'}</p>;

  return (
    <div className="pc-table findings-table">
      <div className="pc-thead f-cols">{head('organ', 'Орган')}{head('name', 'Находка')}</div>
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

/* ---------- Маршрут ---------- */
function RoutePlaceholder({ findings, needsReview }) {
  const directions = [...new Set(findings.filter((f) => f.status !== 'REJECTED').map((f) => f.targetSpecialty).filter(Boolean))];
  return <div className="route-placeholder" aria-label="Маршрут — заглушка">
    <div className="pc-table">
      <div className="pc-thead route-placeholder-cols">
        {['№', 'Специалист', 'Дата посещения'].map((label) => <span key={label} className="col-head">{label}<ArrowDown size={12} /></span>)}
      </div>
      <div className="pc-row pc-step route-placeholder-cols">
        <span>1.</span>
        <button className="pc-pill stub-select" disabled title={needsReview ? 'Направление требует решения врача' : 'Заглушка записи; направление рассчитано по находкам'}><span>{needsReview ? 'Не определён' : directions[0] ?? 'Не выбран'}</span><Chevron size={20} /></button>
        <div className="pc-date"><span className="pc-do">до</span><button className="pc-pill stub-select" disabled title="Дата посещения не назначена"><span>Не назначена</span><Chevron size={20} /></button></div>
        <div className="pc-actions" aria-label="Действия маршрута — заглушки">
          <button className="stub-arrow" disabled aria-label="Переместить этап вверх"><ArrowDown size={16} className="up" /></button>
          <button className="stub-arrow" disabled aria-label="Переместить этап вниз"><ArrowDown size={16} /></button>
          <button className="sq ok" disabled aria-label="Подтвердить этап — заглушка"><CheckMark size={24} /></button>
          <button className="sq no" disabled aria-label="Удалить этап — заглушка"><Close size={24} /></button>
        </div>
      </div>
    </div>
    <button className="pc-add" disabled aria-label="Добавить этап" title="Добавление этапов — заглушка">+ Добавить</button>
  </div>;
}
const NEXT = { BOOKED: 'Записан', COMPLETED: 'Выполнен', NO_SHOW: 'Неявка', SKIPPED: 'Пропустить' };

function RouteBlock({ route: r, findings, onChanged, onNotify, onCancel }) {
  const run = useAction();
  const [sort, setSort] = useState({ key: 'n', dir: 1 });
  const [log, setLog] = useState(false);
  const cur = r.steps.find((s) => s.id === r.currentStepId);
  const urgent = cur?.type === 'ESCALATION';
  const today = new Date(now()).toISOString().slice(0, 10);
  const steps = r.steps.map((s, i) => ({ ...s, n: i + 1 }));
  const get = { n: (s) => s.n, name: (s) => s.name, date: (s) => s.dueDate };
  steps.sort((a, b) => String(get[sort.key](a)).localeCompare(String(get[sort.key](b)), 'ru', { numeric: true }) * sort.dir);
  const head = (key, label) => (
    <button className={`col-head${sort.key === key ? ' active' : ''}`} onClick={() => setSort((s) => ({ key, dir: s.key === key ? -s.dir : 1 }))}>
      {label}<ArrowDown size={12} className={sort.key === key && sort.dir > 0 ? undefined : 'asc'} />
    </button>
  );
  const setStep = (status) => run(() => api.updateStep(r.id, cur.id, { status }), 'Статус этапа обновлён').then(onChanged);

  return (
    <div className="pc-route">
      <div className="pc-route-head">
        <span><b>{r.findingIds.map((id) => findings[id]?.name ?? 'Находка').join(', ')}</b> · {ROUTE[r.status]?.[0]}</span>
        <span className="pc-route-actions">
          {!urgent && <button className="chip sm" onClick={onNotify}>Уведомить пациента</button>}
          <button className="chip sm" onClick={() => setLog((v) => !v)} aria-expanded={log}>Уведомления</button>
          <button className="link danger-link" onClick={onCancel}>Отменить</button>
        </span>
      </div>
      {urgent && <p className="callout red pc-note">Экстренная находка: пациенту сообщения не отправляются, задача передана дежурному врачу.</p>}
      {log && <NotificationLog routeId={r.id} />}
      <div className="pc-table">
        <div className="pc-thead r-cols">{head('n', '№')}{head('name', 'Специалист')}{head('date', 'Дата посещения')}</div>
        {steps.map((s) => {
          const isCur = s.id === r.currentStepId;
          const overdue = isCur && s.dueDate < today && !['BOOKED', 'COMPLETED'].includes(s.status);
          return (
            <div key={s.id} className={`pc-row r-cols pc-step ${s.status.toLowerCase()}${isCur ? ' current' : ''}`}>
              <span className="pc-n">{s.n}.</span>
              <span className="pc-pill" title={s.name}>{stepLabel(s.name)}</span>
              <span className="pc-date">
                <span className="pc-do">{s.completedAt ? '' : 'до'}</span>
                <span className={`pc-pill${overdue ? ' overdue' : ''}`}>{longDate(s.completedAt ?? s.dueDate)}</span>
              </span>
              <span className="pc-actions">
                {isCur && !urgent
                  ? <Dropdown compact ariaLabel="Статус этапа" value={s.status} onChange={(v) => v !== s.status && setStep(v)}
                      options={{ [s.status]: STEP[s.status][0], ...Object.fromEntries(Object.entries(NEXT).filter(([k]) => k !== s.status)) }} />
                  : <span className={`pc-status ${STEP[s.status][1]}`}>{STEP[s.status][0]}{overdue && ', просрочен'}</span>}
                {isCur && <>
                  <button className="sq ok" title="Этап выполнен" aria-label="Этап выполнен" onClick={() => setStep('COMPLETED')}><CheckMark size={24} /></button>
                  <button className="sq no" title="Пропустить этап" aria-label="Пропустить этап" onClick={() => setStep('SKIPPED')}><Close size={24} /></button>
                </>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function NotificationLog({ routeId }) {
  const { data, error } = useAsync(() => api.notifications(routeId), [routeId]);
  if (error) return <p className="error">Не удалось загрузить уведомления: {error.message}</p>;
  if (!data) return <p className="muted pc-note">Загружаем…</p>;
  if (!data.length) return <p className="muted pc-note">Уведомлений ещё не было.</p>;
  return (
    <ul className="pc-log">
      {[...data].reverse().map((n) => (
        <li key={n.id}><time>{fmtDateTime(n.sentAt)}</time><span>{n.text}<small>{n.sentBy === 'SYSTEM' ? 'автоматически' : n.sentBy}</small></span></li>
      ))}
    </ul>
  );
}

/* ---------- История приёмов ---------- */
const HISTORY_LIMIT = 10;

function History({ c, protocols, findings, onOpenProtocol }) {
  const [all, setAll] = useState(false);
  const routes = [...c.routes, ...c.history.routes];
  const events = [
    // Исследование → «Результат» (заключение протокола)
    ...protocols.map((p) => ({ key: p.id, at: p.receivedAt, title: 'Исследование', text: 'Результат',
      hint: STUDY[p.studyType], onClick: () => onOpenProtocol(p.id) })),
    // Приём специалиста → его название; неявка и пропуск — подписью
    ...routes.flatMap((r) => r.steps.filter((s) => s.completedAt || s.status === 'NO_SHOW').map((s) => ({
      key: s.id, at: s.completedAt ?? r.createdAt, title: stepLabel(s.name),
      text: s.status === 'COMPLETED' ? null : STEP[s.status][0], hint: findings[r.findingIds[0]]?.name }))),
    ...c.history.routes.filter((r) => r.status === 'CANCELLED').map((r) => ({
      key: `c-${r.id}`, at: r.createdAt, title: 'Маршрут отменён', text: CANCEL_REASON[r.cancelReason] ?? r.cancelReason })),
  ].sort((a, b) => String(b.at).localeCompare(String(a.at)));
  const shown = all ? events : events.slice(0, HISTORY_LIMIT);

  return (
    <aside className="pc-history">
      <h2>История приёмов</h2>
      {!events.length && <p className="muted">Приёмов пока не было.</p>}
      <div className="pc-events">
        {shown.map((e) => {
          const Tag = e.onClick ? 'button' : 'div';
          return (
            <Tag key={e.key} className="pc-event" data-event-id={e.key} onClick={e.onClick} title={e.hint}>
              <span className="pc-event-date">{stamp(e.at)}</span>
              <span className="pc-event-title">{e.title}</span>
              {e.text && <span className="pc-event-text">{e.text}</span>}
              <Chevron size={12} className="pc-event-arrow" />
            </Tag>
          );
        })}
      </div>
      {events.length > 0 && (
        <button className="pc-history-more" disabled={events.length <= HISTORY_LIMIT} onClick={() => setAll((v) => !v)} aria-expanded={all}>
          {all ? 'Свернуть' : 'Подробнее'}<Chevron size={20} className={all ? 'up' : undefined} />
        </button>
      )}
    </aside>
  );
}
