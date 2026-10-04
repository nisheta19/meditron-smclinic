import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { calendarDate, displayDate, monthCells, monthFor, parseDate, toISO } from '../lib/calendar';

const monthLabel = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric', timeZone: 'UTC' });

/** The text and calendar share focus; closing the popover never clears the draft. */
export default function DateField({ label, value, onChange }) {
  const [draft, setDraft] = useState(() => displayDate(value));
  const [month, setMonth] = useState(() => monthFor(value));
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const [focusDate, setFocusDate] = useState(null);
  const input = useRef(null), popup = useRef(null);
  const id = useId();
  const parsed = parseDate(draft);
  useEffect(() => { setDraft(displayDate(value)); if (value) setMonth(monthFor(value)); }, [value]);
  useLayoutEffect(() => {
    if (!open || !position || !focusDate) return;
    const target = focusDate === 'selected' ? popup.current.querySelector('[aria-pressed="true"]') || popup.current.querySelector('[data-date]')
      : popup.current.querySelector(`[data-date="${focusDate}"]`);
    target?.focus({ preventScroll: true }); setFocusDate(null);
  }, [open, position, focusDate, month]);

  useLayoutEffect(() => {
    if (!open) return;
    let frame, last = '';
    const follow = () => {
      if (input.current.closest('[inert]')) { setOpen(false); return; }
      const r = input.current.getBoundingClientRect();
      const key = `${r.left}|${r.top}|${r.bottom}|${innerWidth}|${innerHeight}`;
      if (key !== last) {
        last = key;
        const width = Math.min(280, innerWidth - 16);
        const below = innerHeight - r.bottom - 14, above = r.top - 14;
        const up = below < 300 && above > below;
        setPosition({ width, left: Math.max(8, Math.min(r.left, innerWidth - width - 8)),
          maxHeight: Math.max(80, up ? above : below),
          ...(up ? { bottom: innerHeight - r.top + 6 } : { top: r.bottom + 6 }) });
      }
      frame = requestAnimationFrame(follow);
    };
    const closeOutside = (event) => {
      if (!input.current.contains(event.target) && !popup.current?.contains(event.target)) setOpen(false);
    };
    follow();
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('focusin', closeOutside);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('focusin', closeOutside);
    };
  }, [open]);

  const edit = (event) => {
    const text = event.target.value;
    setDraft(text); setOpen(true);
    const date = parseDate(text);
    if (date) { onChange(date); setMonth(monthFor(date)); }
    else if (!text) onChange('');
  };
  const pick = (date) => {
    setDraft(displayDate(date)); onChange(date);
    input.current.focus({ preventScroll: true });
  };
  const escape = (event) => {
    if (event.key !== 'Escape') return;
    event.preventDefault(); event.stopPropagation();
    input.current.focus({ preventScroll: true }); setOpen(false);
  };
  const moveMonth = (delta) => setMonth((m) => calendarDate(m.getUTCFullYear(), m.getUTCMonth() + delta));
  const cells = monthCells(month);
  const focusDay = (event, date) => {
    const offset = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
    if (!offset) return;
    event.preventDefault();
    const next = calendarDate(Number(date.slice(0, 4)), Number(date.slice(5, 7)) - 1, Number(date.slice(-2)) + offset);
    if (next.getUTCFullYear() < 1 || next.getUTCFullYear() > 9999) return;
    const iso = toISO(next);
    setMonth(monthFor(iso)); setFocusDate(iso);
  };

  return <>
    <label className="field date-field"><span>{label}</span>
      <input ref={input} type="text" inputMode="numeric" placeholder="дд.мм.гггг" maxLength={10} autoComplete="off"
        value={draft} onChange={edit} onFocus={() => setOpen(true)} onClick={() => setOpen(true)}
        role="combobox" aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined}
        aria-invalid={draft.length === 10 && !parsed ? true : undefined}
        onKeyDown={(event) => {
          escape(event);
          if (['Enter', 'ArrowDown'].includes(event.key)) { event.preventDefault(); setOpen(true); }
          if (event.key === 'ArrowDown') setFocusDate('selected');
        }} />
    </label>
    {open && position && createPortal(
      <div ref={popup} id={id} role="dialog" aria-label={`Календарь: ${label}`} className="date-calendar" style={position} onKeyDown={escape}>
        <div className="date-calendar-head">
          <button type="button" aria-label="Предыдущий месяц" disabled={month.getUTCFullYear() === 1 && month.getUTCMonth() === 0} onClick={() => moveMonth(-1)}>‹</button>
          <span aria-live="polite">{monthLabel.format(month)}</span>
          <button type="button" aria-label="Следующий месяц" disabled={month.getUTCFullYear() === 9999 && month.getUTCMonth() === 11} onClick={() => moveMonth(1)}>›</button>
        </div>
        <div className="date-calendar-days">
          {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((day) => <span className="date-weekday" key={day}>{day}</span>)}
          {cells.map((date, i) => date ? <button key={date} type="button" data-date={date} aria-label={displayDate(date)}
            aria-pressed={date === parsed} onClick={() => pick(date)} onKeyDown={(event) => focusDay(event, date)}>{Number(date.slice(-2))}</button>
            : <span key={`empty-${i}`} />)}
        </div>
      </div>, document.body,
    )}
  </>;
}
