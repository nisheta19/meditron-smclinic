// «Отправить уведомление» по макету pushes.fig: маршрут, шаблон (радио), текст сообщения, «Отправить» / «Отмена».
// Одно уведомление (из карточки) или пачка (выделенные строки «Находок»). Сообщение уходит SMS со ссылкой
// на мобильную страницу записи /next-step/<routeId>. Сервер сам защищает от спама (429) и экстренных находок (409).
import { useState } from 'react';
import { api, caps } from '../api';
import { Dialog, DialogActions, Field, TextArea } from './ui';
import Dropdown from './Dropdown';

export const PUSH_TEMPLATES = [
  { id: 'remind', title: 'Напоминание о записи',
    text: 'Напоминание: по результату УЗИ Вам рекомендована консультация специалиста ({специалист}). Консультация нужна, чтобы уточнить результат исследования. Вы можете выбрать удобный формат — очно или онлайн: {ссылка}' },
  { id: 'noshow', title: 'После неявки',
    text: 'Запланированная консультация ({специалист}) не состоялась. Если вопрос остаётся актуальным, выберите другое время — очно или онлайн: {ссылка}' },
  { id: 'ready', title: 'Результат готов',
    text: 'Ваш результат УЗИ готов. В исследовании описаны изменения, по которым рекомендуется консультация специалиста ({специалист}). Записаться: {ссылка}' },
];
// Адрес для пациента: VITE_PUBLIC_URL (публичный адрес фронта) или текущий origin; из файла — относительная ссылка
const PUBLIC_URL = (import.meta.env.VITE_PUBLIC_URL || (/^https?:$/.test(location.protocol) ? location.origin : '')).replace(/\/$/, '');
export const recordLink = (routeId) => `${PUBLIC_URL}/next-step/${encodeURIComponent(routeId)}`;
const fill = (text, t) => text.replaceAll('{специалист}', (t.specialist ?? 'профильный врач').toLowerCase()).replaceAll('{ссылка}', recordLink(t.routeId));

/**
 * targets: [{ routeId, specialist, label }] — маршруты для выбора (одиночная отправка) или все выбранные (пачка).
 * Старый вызов routeIds={[…]} тоже поддерживается.
 */
export default function NotifyDialog({ targets: given, routeIds = [], recent = 0, bulk, onClose, onDone }) {
  const targets = given ?? routeIds.map((routeId) => ({ routeId }));
  const many = bulk || (targets.length > 1 && !given);
  const [routeId, setRouteId] = useState(targets[0]?.routeId);
  const [tpl, setTpl] = useState(PUSH_TEMPLATES[0].id);
  const [text, setText] = useState(PUSH_TEMPLATES[0].text);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const chosen = many ? targets : targets.filter((t) => t.routeId === routeId);
  const preview = many ? text : fill(text, chosen[0] ?? {});
  const pick = (id) => { setTpl(id); setText(PUSH_TEMPLATES.find((t) => t.id === id).text); };

  const send = async () => {
    setBusy(true);
    const res = { sent: 0, tooFrequent: 0, errors: [] };
    for (const t of chosen) {
      try { await api.notify(t.routeId, { channel: 'SMS', text: fill(text, t) }); res.sent++; }
      catch (e) { e.status === 429 ? res.tooFrequent++ : res.errors.push(e.notImplemented ? 'сервер пока не принимает уведомления (метод не реализован)' : e.message); }
    }
    setResult(res); setBusy(false); onDone?.(res);
  };

  if (result) return (
    <Dialog title={result.sent ? 'Уведомление отправлено' : 'Уведомление не отправлено'} onClose={onClose}
      actions={<button className="btn-main" onClick={onClose}>Готово</button>}>
      <ul className="push-result">
        <li>Отправлено: <b>{result.sent}</b></li>
        {result.tooFrequent > 0 && <li>Пропущено, уже уведомлены за 24 ч: <b>{result.tooFrequent}</b></li>}
        {[...new Set(result.errors)].map((m) => <li key={m}>Не отправлено ({result.errors.filter((x) => x === m).length}): {m}</li>)}
      </ul>
    </Dialog>
  );

  return (
    <Dialog title="Отправить уведомление" onClose={onClose} actions={
      <DialogActions onCancel={onClose}>
        <button className="btn-main" disabled={busy || !chosen.length || !text.trim()} onClick={send}>{busy ? 'Отправляем…' : 'Отправить уведомление'}</button>
      </DialogActions>}>
      {!caps.notifications && <p className="callout">Сервер пока не сообщил, что принимает уведомления. Попробуем отправить — в итоге будет видно, что не ушло.</p>}
      {recent > 0 && <p className="callout">Уже получили сообщение за последние 24 ч: {recent}. Сервер их пропустит.</p>}

      <Field as="div" label="Маршрут">
        {many
          ? <div className="push-box">Выбрано маршрутов: {targets.length}</div>
          : <Dropdown ariaLabel="Маршрут" value={routeId} onChange={setRouteId} options={targets.map((t) => [t.routeId, t.label ?? t.specialist ?? 'Маршрут'])} />}
      </Field>

      <Field as="div" label="Шаблон" role="radiogroup" aria-label="Шаблон">
        {PUSH_TEMPLATES.map((t) => (
          <label key={t.id} className={`push-radio${tpl === t.id ? ' on' : ''}`}>
            <input type="radio" name="push-tpl" checked={tpl === t.id} onChange={() => pick(t.id)} />
            <i aria-hidden="true" />{t.title}
          </label>
        ))}
      </Field>

      <Field label="Сообщение" hint={many && <>{'{специалист}'} и {'{ссылка}'} подставятся для каждого пациента</>}>
        <TextArea value={many ? text : preview} onChange={setText} />
      </Field>
    </Dialog>
  );
}
