import test from 'node:test';
import assert from 'node:assert/strict';
globalThis.location = { search: '' };
const { httpApi, USE_MOCK, API_URL } = await import('../src/api/client.js');

test('real backend and same-origin requests are the defaults', () => {
  assert.equal(USE_MOCK, false);
  assert.equal(API_URL, '');
});
test('nested patient and protocol DTOs preserve fields and flags', async () => {
  globalThis.fetch = async (url) => new Response(JSON.stringify(url.includes('/patients/')
    ? { patient: { id: 'p', maxLevel: 'EMERGENCY' }, currentProtocol: { id: 'r' }, history: { protocols: [] } }
    : { protocol: { id: 'r', status: 'DONE', conclusionFound: false, flags: [{ code: 'NO_CONCLUSION' }] }, text: 'Описание', notTriggered: [] }),
  { headers: { 'Content-Type': 'application/json' } });
  assert.equal((await httpApi.patient('p')).maxLevel, 'EMERGENCY');
  const protocol = await httpApi.protocol('r');
  assert.equal(protocol.conclusionFound, false);
  assert.equal(protocol.flags[0].code, 'NO_CONCLUSION');
  assert.equal(protocol.text, 'Описание');
});
test('HTML with a successful HTTP status is not silently treated as an empty patient list', async () => {
  globalThis.fetch = async () => new Response('<html>wrong proxy</html>');
  await assert.rejects(httpApi.patients(), { code: 'INVALID_RESPONSE' });
});
test('doctor actions preserve backend validation messages', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ code: 'PROTOCOL_INACTIVE', message: 'Протокол аннулирован' }), { status: 400 });
  await assert.rejects(httpApi.updateFinding('f', { status: 'CONFIRMED' }), { code: 'PROTOCOL_INACTIVE', message: 'Протокол аннулирован' });
});
test('deletion accepts an empty 204 response', async () => {
  globalThis.fetch = async () => new Response(null, { status: 204 });
  assert.equal(await httpApi.removeFinding('f'), null);
});
