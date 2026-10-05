// HTTP-клиент по контракту docs/openapi.yaml (v0.4.0). Каждая функция = один эндпоинт.
// Авторизация backend: cookie-сессия (credentials: 'include') + CSRF-заголовок для изменяющих запросов.

const env = import.meta.env;
const override = new URLSearchParams(location.search).get('mock'); // ?mock=1 / ?mock=0

/** Флаг: заглушки и демо-данные вместо backend. По умолчанию включён, пока сервера нет. */
export const USE_MOCK = override != null ? override !== '0' : env.VITE_USE_MOCK !== 'false';
export const API_URL = (env.VITE_API_URL ?? 'http://localhost:8080').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message || code || `Ошибка ${status}`);
    Object.assign(this, { status, code });
  }
  /** 404/405 без кода ошибки из контракта — эндпоинт ещё не реализован на сервере */
  get notImplemented() { return [404, 405].includes(this.status) && !this.code; }
}

/** Событие «сессия истекла / нет входа» — App показывает страницу авторизации */
export const UNAUTHORIZED = 'sm-route:unauthorized';

// CSRF: GET /api/auth/csrf → { token, headerName }. После входа Spring выдаёт новый токен — перечитываем.
let csrf = null;
async function loadCsrf(force = false) {
  if (csrf && !force) return csrf;
  const res = await fetch(`${API_URL}/api/auth/csrf`, { credentials: 'include' }).catch(() => null);
  csrf = res?.ok ? await res.json().catch(() => null) : null;
  return csrf;
}

async function request(method, path, { query, body } = {}, retried = false) {
  const qs = new URLSearchParams(Object.entries(query ?? {}).filter(([, v]) => v !== undefined && v !== '' && v !== null && v !== false));
  const headers = {};
  if (body) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') { const t = await loadCsrf(); if (t?.token) headers[t.headerName || 'X-XSRF-TOKEN'] = t.token; }
  const res = await fetch(`${API_URL}${path}${qs.size ? `?${qs}` : ''}`, {
    method, credentials: 'include', headers, body: body ? JSON.stringify(body) : undefined,
  }).catch(() => { throw new ApiError(0, 'NETWORK', `Сервер ${API_URL} недоступен`); });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    // 403 на изменяющем запросе — чаще всего устаревший CSRF-токен: обновляем и повторяем один раз
    if (res.status === 403 && method !== 'GET' && !retried) { await loadCsrf(true); return request(method, path, { query, body }, true); }
    if (res.status === 401 && !path.startsWith('/api/auth/')) dispatchEvent(new Event(UNAUTHORIZED));
    if (res.status === 401) throw new ApiError(401, 'UNAUTHORIZED', data?.message || 'Нужно войти в систему');
    // Ошибки контракта приходят как { code, message }; для нереализованных путей Spring отдаёт свой формат без code
    const missing = [404, 405].includes(res.status) && !data?.code;
    throw new ApiError(res.status, data?.code, missing ? `Сервер пока не поддерживает ${method} ${path}` : data?.message);
  }
  return data;
}

// ---------- Приведение ответов backend к виду из openapi.yaml ----------
// Backend отдаёт PatientCard как { patient: {...}, currentProtocol, ... } вместо allOf (плоских полей),
// а Protocol как { protocol: {...}, text, ... }. Разворачиваем; ответы по контракту проходят без изменений.
const flatCard = (d) => (d?.patient ? {
  ...d.patient, currentProtocol: d.currentProtocol ?? null, currentFindings: d.currentFindings ?? [], routes: d.routes ?? [],
  history: { protocols: [], findings: [], routes: [], ...d.history },
} : d);
const flatProtocol = (d) => (d?.protocol ? {
  ...d.protocol, patientId: d.patientId, text: d.text ?? null, modelVersion: d.modelVersion, error: d.error ?? null,
  findings: d.findings ?? [], notTriggered: d.notTriggered ?? [],
} : d);

const get = (p, query) => request('GET', p, { query });
const send = (method) => (p, body, query) => request(method, p, { body, query });
const [post, patch, put, del] = ['POST', 'PATCH', 'PUT', 'DELETE'].map(send);

export const httpApi = {
  // Авторизация (единственный тестовый аккаунт backend)
  login: async (body) => { await loadCsrf(true); const acc = await post('/api/auth/login', body); await loadCsrf(true); return acc; },
  me: () => get('/api/auth/me'),
  logout: async () => { await post('/api/auth/logout').catch(() => null); csrf = null; },
  // Пациенты и протоколы
  patients: (params) => get('/api/patients', params),
  patient: (id) => get(`/api/patients/${id}`).then(flatCard),
  protocol: (id) => get(`/api/protocols/${id}`).then(flatProtocol),
  // Находки
  findings: (patientId, status) => get(`/api/patients/${patientId}/findings`, { status }),
  addFinding: (patientId, body) => post(`/api/patients/${patientId}/findings`, body),
  confirmFindings: (patientId, body) => post(`/api/patients/${patientId}/findings/confirm`, body),
  updateFinding: (id, body) => patch(`/api/findings/${id}`, body),
  removeFinding: (id, reason) => del(`/api/findings/${id}`, undefined, { reason }),
  // Словарь
  dictionary: (params) => get('/api/dictionary/findings', params),
  createDictionaryEntry: (body) => post('/api/dictionary/findings', body),
  updateDictionaryEntry: (code, body) => put(`/api/dictionary/findings/${code}`, body),
  // Маршруты
  routeTemplates: () => get('/api/route-templates'),
  patientRoutes: (patientId) => get(`/api/patients/${patientId}/routes`),
  buildRoutes: (patientId, body) => post(`/api/patients/${patientId}/routes`, body),
  routes: (params) => get('/api/routes', params),
  route: (id) => get(`/api/routes/${id}`),
  cancelRoute: (id, reason) => del(`/api/routes/${id}`, undefined, { reason }),
  updateStep: (routeId, stepId, body) => patch(`/api/routes/${routeId}/steps/${stepId}`, body),
  // Уведомления
  notifications: (routeId) => get(`/api/routes/${routeId}/notifications`),
  notify: (routeId, body) => post(`/api/routes/${routeId}/notifications`, body),
};
