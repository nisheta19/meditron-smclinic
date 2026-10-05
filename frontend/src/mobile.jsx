// Отдельная точка входа для статичного HTML мобильной страницы записи (без остального приложения)
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import MobileRecord from './pages/MobileRecord';
import { MARK_SVG } from './components/Icons';

const icon = Object.assign(document.createElement('link'), {
  rel: 'icon', type: 'image/svg+xml', href: URL.createObjectURL(new Blob([MARK_SVG], { type: 'image/svg+xml' })),
});
document.head.append(icon);

const id = location.pathname.match(/\/next-step\/([^/]+)/)?.[1] ?? location.hash.match(/next-step\/([^/?]+)/)?.[1] ?? 'demo';
createRoot(document.getElementById('root')).render(<StrictMode><MobileRecord id={decodeURIComponent(id)} /></StrictMode>);
