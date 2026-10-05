import Dropdown from './Dropdown';
import { useEffect, useState } from 'react';
export { default as DateField } from './DateField';

export const Badge = ({ tone = 'neutral', children, title }) => <span className={`badge ${tone}`} title={title}>{children}</span>;

/** Бейдж по словарю вида { KEY: [подпись, тон] } */
export const EnumBadge = ({ map, value }) => (value ? <Badge tone={map[value]?.[1]}>{map[value]?.[0] ?? value}</Badge> : null);

export function useEsc(fn) {
  useEffect(() => {
    const h = (e) => e.key === 'Escape' && fn();
    addEventListener('keydown', h);
    return () => removeEventListener('keydown', h);
  }, [fn]);
}

export function Dialog({ title, onClose, children, actions, wide, className = '' }) {
  useEsc(onClose);
  return (
    <div className={`overlay${className ? ` ${className}-overlay` : ''}`} onMouseDown={onClose}>
      <div className={`dialog${wide ? ' wide' : ''} ${className}`} role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
        <header><h2>{title}</h2><button className="icon" aria-label="Закрыть" onClick={onClose}>×</button></header>
        <div className="dialog-body">{children}</div>
        {actions && <footer className="actions">{actions}</footer>}
      </div>
    </div>
  );
}

/** Диалог с причиной: отклонить находку, удалить, отменить маршрут */
export function ReasonDialog({ title, label = 'Причина', action, danger, onSubmit, onClose }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => { setBusy(true); try { await onSubmit(text.trim()); onClose(); } catch { setBusy(false); } };
  return (
    <Dialog title={title} onClose={onClose} actions={<>
      <button className="btn ghost" onClick={onClose}>Отмена</button>
      <button className={`btn ${danger ? 'danger' : 'primary'}`} disabled={busy} onClick={submit}>{action}</button>
    </>}>
      <label className="field"><span>{label}</span><textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} autoFocus /></label>
    </Dialog>
  );
}

export const ErrorBox = ({ error, onRetry }) => (
  <div className="error-box">
    <p>Не удалось загрузить данные: {error.message}.</p>
    {error.code === 'NETWORK' && <p className="muted">Соединение с сервером недоступно. Попробуйте загрузить данные снова.</p>}
    {onRetry && <button className="btn ghost" onClick={onRetry}>Повторить</button>}
  </div>
);

/** Поле-выпадающий список с подписью (обёртка над Dropdown) */
export const Select = ({ label, value, onChange, options, all = 'Все', neutral = true }) => (
  <Dropdown label={label} value={value} onChange={onChange} options={options} all={all} neutral={neutral} />
);
