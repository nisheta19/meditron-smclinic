import Dropdown from './Dropdown';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { CloseLg } from './Icons';

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

/**
 * Модальное окно по макету pushes.fig: заголовок, круглая кнопка закрытия, поля, кнопки внизу
 * (главное действие первым, «Отмена» — второй). На телефоне — шторка снизу.
 */
export function Dialog({ title, onClose, children, actions, wide }) {
  useEsc(onClose);
  return (
    <div className="overlay" onMouseDown={onClose}>
      <div className={`dialog${wide ? ' wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        <button className="dialog-close" aria-label="Закрыть" onClick={onClose}><CloseLg size={22} /></button>
        <div className="dialog-body">{children}</div>
        {actions && <footer className="dialog-actions">{actions}</footer>}
      </div>
    </div>
  );
}

/** Поле с подписью сверху и необязательной подсказкой снизу. as="div" — когда внутри не один контрол (радио, Dropdown) */
export const Field = ({ label, hint, grow, as: Tag = 'label', className = '', children, ...rest }) => (
  <Tag className={`field${grow ? ' grow' : ''} ${className}`.trim()} {...rest}>
    <span>{label}</span>{children}{hint && <small>{hint}</small>}
  </Tag>
);

/** Многострочное поле, растёт по тексту: весь текст виден с одинаковыми отступами сверху и снизу */
export function TextArea({ value, onChange, ...rest }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return <textarea ref={ref} rows={2} value={value} onChange={(e) => onChange(e.target.value)} {...rest} />;
}

/** Кнопки диалога: главное действие + «Отмена» */
export const DialogActions = ({ onCancel, cancel = 'Отмена', children }) => (
  <>{children}<button className="chip" onClick={onCancel}>{cancel}</button></>
);

/** Диалог с причиной: отклонить находку, удалить, отменить маршрут */
export function ReasonDialog({ title, label = 'Причина', action, danger, onSubmit, onClose }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => { setBusy(true); try { await onSubmit(text.trim()); onClose(); } catch { setBusy(false); } };
  return (
    <Dialog title={title} onClose={onClose} actions={
      <DialogActions onCancel={onClose}>
        <button className={danger ? 'btn danger' : 'btn-main'} disabled={busy} onClick={submit}>{action}</button>
      </DialogActions>}>
      <Field label={label}><TextArea value={text} onChange={setText} autoFocus /></Field>
    </Dialog>
  );
}

export const ErrorBox = ({ error, onRetry }) => (
  <div className="error-box">
    <p>Не удалось загрузить данные: {error.message}.</p>
    {error.code === 'NETWORK' && <p className="muted">Запустите backend или откройте демо-режим: VITE_USE_MOCK=true либо ?mock=1 в адресе.</p>}
    {onRetry && <button className="btn ghost" onClick={onRetry}>Повторить</button>}
  </div>
);

/** Поле-выпадающий список с подписью (обёртка над Dropdown) */
export const Select = ({ label, value, onChange, options, all = 'Все' }) => (
  <Dropdown label={label} value={value} onChange={onChange} options={options} all={all} />
);
