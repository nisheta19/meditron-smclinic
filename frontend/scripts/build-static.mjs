// Собирает приложение в ОДИН самодостаточный HTML-файл: dist/sm-route.html
// JS и CSS встраиваются внутрь, файл открывается двойным кликом без сервера.
// Offline presentation only: never send real patient data to this file.
import { build } from 'vite';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const OUT = 'dist';
// inlineDynamicImports: ленивые чанки (документация API) тоже попадают в один файл
await build({ define: { 'import.meta.env.VITE_USE_MOCK': JSON.stringify('true') }, build: { outDir: OUT, assetsInlineLimit: 1e8, cssCodeSplit: false, modulePreload: false,
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
