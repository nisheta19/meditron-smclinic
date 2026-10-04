import { useState } from 'react';
import { api, caps } from '../api';
import { CHANNEL } from '../lib/format';
import { Dialog } from './ui';

/** «Пуш» по одному или нескольким маршрутам. Сервер сам защищает от спама (429) и экстренных находок (409). */
export default function NotifyDialog({ routeIds, recent = 0, onClose, onDone }) {
  const [channel, setChannel] = useState('PERSONAL_ACCOUNT');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const send = async () => {
    setBusy(true);
    const res = { sent: 0, tooFrequent: 0, errors: [] };
    for (const id of routeIds) {
      try { await api.notify(id, { channel, ...(text.trim() && { text: text.trim() }) }); res.sent++; }
      catch (e) { e.status === 429 ? res.tooFrequent++ : res.errors.push(e.notImplemented ? 'сервер пока не принимает уведомления (метод не реализован)' : e.message); }
    }
    setResult(res); setBusy(false); onDone?.(res);
  };

  if (result) return (
    <Dialog title={result.sent ? 'Уведомления отправлены' : 'Уведомление не отправлено'} onClose={onClose} actions={<button className="btn primary" onClick={onClose}>Готово</button>}>
      <ul className="result">
        <li>Отправлено: <b>{result.sent}</b></li>
        {result.tooFrequent > 0 && <li>Пропущено, уже уведомлены за 24 ч: <b>{result.tooFrequent}</b></li>}
        {[...new Set(result.errors)].map((m) => <li key={m}>Не отправлено ({result.errors.filter((x) => x === m).length}): {m}</li>)}
      </ul>
    </Dialog>
  );

  return (
    <Dialog title={routeIds.length > 1 ? `Уведомление: ${routeIds.length} маршрутов` : 'Уведомление пациенту'} onClose={onClose} actions={<>
      <button className="btn ghost" onClick={onClose}>Отмена</button>
      <button className="btn primary" disabled={busy} onClick={send}>{busy ? 'Отправляем…' : 'Отправить'}</button>
    </>}>
      {!caps.notifications && <p className="callout">Сервер пока не сообщил, что принимает уведомления. Попробуем отправить — если метод
        не поддерживается, в итоге будет указано, какие сообщения не ушли.</p>}
      {recent > 0 && <p className="callout">Уже получили сообщение за последние 24 ч: {recent}. Сервер их пропустит, чтобы не перегружать пациентов.</p>}
      <fieldset>
        <legend>Канал</legend>
        <div className="chips wrap">
          {Object.entries(CHANNEL).map(([k, l]) => (
            <label key={k} className="chip"><input type="radio" name="channel" checked={channel === k} onChange={() => setChannel(k)} />{l}</label>
          ))}
        </div>
      </fieldset>
      <label className="field">
        <span>Текст сообщения</span>
        <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Оставьте пустым: возьмётся нейтральный текст из шаблона текущего этапа" />
      </label>
      <p className="hint">
        {channel === 'SMS' ? 'В SMS не указывайте находку и диагноз: только приглашение открыть личный кабинет.' : 'Сообщение не должно содержать диагноз: только рекомендацию и способ записаться.'}
      </p>
    </Dialog>
  );
}
