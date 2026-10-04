// Точка входа: компоненты импортируют только `api` и не знают, мок это или backend.
import { httpApi, USE_MOCK } from './client';
import { mockApi } from './mock/server';

export { ApiError, USE_MOCK, API_URL } from './client';
export { demo } from './mock/server';

export const api = USE_MOCK ? mockApi : httpApi;

/**
 * Что умеет подключённый backend. Маршруты и уведомления проверяем безопасным GET /api/route-templates:
 * если путь не реализован, интерфейс работает с находками без маршрутов (см. README, «Подключение к backend»).
 */
export const caps = { routes: true, notifications: true, dictionaryWrite: true };
export const capsReady = USE_MOCK ? Promise.resolve(caps) : httpApi.routeTemplates().then(() => caps, (e) => {
  if (e.notImplemented) Object.assign(caps, { routes: false, notifications: false });
  return caps;
});

if (import.meta.env.DEV) {
  const missing = Object.keys(httpApi).filter((k) => !mockApi[k]);
  if (missing.length) console.warn('Мок не реализует эндпоинты:', missing);
}
