import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

/** Confirmed findings have the same actions in protocol and standalone review. */
export default function FindingMenu({ name, onEdit, onRemove }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const trigger = useRef(null), menu = useRef(null);
  const id = useId();
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const button = trigger.current;
      const r = button.getBoundingClientRect();
      const scale = r.width / button.offsetWidth;
      const width = Math.min(164 * scale, innerWidth - 16);
      const height = 68 * scale;
      setPosition({ width, left: Math.max(8, Math.min(r.right - width, innerWidth - width - 8)),
        top: Math.max(8, r.bottom + height + 4 * scale < innerHeight ? r.bottom + 4 * scale : r.top - height - 4 * scale),
        '--finding-menu-scale': scale });
    };
    const outside = e => {
      if (!trigger.current?.contains(e.target) && !menu.current?.contains(e.target)) setOpen(false);
    };
    place();
    addEventListener('resize', place);
    addEventListener('scroll', place, true);
    document.addEventListener('pointerdown', outside);
    document.addEventListener('focusin', outside);
    return () => {
      removeEventListener('resize', place);
      removeEventListener('scroll', place, true);
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('focusin', outside);
    };
  }, [open]);
  useEffect(() => { if (open && position) menu.current?.querySelector('button')?.focus({ preventScroll:true }); }, [open, !!position]);
  const close = () => { setOpen(false); trigger.current?.focus({ preventScroll:true }); };
  const keyDown = e => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
      e.preventDefault();
      const items = [...menu.current.querySelectorAll('button')];
      const index = items.indexOf(document.activeElement);
      items[e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (index + (e.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length].focus();
    }
  };
  const pick = action => { setOpen(false); action(); };
  return <>
    <button ref={trigger} type="button" className="finding-menu-trigger" aria-label={`Действия: ${name}`}
      aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={e => { e.stopPropagation(); setOpen(v => !v); }}
      onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); } }}>
      <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>
    </button>
    {open && position && createPortal(<div ref={menu} id={id} role="menu" aria-label={`Действия: ${name}`}
      className="finding-menu" style={position} onKeyDown={keyDown} onClick={e => e.stopPropagation()}>
      <button type="button" role="menuitem" onClick={() => pick(onEdit)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m10 3-.5 2-2 .9-1.9-.6-2 3.4L5 10v2l-1.4 1.3 2 3.4 1.9-.6 2 .9.5 2h4l.5-2 2-.9 1.9.6 2-3.4L19 12v-2l1.4-1.3-2-3.4-1.9.6-2-.9-.5-2Z"/><circle cx="12" cy="11" r="3"/></svg>
        Редактировать
      </button>
      <button type="button" role="menuitem" className="finding-menu-delete" onClick={() => pick(onRemove)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 9v9m4-9v9"/></svg>
        Удалить
      </button>
    </div>, document.body)}
  </>;
}
