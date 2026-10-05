import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { USE_MOCK, API_URL, UNAUTHORIZED, api, detectCaps, demo } from './api';
import { session } from './api/session';
import { CURRENT_DOCTOR } from './config';
import { fmtDateTime } from './lib/format';
import { Revision, Toast, go, useMedia, useRoute } from './lib/hooks';
import { Archive, ArrowLeft, Briefcase, GridIcon, Inbox, LogOut, Logo } from './components/Icons';
import Findings from './pages/Findings';
import Patients from './pages/Patients';
import PatientCard from './pages/PatientCard';
import Dictionary from './pages/Dictionary';
import Dashboard from './pages/Dashboard';
import Login, { logout } from './pages/Login';
import PushCard from './pages/PushCard';
import MobileRecord from './pages/MobileRecord';

// Мобильная страница записи по ссылке из SMS: /next-step/<id> (или #/next-step/<id>) — без входа
const mobileRecordId = () => location.pathname.match(/\/next-step\/([^/]+)/)?.[1];

// Документация API грузится отдельным чанком и открывается только по прямому адресу
const ApiDocs = lazy(() => import('./pages/ApiDocs'));
const isDocsPath = () => /\/open-api\/?$/.test(location.pathname);

// Пункты меню — как в макете (без «Настроек»; словарь находок доступен по адресу #/settings)
const NAV = [
  ['dashboard', 'Дашборд', GridIcon],
  ['inbox', 'Входящие', Inbox],
  ['findings', 'Находки', Briefcase],
  ['archive', 'Картотека', Archive],
];
const STEPS = [[24, '+24 ч'], [72, '+72 ч'], [168, '+7 дн'], [720, '+30 дн']];
const BACK = [[-24, '−24 ч'], [-72, '−72 ч'], [-168, '−7 дн'], [-720, '−30 дн']];

export default function App() {
  const [section = 'findings', id, sub] = useRoute();
  const [rev, setRev] = useState(0);
  const [toasts, setToasts] = useState([]);
  const [collapsed, setCollapsed] = useState(false);
  // authed: null — проверяем сессию (GET /api/auth/me), true/false — результат
  const [authed, setAuthed] = useState(() => (session.has() ? null : false));
  const [ready, setReady] = useState(false);
  // 721–1000 px: меню сворачивается само; на телефоне — нижняя панель, класс collapsed не нужен
  const narrow = useMedia('(min-width: 721px) and (max-width: 1000px)');
  const mobile = useMedia('(max-width: 720px)');
  const isCollapsed = !mobile && (collapsed || narrow);
  useEffect(() => {
    if (authed !== null) return;
    api.me().then(() => setAuthed(true), () => { session.clear(); setAuthed(false); });
  }, [authed]);
  useEffect(() => { if (authed) detectCaps().then(() => setReady(true)); }, [authed]);   // возможности сервера — после входа
  useEffect(() => {
    const drop = () => { session.clear(); setReady(false); setAuthed(false); };   // 401 из любого запроса
    addEventListener(UNAUTHORIZED, drop);
    return () => removeEventListener(UNAUTHORIZED, drop);
  }, []);

  const toast = useCallback((text, tone = 'ok') => {
    const key = Math.random();
    setToasts((t) => [...t, { key, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.key !== key)), 4000);
  }, []);
  useEffect(() => { window.scrollTo(0, 0); }, [section, id]);

  // Авторизация: без входа показывается только страница логина (документация /open-api доступна без входа)
  const recordId = mobileRecordId() ?? (section === 'next-step' ? id : null);
  if (recordId) return <MobileRecord id={decodeURIComponent(recordId)} />;
  if (authed === null && section !== 'open-api' && !isDocsPath()) return <p className="state">Проверяем вход…</p>;
  if (!authed && section !== 'open-api' && !isDocsPath()) return <Login onLogin={() => setAuthed(true)} />;

  if (section === 'open-api' || isDocsPath()) {
    return <Suspense fallback={<p className="state">Загружаем документацию API…</p>}><ApiDocs /></Suspense>;
  }

  const page = !ready ? <p className="state">Подключаемся к серверу…</p>
    : section === 'patients' && id ? <PatientCard id={id} />
    : section === 'push' && id ? <PushCard id={id} routeId={sub} />
    : section === 'inbox' ? <Patients key="inbox" preset="inbox" />
    : section === 'archive' ? <Patients key="archive" preset="archive" />
    : section === 'settings' ? <Dictionary /> : section === 'dashboard' ? <Dashboard /> : <Findings />;
  // Карточка пациента — раздел «Картотека», карточка уведомлений (push) открывается из «Находок»
  const current = section === 'patients' ? 'archive' : section === 'push' ? 'findings' : section;

  return (
    <Toast.Provider value={toast}>
      <Revision.Provider value={rev}>
        <div className={`layout${isCollapsed ? ' collapsed' : ''}`}>
          <header className="mobile-top"><Logo height={22} /><UserMenu mobile onLogout={() => logout().then(() => { setReady(false); setAuthed(false); })} /></header>
          <aside className="sidebar">
            <a className="brand" href="#/findings" aria-label="СМ-Клиника, на главную"><Logo /></a>
            <nav className="nav" aria-label="Разделы">
              {NAV.map(([key, label, Icon]) => (
                <a key={key} href={`#/${key}`} className="nav-item" aria-current={current === key ? 'page' : undefined} title={label}>
                  <Icon size={16} /><span>{label}</span>
                </a>
              ))}
            </nav>
            <div className="nav-bottom">
              <UserMenu onLogout={() => logout().then(() => { setReady(false); setAuthed(false); })} />
              {!narrow && <button className="nav-item faint" onClick={() => setCollapsed((v) => !v)} aria-expanded={!collapsed} title={collapsed ? 'Развернуть' : 'Свернуть'}>
                <ArrowLeft size={16} className={collapsed ? 'flip' : undefined} /><span>Свернуть</span>
              </button>}
            </div>
          </aside>
          <main className="main">{page}</main>
        </div>
        {USE_MOCK && <DemoPanel onChange={() => setRev((r) => r + 1)} toast={toast} />}
        {!USE_MOCK && <p className="api-note">API: {API_URL || location.origin}</p>}
        <div className="toasts" role="status">{toasts.map((t) => <div key={t.key} className={`toast ${t.tone}`}>{t.text}</div>)}</div>
      </Revision.Provider>
    </Toast.Provider>
  );
}

