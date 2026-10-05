import assert from 'node:assert/strict';

/** Authenticate a real browser context, using its shared cookie jar. */
export async function signIn(context, base) {
  const token = await context.request.get(`${base}/api/auth/csrf`);
  assert.equal(token.status(), 200);
  const { token: csrf, headerName } = await token.json();
  const response = await context.request.post(`${base}/api/auth/login`, {
    headers: { [headerName]: csrf },
    data: { login: process.env.AUTH_LOGIN || '123', password: process.env.AUTH_PASSWORD || '123' },
  });
  assert.equal(response.status(), 200);
}
