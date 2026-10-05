// Собирает приложение в ОДИН самодостаточный HTML-файл: dist/sm-route.html
// JS и CSS встраиваются внутрь, файл открывается двойным кликом без сервера.
// Запуск: npm run static   (с backend: VITE_API_URL=https://... npm run static)
import { mkdir, writeFile } from 'node:fs/promises';
import { buildSingleFile } from './single-file.mjs';

const html = await buildSingleFile('index.html');
await mkdir('dist', { recursive: true });
await writeFile('dist/sm-route.html', html);
console.log(`✓ dist/sm-route.html (${(html.length / 1024).toFixed(0)} КБ)`);
