import { useId, useState } from 'react';
import { ArrowDown, ArrowLeft, Copy, FileIcon, Mail, Phone, Search, Sliders } from './Icons';
import './patient-card.css';
import { sortRows } from './sortRows';

const dash = value => value == null || value === '' ? '—' : value;
const cx = (...parts) => parts.filter(Boolean).join(' ');

function Chevron({ down = false, className = '' }) {
  return <svg className={cx('npc-chevron', down && 'npc-chevron--down', className)} width="8" height="14" viewBox="0 0 8 14" fill="none" aria-hidden="true"><path d="M1 1L7 7L1 13" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export function PatientSearch({ onSearch, onFilters }) {
  const [value, setValue] = useState('');
  return <form className="npc-search" role="search" onSubmit={e => { e.preventDefault(); onSearch?.(value); }}>
    <input type="search" aria-label="Поиск" placeholder="Поиск" value={value} onChange={e => setValue(e.target.value)} />
    <button type="button" className="npc-search-filters" aria-label="Фильтры поиска" disabled={!onFilters} onClick={onFilters}><Sliders /></button>
    <button type="submit" className="npc-search-submit" disabled={!onSearch}><span>Найти</span><Search /></button>
  </form>;
}

export function PatientCardPage({ patient, onClose, onSearch, onFilters, ...props }) {
  return <div className="npc-page">
    <PatientSearch onSearch={onSearch} onFilters={onFilters} />
    <div className="npc-toolbar"><button className="npc-close" type="button" aria-label="Закрыть карточку" disabled={!onClose} onClick={onClose}><svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true"><path d="M5.5 5.5L16.5 16.5M16.5 5.5L5.5 16.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg></button></div>
    <PatientCardView patient={patient} {...props} />
  </div>;
}

function Stat({ label, value }) {
  return <div className="npc-stat"><dt>{label}</dt><dd>{dash(value)}</dd></div>;
}

function PatientInfo({ patient: p, onMore, onCopy }) {
  const [copyMessage, setCopyMessage] = useState('');
  const copy = async () => {
    try {
      if (onCopy) await onCopy(p.id);
      else await navigator.clipboard.writeText(String(p.id));
      setCopyMessage('ID скопирован');
    } catch { setCopyMessage('Не удалось скопировать ID'); }
  };
  return <header className="npc-info">
    <div className="npc-person">
      <h1>{(p.name?.length ? p.name : ['—']).map((part, i) => <span key={i}>{part}</span>)}</h1>
      <ul className="npc-contacts">
        <li><Mail /><span>{dash(p.email)}</span></li>
        <li><Phone /><span>{dash(p.phone)}</span></li>
        <li><FileIcon /><span>СНИЛС {dash(p.snils)}</span></li>
      </ul>
      <button type="button" className="npc-id" onClick={copy} disabled={!p.id} aria-label="Скопировать ID пациента"><span>id {dash(p.id)}</span><Copy /></button>
      <span role="status" className="npc-sr-only">{copyMessage}</span>
    </div>
    <div className="npc-stats">
      <dl><Stat label="Возраст" value={p.age} /><Stat label="Дата рождения" value={p.birthDate} /><Stat label="Пол" value={p.sex} /></dl>
      <dl><Stat label="Рост" value={p.height} /><Stat label="Вес" value={p.weight} /><Stat label="ИМТ" value={p.bmi} /></dl>
      <div><dl><Stat label="Группа крови" value={p.blood} /></dl><button type="button" className="npc-more" disabled={!onMore} onClick={onMore}><span>Подробнее</span><ArrowLeft className="npc-arrow-right" /></button></div>
    </div>
  </header>;
}

function useSort(rows) {
  const [sort, setSort] = useState(null);
  return {
    sort,
    sortBy: key => setSort(s => ({ key, direction: s?.key === key ? -s.direction : 1 })),
    rows: sortRows(rows, sort)
  };
}

function SortHead({ label, field, table, plain = false }) {
  if (plain) return <span className="npc-colhead"><span>{label}</span></span>;
  return <button type="button" className="npc-colhead" onClick={() => table.sortBy(field)} aria-label={`Сортировать: ${label}`}><span>{label}</span><ArrowDown className={table.sort?.key === field && table.sort.direction < 0 ? 'npc-arrow-up' : undefined} /></button>;
}

export function RouteDetails({ details, id }) {
  return <div className="npc-route-details" id={id}>
    <div className="npc-route-findings"><h3>Находки маршрута</h3><p>{details.findings?.length ? details.findings.map((s, i) => <span key={i}>{s}</span>) : '—'}</p></div>
    <div className="npc-route-stages"><h3>История этапов</h3><p>{details.stages?.length ? details.stages.map((s, i) => <span key={i}>{s}</span>) : '—'}</p></div>
    <div className="npc-route-conclusion"><h3>Находки маршрута</h3><p>{dash(details.conclusion)}</p></div>
    <div className="npc-route-task"><h3>Открытые задачи</h3><p>{dash(details.task)}</p></div>
  </div>;
}

function Routes({ rows, initialExpandedRouteId, onRouteOpen }) {
  const table = useSort(rows);
  const [expanded, setExpanded] = useState(initialExpandedRouteId ?? null);
  const prefix = useId();
  return <section className="npc-routes" aria-label="Маршрут">
    <h2>Маршрут</h2>
    <div className="npc-route-head npc-route-cols">
      <SortHead label="Специалист и тип" plain /><SortHead label="Этап" field="stage" table={table} /><SortHead label="Посетить до" field="due" table={table} /><SortHead label="Дата посещения" field="visit" table={table} />
    </div>
    <div className="npc-route-list">{table.rows.length ? table.rows.map(r => {
      const open = expanded === r.id;
      return <div key={r.id} className="npc-route-group">
        <button type="button" className="npc-route-row npc-route-cols" disabled={!r.details && !onRouteOpen} aria-label={`Маршрут: ${r.specialist}`} aria-expanded={r.details ? open : undefined} aria-controls={r.details ? `${prefix}-${r.id}` : undefined} onClick={() => r.details ? setExpanded(open ? null : r.id) : onRouteOpen?.(r)}>
          <span className="npc-route-specialist"><span>{dash(r.specialist)}</span><small>{dash(r.type)}</small></span>
          <span>{dash(r.stage)}</span><span className={r.overdue ? 'npc-danger' : undefined}>{dash(r.due)}</span><span>{dash(r.visit)}</span><Chevron down={open} />
        </button>
        {open && r.details && <RouteDetails details={r.details} id={`${prefix}-${r.id}`} />}
      </div>;
    }) : <p className="npc-empty">Маршрутов пока нет</p>}</div>
  </section>;
}

function Notifications({ rows, onNotify, state, onNotificationOpen }) {
  const table = useSort(rows);
  return <section className="npc-notifications" aria-label="Уведомления">
    <h2>Уведомления</h2>
    <div className="npc-notification-head npc-notification-cols">{[['Сообщение', 'message'], ['Маршрут', 'route'], ['Дата отправки', 'sent'], ['Прочитано', 'read'], ['Запись', 'booked']].map(([label, field]) => <SortHead key={field} label={label} field={field} table={table} />)}</div>
    <div className="npc-notification-list">{state ?? (table.rows.length ? table.rows.map(n => <div className="npc-notification-row npc-notification-cols" key={n.id}>
      <span><button className="npc-message" title={n.message} type="button" disabled={!onNotificationOpen} onClick={() => onNotificationOpen?.(n)}>{dash(n.message)}</button></span><span>{dash(n.route)}</span><span>{dash(n.sent)}</span><span>{dash(n.read)}</span><span className="npc-booked" aria-label={n.booked == null ? 'Данные о записи не переданы' : n.booked ? 'Записан' : 'Не записан'}>{n.booked ? <svg width="14" height="10" viewBox="0 0 14 10" fill="none" aria-hidden="true"><path d="M1 5L5 9L13 1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg> : '—'}</span>
    </div>) : <p className="npc-empty">Уведомлений пока нет</p>)}</div>
    <button type="button" className="npc-notify" disabled={!onNotify} onClick={onNotify}><span>Отправить уведомление</span></button>
  </section>;
}

function Findings({ rows, onFindingOpen }) {
  const table = useSort(rows);
  return <section className="npc-findings" aria-label="Находки">
    <h2>Находки</h2>
    <div className="npc-finding-head npc-finding-cols">{[['Орган', 'organ'], ['Находка', 'name'], ['Статус', 'status']].map(([label, field]) => <SortHead key={field} label={label} field={field} table={table} />)}</div>
    <div className="npc-finding-list">{table.rows.length ? table.rows.map(f => <button type="button" className="npc-finding-row npc-finding-cols" key={f.id} disabled={!onFindingOpen} onClick={() => onFindingOpen?.(f)}><span>{dash(f.organ)}</span><span>{dash(f.name)}</span><span className={f.urgent ? 'npc-danger' : undefined}>{dash(f.status)}</span></button>) : <p className="npc-empty">Находок пока нет</p>}</div>
  </section>;
}

function History({ rows, onHistoryOpen, onHistoryMore }) {
  return <aside className="npc-history" aria-label="История приёмов"><h2>История приёмов</h2>
    <div className="npc-events">{rows.length ? rows.map(event => <button key={event.id} type="button" className="npc-event" disabled={!onHistoryOpen} onClick={() => onHistoryOpen?.(event)}>
      <time>{dash(event.date)}</time><span className="npc-event-title">{dash(event.title)}</span>{event.subtitle && <span className="npc-event-subtitle">{event.subtitle}</span>}<Chevron />
    </button>) : <p className="npc-empty">История пока пуста</p>}</div>
    <button type="button" className="npc-history-more" disabled={!onHistoryMore} onClick={onHistoryMore}><span>Подробнее</span><Chevron down /></button>
  </aside>;
}

/** Data-only presentation component: does not fetch or mutate patient information. */
export default function PatientCardView({ patient, children, initialExpandedRouteId, onMore, onCopy, onRouteOpen, onNotify, onFindingOpen, onHistoryOpen, onHistoryMore, notificationsState, onNotificationOpen }) {
  if (!patient) return <p className="npc-empty">Данные пациента не переданы</p>;
  return <article className={`npc-card${children ? ' npc-review-sheet' : ''}`}>
    <div className="npc-main">
      <PatientInfo patient={patient} onMore={onMore} onCopy={onCopy} />
      {children || <><Routes rows={patient.routes ?? []} initialExpandedRouteId={initialExpandedRouteId} onRouteOpen={onRouteOpen} />
      <Notifications rows={patient.notifications ?? []} onNotify={onNotify} state={notificationsState} onNotificationOpen={onNotificationOpen} />
      <Findings rows={patient.findings ?? []} onFindingOpen={onFindingOpen} /></>}
    </div>
    <History rows={patient.history ?? []} onHistoryOpen={onHistoryOpen} onHistoryMore={onHistoryMore} />
  </article>;
}
