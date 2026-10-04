import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { MARK_SVG } from './components/Icons';
import './styles.css';

// Favicon из кода: знак СМ-Клиники собирается в Blob, без внешних файлов
const icon = Object.assign(document.createElement('link'), {
  rel: 'icon', type: 'image/svg+xml', href: URL.createObjectURL(new Blob([MARK_SVG], { type: 'image/svg+xml' })),
});
document.head.append(icon);

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>);
