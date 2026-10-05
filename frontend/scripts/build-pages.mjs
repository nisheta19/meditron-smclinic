// Статика для GitVerse Pages (Jekyll): собирает в папку pages/ два самодостаточных файла
//   main.html      — весь сайт (демо-режим, без backend; разделы — по хэшу #/findings, #/open-api, …)
//   next_step.html — мобильная страница записи пациента (мок, всегда демо-данные)
// Остальное в pages/ (_config.yml, index.md, _layouts, assets) — исходники Jekyll, их сборка не трогает.
// Запуск: npm run pages
import { writeFile } from 'node:fs/promises';
import { buildSingleFile } from './single-file.mjs';

const PAGES = [
  ['main.html', 'index.html', { VITE_USE_MOCK: 'true' }],
  ['next_step.html', 'next_step.html', {}],
];
for (const [out, input, env] of PAGES) {
  const html = await buildSingleFile(input, { env });
  await writeFile(`pages/${out}`, html);
  console.log(`✓ pages/${out} (${(html.length / 1024).toFixed(0)} КБ)`);
}
