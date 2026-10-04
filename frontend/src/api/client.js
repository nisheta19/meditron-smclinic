// HTTP-клиент по контракту openapi.yaml (v0.2.0). Каждая функция = один эндпоинт.

const env = import.meta.env ?? {};
const override = new URLSearchParams(location.search).get('mock'); // ?mock=1 / ?mock=0

/** Заглушки включаются только явно; рабочий режим всегда обращается к backend. */
export const USE_MOCK = override != null ? override === '1' : env.VITE_USE_MOCK === 'true';
export const API_URL = (env.VITE_API_URL ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message || code || `Ошибка ${status}`);
    Object.assign(this, { status, code });
  }
  /** 404/405 без кода ошибки из контракта — эндпоинт ещё не реализован на сервере */
  get notImplemented() { return [404, 405].includes(this.status) && !this.code; }
}

async function request(method, path, { query, body } = {}) {
  const qs = new URLSearchParams(Object.entries(query ?? {}).filter(([, v]) => v !== undefined && v !== '' && v !== null));
  const res = await fetch(`${API_URL}${path}${qs.size ? `?${qs}` : ''}`, {
    method,
    signal: AbortSignal.timeout(20000),
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  }).catch(() => { throw new ApiError(0, 'NETWORK', `Сервер ${API_URL} недоступен`); });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    // Ошибки контракта приходят как { code, message }; для нереализованных путей Spring отдаёт свой формат без code
    const missing = [404, 405].includes(res.status) && !data?.code;
    throw new ApiError(res.status, data?.code, missing ? `Сервер пока не поддерживает ${method} ${path}` : data?.message);
  }
  if (data == null) throw new ApiError(res.status, 'INVALID_RESPONSE', 'Сервер вернул ответ в неверном формате');
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
