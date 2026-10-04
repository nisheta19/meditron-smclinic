// Выпадающий список вместо нативного <select>: тот же вид во всех браузерах, клавиатура, aria-listbox.
// Меню рендерится в body (portal) с position: fixed и следует за кнопкой — не обрезается в диалогах и панелях.
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Chevron } from './Icons';

/** options: { value: 'Подпись' } или [[value, 'Подпись']]; all — подпись пустого значения */
export default function Dropdown({ value, onChange, options, all, label, ariaLabel, compact, neutral = false }) {
  const items = [...(all != null ? [['', all]] : []), ...(Array.isArray(options) ? options : Object.entries(options))]
    .map(([v, l]) => [v, Array.isArray(l) ? l[0] : l]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [pos, setPos] = useState(null);
  const btn = useRef(null), list = useRef(null);
  const id = useId();
  const current = items.find(([v]) => v === value);

  const place = () => {
    const r = btn.current.getBoundingClientRect();
    const up = innerHeight - r.bottom < 260 && r.top > innerHeight - r.bottom;
    setPos({ left: r.left, width: Math.max(r.width, 200), ...(up ? { bottom: innerHeight - r.top + 6 } : { top: r.bottom + 6 }) });
  };
  const show = () => { if (!items.length) return; place(); setActive(Math.max(0, items.findIndex(([v]) => v === value))); setOpen(true); };
  const pick = (v) => { onChange(v); setOpen(false); btn.current.focus(); };

  useLayoutEffect(() => { if (open) list.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' }); }, [open, active]);
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (!btn.current?.contains(e.target) && !list.current?.contains(e.target)) setOpen(false); };
    // Меню следует за кнопкой (прокрутка, ресайз, анимация раскрытия панели фильтров), а не закрывается
    let raf, last = '';
    const follow = () => {
      const r = btn.current?.getBoundingClientRect();
      if (r) { const key = `${r.left}|${r.top}|${r.width}`; if (key !== last) { last = key; place(); } }
      raf = requestAnimationFrame(follow);
    };
    raf = requestAnimationFrame(follow);
    document.addEventListener('mousedown', close);
    return () => { cancelAnimationFrame(raf); document.removeEventListener('mousedown', close); };
  }, [open]);   // eslint-disable-line react-hooks/exhaustive-deps

  const onKey = (e) => {
    if (['ArrowDown', 'ArrowUp'].includes(e.key)) {
      e.preventDefault();
      if (!open) return show();
      setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length);
    } else if (open && e.key === 'Enter') { e.preventDefault(); if (items[active]) pick(items[active][0]); }
    else if (e.key === 'Escape' && open) { e.stopPropagation(); setOpen(false); }
    else if (e.key === 'Tab') setOpen(false);
  };

  const control = (
    <div className={`dd${compact ? ' compact' : ''}`}>
      <button ref={btn} type="button" className={`dd-btn${open ? ' open' : ''}`} aria-haspopup="listbox" aria-expanded={open}
        aria-controls={id} aria-label={ariaLabel} onClick={() => (open ? setOpen(false) : show())} onKeyDown={onKey}>
        <span className={current?.[0] === '' ? 'dd-all' : undefined}>{current?.[1] ?? 'Не выбрано'}</span>
        <Chevron size={12} />
      </button>
      {open && pos && createPortal(   // в body: анимации (transform) родителей не сдвигают fixed-меню
        <ul ref={list} id={id} role="listbox" className={`dd-list${neutral ? ' neutral' : ''}`} style={pos} aria-activedescendant={`${id}-${active}`}>
          {items.map(([v, l], i) => (
            <li key={v} id={`${id}-${i}`} role="option" aria-selected={v === value} data-active={i === active}
              onMouseEnter={() => setActive(i)} onMouseDown={(e) => e.preventDefault()} onClick={() => pick(v)}>
              <span>{l}</span>{v === value && <Check size={14} />}
            </li>
          ))}
        </ul>, document.body,
      )}
    </div>
  );
  return label ? <div className="field"><span>{label}</span>{control}</div> : control;
}
