import test from 'node:test';
import assert from 'node:assert/strict';
globalThis.location = { search: '' };
const { loginAccount, currentAccount, logoutAccount } = await import('../src/api/auth.js');
const { httpApi } = await import('../src/api/client.js');

test('login uses cookie session and CSRF, then refreshes the token before a doctor action', async () => {
  let token = 0;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    assert.equal(options.credentials, 'include');
    if (url.endsWith('/csrf')) return Response.json({ headerName: 'X-CSRF-TOKEN', token: `token-${++token}` });
    if (url.endsWith('/login')) {
      assert.equal(options.headers['X-CSRF-TOKEN'], 'token-1');
      assert.deepEqual(JSON.parse(options.body), { login: '123', password: '123' });
      return Response.json({ login: '123', roles: ['DOCTOR'] });
    }
    assert.equal(options.headers['X-CSRF-TOKEN'], 'token-2');
    return new Response(null, { status: 204 });
  };
  await loginAccount('123', '123');
  await httpApi.removeFinding('fake-finding');
  assert.deepEqual(calls.map(call => call.url), ['/api/auth/csrf', '/api/auth/login', '/api/auth/csrf', '/api/findings/fake-finding']);
});

test('failed login and expired session do not authenticate the client', async () => {
  globalThis.fetch = async () => Response.json({ code: 'INVALID_CREDENTIALS' }, { status: 401 });
  await assert.rejects(loginAccount('wrong', 'wrong'), { status: 401 });
  await assert.rejects(currentAccount(), { status: 401 });
  let expired = false;
  globalThis.window = { dispatchEvent: event => { expired = event.type === 'auth-expired'; } };
  await assert.rejects(httpApi.patients(), { status: 401 });
  assert.equal(expired, true);
});

test('logout posts with a fresh CSRF and cookies, accepts 204, and clears the cached token', async () => {
  let count = 0;
  globalThis.fetch = async (url, options) => {
    assert.equal(options.credentials, 'include');
    if (url.endsWith('/csrf')) return Response.json({ headerName: 'X-CSRF-TOKEN', token: `logout-${++count}` });
    assert.ok(url.endsWith('/logout'));
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['X-CSRF-TOKEN'], `logout-${count}`);
    return new Response(null, { status: 204 });
  };
  await logoutAccount(); await logoutAccount();
  assert.equal(count, 2);
});

test('logout treats 401 as an expired session but does not conceal network failures', async () => {
  globalThis.fetch = async url => url.endsWith('/csrf')
    ? Response.json({ headerName: 'X-CSRF-TOKEN', token: 'logout-test' })
    : Response.json({ code: 'UNAUTHORIZED' }, { status: 401 });
  await logoutAccount();
  globalThis.fetch = async () => { throw new Error('offline'); };
  await assert.rejects(logoutAccount(), { code: 'NETWORK' });
});
