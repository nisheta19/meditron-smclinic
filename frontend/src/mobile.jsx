// Отдельная точка входа для статичного HTML мобильной страницы записи (без остального приложения)
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import MobileRecord from './pages/MobileRecord';

const id = location.pathname.match(/\/next-step\/([^/]+)/)?.[1] ?? location.hash.match(/next-step\/([^/?]+)/)?.[1] ?? 'demo';
createRoot(document.getElementById('root')).render(<StrictMode><MobileRecord id={decodeURIComponent(id)} /></StrictMode>);
