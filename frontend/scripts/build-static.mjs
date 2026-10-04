// Собирает приложение в ОДИН самодостаточный HTML-файл: dist/sm-route.html
// JS и CSS встраиваются внутрь, файл открывается двойным кликом без сервера.
// Запуск: npm run static   (с backend: VITE_API_URL=https://... npm run static)
import { build } from 'vite';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const OUT = 'dist';
// inlineDynamicImports: ленивые чанки (документация API) тоже попадают в один файл
await build({ build: { outDir: OUT, assetsInlineLimit: 1e8, cssCodeSplit: false, modulePreload: false,
  rollupOptions: { output: { inlineDynamicImports: true } } } });

const read = (path) => readFile(join(OUT, path), 'utf8');
let html = await read('index.html');

for (const [tag, src] of html.matchAll(/<script[^>]*src="\.\/([^"]+)"[^>]*><\/script>/g)) {
  const js = (await read(src)).replace(/<\/script/gi, '<\\/script');
  html = html.replace(tag, () => `<script type="module">${js}</script>`);
}
for (const [tag, href] of html.matchAll(/<link[^>]*rel="stylesheet"[^>]*href="\.\/([^"]+)"[^>]*>/g)) {
  const css = await read(href);
  html = html.replace(tag, () => `<style>${css}</style>`);
}

await writeFile(join(OUT, 'sm-route.html'), html);
console.log(`✓ ${OUT}/sm-route.html (${(html.length / 1024).toFixed(0)} КБ)`);
