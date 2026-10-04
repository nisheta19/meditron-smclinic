import { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { USE_MOCK, API_URL, capsReady, demo } from './api';
import { DOCTOR_DISPLAY_NAME } from './config';
import { fmtDateTime } from './lib/format';
import { Revision, Toast, go, useMedia, useRoute } from './lib/hooks';
import { Archive, ArrowLeft, Briefcase, Grid, Inbox, Logo, Tool } from './components/Icons';
import Findings from './pages/Findings';
import Patients from './pages/Patients';
import PatientCard from './pages/PatientCard';

// Документация API грузится отдельным чанком и открывается только по прямому адресу
const ApiDocs = lazy(() => import('./pages/ApiDocs'));
const isDocsPath = () => /\/open-api\/?$/.test(location.pathname);

// Пункты меню — как в макете
const NAV = [
  ['inbox', 'Входящие', Inbox],
  ['findings', 'Находки', Briefcase],
  ['archive', 'Картотека', Archive],
  ['settings', 'Настройки', Tool],
];
const STEPS = [[24, '+24 ч'], [72, '+72 ч'], [168, '+7 дн'], [720, '+30 дн']];

export default function App() {
  const [section = 'findings', id] = useRoute();
  const [rev, setRev] = useState(0);
  const [toasts, setToasts] = useState([]);
  const [collapsed, setCollapsed] = useState(false);
  const [ready, setReady] = useState(USE_MOCK);
  // 721–1000 px: меню сворачивается само; на телефоне — нижняя панель, класс collapsed не нужен
  const narrow = useMedia('(min-width: 721px) and (max-width: 1000px)');
  const mobile = useMedia('(max-width: 720px)');
  const isCollapsed = !mobile && (collapsed || narrow);
  useEffect(() => { capsReady.then(() => setReady(true)); }, []);

  const toast = useCallback((text, tone = 'ok') => {
    const key = Math.random();
    setToasts((t) => [...t, { key, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.key !== key)), 4000);
  }, []);
  useEffect(() => { window.scrollTo(0, 0); }, [section, id]);

  if (section === 'open-api' || isDocsPath()) {
    return <Suspense fallback={<p className="state">Загружаем документацию API…</p>}><ApiDocs /></Suspense>;
  }

  const page = !ready ? <p className="state">Подключаемся к серверу…</p>
    : section === 'patients' && id ? <PatientCard key={id} id={id} />
    : section === 'inbox' ? <Patients key="inbox" preset="inbox" />
    : ['archive', 'settings'].includes(section) ? <p className="state" role="status">Раздел пока недоступен</p> : <Findings />;
  const current = section === 'patients' ? 'findings' : section;   // карточка открывается из «Находок»

  return (
    <Toast.Provider value={toast}>
      <Revision.Provider value={rev}>
        <div className={`layout${isCollapsed ? ' collapsed' : ''}${section === 'patients' ? ' patient-view' : ''}`}>
          <header className="mobile-top"><Logo height={22} /></header>
          <aside className="sidebar">
            <a className="brand" href="#/findings" aria-label="СМ-Клиника, на главную"><Logo /></a>
            <nav className="nav" aria-label="Разделы">
              {section === 'patients' && <button className="nav-item dashboard-stub" disabled title="Дашборд — заглушка"><Grid size={16} /><span>Дашборд</span></button>}
              {NAV.map(([key, label, Icon]) => ['archive', 'settings'].includes(key) ? (
                <button key={key} className="nav-item" disabled title={`${label} — заглушка`}><Icon size={16} /><span>{label}</span></button>
              ) : (
                <a key={key} href={`#/${key}`} className="nav-item" aria-current={current === key ? 'page' : undefined} title={label}>
                  <Icon size={16} /><span>{label}</span>
                </a>
              ))}
            </nav>
            <div className="nav-bottom">
              <span className="nav-user" title={DOCTOR_DISPLAY_NAME}>
                <span className="nav-avatar" aria-hidden="true" />
                <span className="nav-user-text"><span>{DOCTOR_DISPLAY_NAME}</span><small>Врач</small></span>
              </span>
              {!narrow && <button className="nav-item faint" onClick={() => setCollapsed((v) => !v)} aria-expanded={!collapsed} title={collapsed ? 'Развернуть' : 'Свернуть'}>
                <ArrowLeft size={16} className={collapsed ? 'flip' : undefined} /><span>Свернуть</span>
              </button>}
            </div>
          </aside>
          <main className="main">{page}</main>
        </div>
        {USE_MOCK && <DemoPanel onChange={() => setRev((r) => r + 1)} toast={toast} />}
        <div className="toasts" role="status">{toasts.map((t) => <div key={t.key} className={`toast ${t.tone}`}>{t.text}</div>)}</div>
      </Revision.Provider>
    </Toast.Provider>
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
          <p><b>Автономная демонстрация.</b> Вымышленные данные и условные правила. Изменения живут до перезагрузки и не отправляются в систему.</p>
          <p className="demo-time">Модельное время: <b>{fmtDateTime(demo.now())}</b></p>
          <div className="demo-steps">{STEPS.map(([h, l]) => <button key={h} className="chip" onClick={() => { demo.advance(h); update(); }}>{l}</button>)}</div>
          <button className="btn-main" disabled={!demo.queueLeft()} onClick={receive}>Поступил протокол из МИС ({demo.queueLeft()})</button>
        </div>
      )}
      <button className="demo-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open}>{open ? 'Скрыть' : 'Демо'}</button>
    </div>
  );
}
