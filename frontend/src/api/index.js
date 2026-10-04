// Точка входа: компоненты импортируют только `api` и не знают, мок это или backend.
import { httpApi, USE_MOCK } from './client';
import { mockApi } from './mock/server';

export { ApiError, USE_MOCK, API_URL } from './client';
export { demo } from './mock/server';

export const api = USE_MOCK ? mockApi : httpApi;

/**
 * Возможности текущего backend подтверждены его OpenAPI. Незавершённые функции
 * доступны только в явно выбранной автономной демонстрации.
 */
export const caps = { routes: USE_MOCK, notifications: USE_MOCK, dictionaryWrite: USE_MOCK };
export const capsReady = Promise.resolve(caps);

if (import.meta.env.DEV) {
  const missing = Object.keys(httpApi).filter((k) => !mockApi[k]);
  if (missing.length) console.warn('Мок не реализует эндпоинты:', missing);
}
