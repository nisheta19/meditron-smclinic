// Мобильная страница записи для пациента (макет mobile.fig, «Уведомление пациенту»).
// Ссылка приходит в SMS: /next-step/<id>. Пока статическая демо-страница: запись происходит только
// на фронте (backend не трогаем), данные — демо. Вход в систему не нужен.
import { useMemo, useState } from 'react';
import { Logo, Chevron } from '../components/Icons';
import './mobile.css';

const CLINICS = ['Москва, Волгоградский пр-т., 42к12', 'Москва, м. Марьино', 'Москва, м. Медведково'];
const DOCTORS = [
  { name: 'Ковалёв А. С.', role: 'Хирург', exp: 12 },
  { name: 'Орлова Е. В.', role: 'Хирург', exp: 8 },
  { name: 'Миронов Д. П.', role: 'Хирург', exp: 15 },
];
const WEEK = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const TIMES = ['09:00', '09:30', '10:00', '11:00', '12:30', '14:00', '15:30', '17:00', '18:30'];
const years = (n) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? 'год' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'года' : 'лет'}`;

/** Ближайшие 14 дней, воскресенье — выходной; часть слотов «занята» детерминированно */
function useSlots() {
  return useMemo(() => {
    const today = new Date(); today.setHours(0, 0, 0, 0);
    return Array.from({ length: 14 }, (_, i) => {
      const d = new Date(today); d.setDate(today.getDate() + i + 1);
      const busy = new Set(TIMES.filter((_, k) => (d.getDate() * 7 + k * 3) % 5 === 0));
      return { date: d, off: d.getDay() === 0, busy };
    });
  }, []);
}

export default function MobileRecord({ id = 'demo' }) {
  const slots = useSlots();
  const [mode, setMode] = useState('clinic');
  const [clinic, setClinic] = useState(0);
  const [doctor, setDoctor] = useState(0);
  const [day, setDay] = useState(() => slots.findIndex((s) => !s.off));
  const [time, setTime] = useState(null);
  const [sheet, setSheet] = useState(null);
  const [done, setDone] = useState(false);
  const d = slots[day];
  const free = TIMES.filter((t) => !d.busy.has(t));
  const chosenTime = time && free.includes(time) ? time : free[0];
  const doc = DOCTORS[doctor];
  const when = d.date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', weekday: 'long' });

  if (done) return (
    <div className="mr">
      <header className="mr-top"><Logo height={26} /></header>
      <main className="mr-sheet mr-done">
        <div className="mr-check" aria-hidden="true"><svg viewBox="0 0 24 24" width="36" height="36"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg></div>
        <h1>Вы записаны</h1>
        <p className="mr-sub">Напомним о приёме в SMS за день и за 2 часа</p>
        <dl className="mr-summary">
          <div><dt>Формат</dt><dd>{mode === 'clinic' ? 'В клинике' : 'Онлайн, ссылка придёт в SMS'}</dd></div>
          {mode === 'clinic' && <div><dt>Клиника</dt><dd>{CLINICS[clinic]}</dd></div>}
          <div><dt>Врач</dt><dd>{doc.name}, {doc.role.toLowerCase()}</dd></div>
          <div><dt>Когда</dt><dd>{when}, {chosenTime}</dd></div>
        </dl>
        <button className="mr-btn ghost" onClick={() => setDone(false)}>Изменить запись</button>
      </main>
    </div>
  );

  return (
    <div className="mr" data-record={id}>
      <header className="mr-top"><Logo height={26} /></header>
      <main className="mr-sheet">
        <h1>Здравствуйте, Анна</h1>
        <p className="mr-sub">Подобрали специалиста по вашему анализу</p>

        <div className="mr-seg" role="tablist" aria-label="Формат приёма">
          <span className="mr-seg-thumb" data-pos={mode} aria-hidden="true" />
          <button role="tab" aria-selected={mode === 'clinic'} onClick={() => setMode('clinic')}>В клинике</button>
          <button role="tab" aria-selected={mode === 'online'} onClick={() => setMode('online')}>Онлайн</button>
        </div>

        {mode === 'clinic' ? (
          <section className="mr-field">
            <span>Клиника</span>
            <button className="mr-box mr-select" onClick={() => setSheet('clinic')}>{CLINICS[clinic]}<Chevron size={12} /></button>
          </section>
        ) : (
          <p className="mr-note">Консультация по видеосвязи. Ссылка на звонок придёт в SMS за 15 минут до начала.</p>
        )}

        <section className="mr-field">
          <span>Врач</span>
          <div className="mr-box mr-doctor">
            <span className="mr-avatar" aria-hidden="true">{doc.name.split(' ').slice(0, 2).map((w) => w[0]).join('')}</span>
            <span className="mr-doc-text"><b>{doc.name}</b><small>{doc.role} · стаж {years(doc.exp)}</small></span>
            <button className="mr-link" onClick={() => setSheet('doctor')}>Изменить</button>
          </div>
        </section>

        <section className="mr-field">
          <span>Дата</span>
          <div className="mr-scroll" role="listbox" aria-label="Дата">
            {slots.map((s, i) => (
              <button key={i} role="option" aria-selected={i === day} disabled={s.off} className="mr-day" onClick={() => { setDay(i); setTime(null); }}>
                <b>{s.date.getDate()}</b><small>{WEEK[s.date.getDay()]}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="mr-field">
          <span>Время</span>
          <div className="mr-scroll" role="listbox" aria-label="Время">
            {TIMES.map((t) => (
              <button key={t} role="option" aria-selected={t === chosenTime} disabled={d.busy.has(t)} className="mr-time" onClick={() => setTime(t)}>{t}</button>
            ))}
          </div>
        </section>

        <button className="mr-btn" disabled={!chosenTime} onClick={() => setDone(true)}>Записаться</button>
      </main>

      {sheet && (
        <div className="mr-overlay" onClick={() => setSheet(null)}>
          <div className="mr-panel" role="dialog" aria-modal="true" aria-label={sheet === 'clinic' ? 'Выбор клиники' : 'Выбор врача'} onClick={(e) => e.stopPropagation()}>
            <i className="mr-grip" aria-hidden="true" />
            <h2>{sheet === 'clinic' ? 'Клиника' : 'Врач'}</h2>
            {(sheet === 'clinic' ? CLINICS : DOCTORS).map((item, i) => {
              const on = i === (sheet === 'clinic' ? clinic : doctor);
              return (
                <button key={i} className={`mr-option${on ? ' on' : ''}`}
                  onClick={() => { (sheet === 'clinic' ? setClinic : setDoctor)(i); setSheet(null); }}>
                  {typeof item === 'string' ? item : <span className="mr-doc-text"><b>{item.name}</b><small>{item.role} · стаж {years(item.exp)}</small></span>}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
