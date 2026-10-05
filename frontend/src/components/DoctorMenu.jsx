import { useEffect, useId, useRef, useState } from 'react';
import { USE_MOCK } from '../api/client';
import { logoutAccount } from '../api/auth';
import './DoctorMenu.css';

export default function DoctorMenu({ name, onLogout, onError, onOpenChange }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const root = useRef(null);
  const trigger = useRef(null);
  const menuId = useId();
  const changeOpen = value => { setOpen(value); onOpenChange?.(value); };

  useEffect(() => {
    if (!open) return;
    root.current?.querySelector('.doctor-menu-identity')?.focus({ preventScroll: true });
    const outside = event => { if (!root.current?.contains(event.target)) changeOpen(false); };
    const escape = event => {
      if (event.key === 'Escape') {
        changeOpen(false);
        requestAnimationFrame(() => trigger.current?.focus({ preventScroll: true }));
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  const exit = async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (!USE_MOCK) await logoutAccount();
      changeOpen(false);
      onLogout();
    } catch {
      onError?.('Не удалось выйти. Попробуйте ещё раз.');
    } finally { setBusy(false); }
  };
  const identity = <><span className="nav-avatar" aria-hidden="true" />
    <span className="nav-user-text"><span>{name}</span><small>Врач</small></span></>;

  return <div ref={root} className={`doctor-menu${open ? ' is-open' : ''}`} onBlur={event => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) changeOpen(false);
  }}>
    <button ref={trigger} type="button" className="nav-user doctor-menu-trigger" title={name}
      aria-label={`Профиль врача: ${name}`} aria-expanded={open} aria-controls={open ? menuId : undefined}
      onClick={() => changeOpen(!open)}>{identity}</button>
    {open && <div id={menuId} className="doctor-menu-card" aria-label="Профиль врача">
      <button type="button" className="nav-user doctor-menu-identity" aria-label="Закрыть профиль врача"
        onClick={() => { changeOpen(false); requestAnimationFrame(() => trigger.current?.focus({ preventScroll: true })); }}>{identity}</button>
      <button type="button" className="doctor-menu-logout" disabled={busy} onClick={exit}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M10 14h2.6667A1.3333 1.3333 0 0 0 14 12.6667V3.3333A1.3333 1.3333 0 0 0 12.6667 2H10M5.3335 11.3333 2.0002 8l3.3333-3.3333M2 8h8"
            stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg><span>Выйти</span>
      </button>
    </div>}
  </div>;
}
