// Сборка одной HTML-точки входа Vite в ОДИН самодостаточный файл: JS и CSS встраиваются внутрь,
// картинки — data: URI. Такой файл открывается двойным кликом и кладётся на любой статический хостинг.
import { build } from 'vite';
import { readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';

/** input — HTML-файл в корне frontend (index.html, next_step.html); возвращает готовый HTML строкой */
export async function buildSingleFile(input, { env = {} } = {}) {
  Object.assign(process.env, env);   // VITE_* из окружения Vite подхватывает при сборке
  const outDir = join('node_modules', '.single-file', input.replace(/\W/g, '_'));
  // base: './' — пути относительные, inlineDynamicImports: ленивые чанки (документация API) попадают в тот же файл
  await build({ base: './', logLevel: 'warn', build: { outDir, emptyOutDir: true, assetsInlineLimit: 1e8, cssCodeSplit: false, modulePreload: false,
    rollupOptions: { input, output: { inlineDynamicImports: true } } } });

  const read = (path) => readFile(join(outDir, path), 'utf8');
  let html = await read(input);
  for (const [tag, src] of html.matchAll(/<script[^>]*src="\.\/([^"]+)"[^>]*><\/script>/g)) {
    const js = (await read(src)).replace(/<\/script/gi, '<\\/script');
    html = html.replace(tag, () => `<script type="module">${js}</script>`);
  }
  for (const [tag, href] of html.matchAll(/<link[^>]*rel="stylesheet"[^>]*href="\.\/([^"]+)"[^>]*>/g)) {
    const css = await read(href);
    html = html.replace(tag, () => `<style>${css}</style>`);
  }
  await rm(outDir, { recursive: true, force: true });
  return html;
}