/** Профиль врача внизу меню: по клику открывается белая карточка с кнопкой «Выйти» (макет «Правило»). Выход ведёт на авторизацию */
function UserMenu({ onLogout, mobile }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const esc = (e) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', away); addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', away); removeEventListener('keydown', esc); };
  }, [open]);
  const initials = CURRENT_DOCTOR.split(/\s+/).slice(0, 2).map((w) => w[0]).join('');
  const who = <><span className="nav-avatar" aria-hidden="true">{initials}</span><span className="nav-user-text"><span>{CURRENT_DOCTOR}</span><small>Врач</small></span></>;
  return (
    <div className={`user-menu${open ? ' open' : ''}${mobile ? ' mobile' : ''}${mobile && USE_MOCK ? ' with-demo' : ''}`} ref={ref}>
      <button className="nav-user" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>{who}</button>
      {open && (
        <div className="user-pop" role="menu">
          <button className="nav-user" onClick={() => setOpen(false)} aria-label="Закрыть меню профиля">{who}</button>
          <button role="menuitem" className="nav-item logout" onClick={onLogout}><LogOut size={16} className="flip" /><span>Выйти</span></button>
        </div>
      )}
    </div>
  );
}

/** Демо-режим (только с заглушками): модельное время и поступление протоколов. Свёрнут в кнопку, чтобы не мешать макету */
function DemoPanel({ onChange, toast }) {
  const [open, setOpen] = useState(false);
  const [, force] = useState(0);
  const update = () => { force((n) => n + 1); onChange(); };
  const receive = () => {
    const pid = demo.receiveNext();
    update();
    toast('Поступил новый протокол: находка ждёт проверки врача');
    if (pid) go(`patients/${pid}`);
  };
  return (
    <div className={`demo${open ? ' open' : ''}`}>
      {open && (
        <div className="demo-body">
          <p><b>Демо-режим.</b> Данные из docs/ml-results, изменения живут до перезагрузки.</p>
          <p className="demo-time">Модельное время: <b>{fmtDateTime(demo.now())}</b></p>
          <p className="demo-label">Вперёд</p>
          <div className="demo-steps">{STEPS.map(([h, l]) => <button key={h} className="chip" onClick={() => { demo.advance(h); update(); }}>{l}</button>)}</div>
          <p className="demo-label">Назад <span>откатывает всё, что произошло позже</span></p>
          <div className="demo-steps">
            {BACK.map(([h, l]) => <button key={h} className="chip" disabled={!demo.canRewind()} onClick={() => { demo.advance(h); update(); }}>{l}</button>)}
            <button className="chip" disabled={!demo.canRewind()} onClick={() => { demo.reset(); update(); toast('Демо возвращено к началу'); }}>К началу</button>
          </div>
          <button className="btn-main" disabled={!demo.queueLeft()} onClick={receive}>Поступил протокол из МИС ({demo.queueLeft()})</button>
        </div>
      )}
      <button className="demo-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open}>{open ? 'Скрыть' : 'Демо'}</button>
    </div>
  );
}
