import { useRef, useState } from 'react';
import { api } from '../api';
import { CURRENT_DOCTOR } from '../config';
import { useAsync } from '../lib/hooks';
import { Dialog, ErrorBox } from './ui';
import './ClinicalNotifyDialog.css';

/** Uses server templates and explicit confirmation for a repeated message. */
export default function ClinicalNotifyDialog({routes, onClose, onDone}) {
  const templates = useAsync(() => api.notificationTemplates(), []);
  const [routeId,setRouteId] = useState(routes[0]?.id ?? '');
  const [templateCode,setTemplateCode] = useState('');
  const [confirm,setConfirm] = useState(false);
  const [error,setError] = useState(null);
  const [busy,setBusy] = useState(false);
  const [sent,setSent] = useState(null);
  const submitting = useRef(false);
  const options = (templates.data ?? []).filter(t => t.manual);
  const code = templateCode || options.find(t => t.code === 'REMINDER_24H')?.code || options[0]?.code;
  const preview = useAsync(async () => routeId && code ? {routeId,...await api.notificationPreview(routeId,code)} : null,[routeId,code]);
  const message = preview.data?.routeId === routeId && preview.data?.templateCode === code ? preview.data : null;
  const send = async () => {
    if (submitting.current || !routeId || !code || !message || preview.loading || preview.error) return;
    submitting.current = true; setBusy(true); setError(null);
    try { setSent(await api.notify(routeId,{templateCode:code,confirm,doctor:CURRENT_DOCTOR})); onDone(); }
    catch(e) { if(e.code === 'CONFIRM_REQUIRED') setConfirm(true); else { setConfirm(false); setError(e); } }
    finally { submitting.current = false; setBusy(false); }
  };
  return <Dialog className="clinical-notify" title="Отправить уведомление" onClose={busy ? () => {} : onClose} actions={sent ?
    <button className="btn primary" onClick={onClose}>Готово</button> : <>
      <button className="btn primary" disabled={busy || templates.loading || !!templates.error || preview.loading || !!preview.error || !message || !routes.some(r => r.id === routeId)} onClick={send}>
        {busy ? 'Отправляем…' : confirm ? 'Отправить повторно' : 'Отправить уведомление'}
      </button>
      <button className="btn ghost" disabled={busy} onClick={onClose}>Отмена</button>
    </>}>
    {sent ? <><p role="status">Уведомление передано в CRM.</p><p>{sent.fullText}</p></> : <>
      <label className="field"><span>Маршрут</span><select aria-label="Маршрут" value={routeId} disabled={busy} onChange={e => {setRouteId(e.target.value);setConfirm(false);setError(null);}}>
        {routes.map(r => <option key={r.id} value={r.id}>{r.specialty}</option>)}
      </select></label>
      {templates.error ? <ErrorBox error={templates.error} onRetry={templates.reload} /> :
        <fieldset className="notify-templates" disabled={busy || templates.loading}><legend>Шаблон</legend>
          {!options.length && <p>{templates.loading ? 'Загружаем…' : 'Нет доступных шаблонов'}</p>}
          <div>{options.map(t => <label className="notify-template" key={t.code}><input type="radio" name="notification-template" value={t.code} checked={code === t.code} onChange={() => {setTemplateCode(t.code);setConfirm(false);setError(null);}} /><span>{t.title}</span></label>)}</div>
        </fieldset>}
      <div className="notify-preview"><span>Сообщение</span>{templates.loading || preview.loading || (code && !message && !preview.error) ? <p aria-busy="true">Загружаем сообщение…</p> : preview.error ? <ErrorBox error={preview.error} onRetry={preview.reload} /> : <p>{message?.fullText ?? 'Выберите маршрут и шаблон'}</p>}</div>
      {confirm && <p role="alert">Пациенту уже отправляли уведомление за последние 24 часа. Подтвердите повторную отправку.</p>}
      {error && <p role="alert">{error.message}</p>}
    </>}
  </Dialog>;
}
