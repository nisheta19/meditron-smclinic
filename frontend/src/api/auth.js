import { API_URL, ApiError } from './client.js';

let csrf;
export const clearCsrf = () => { csrf = undefined; };
async function authRequest(path, options = {}) {
  const response = await fetch(`${API_URL}/api/auth/${path}`, {
    credentials: 'include', signal: AbortSignal.timeout(20000), ...options,
  }).catch(() => { throw new ApiError(0, 'NETWORK', 'Сервер недоступен'); });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data?.code, data?.message);
  if (!data) throw new ApiError(response.status, 'INVALID_RESPONSE', 'Неверный ответ сервера');
  return data;
}

export async function csrfHeaders() {
  csrf ??= authRequest('csrf').catch(error => { csrf = undefined; throw error; });
  const { headerName, token } = await csrf;
  return { [headerName]: token };
}

export const currentAccount = () => authRequest('me').catch(error => {
  if (error.status === 401) clearCsrf();
  throw error;
});
export async function loginAccount(login, password) {
  const headers = await csrfHeaders();
  try {
    return await authRequest('login', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify({ login, password }),
    });
  } finally {
    // Spring rotates the session and CSRF token after authentication.
    csrf = undefined;
  }
}

export async function logoutAccount() {
  // Fetch a fresh token: a long-open tab may hold a token from an older session.
  clearCsrf();
  try {
    return await authRequest('logout', { method: 'POST', headers: await csrfHeaders() });
  } catch (error) {
    if (error.status !== 401) throw error;
  } finally { clearCsrf(); }
}
