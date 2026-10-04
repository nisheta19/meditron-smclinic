import test from 'node:test';
import assert from 'node:assert/strict';
import { fieldType, parseAttributes } from '../src/lib/findingFields.js';

const entry = { attributes: ['birads', 'side', 'inflammation', 'sizeMm'], rules: [
  { all: [{ attr: 'birads', gte: 4 }, { attr: 'inflammation', eq: true }] },
] };
test('manual BI-RADS is numeric; explicit false is retained', () => {
  assert.deepEqual(parseAttributes(entry, { birads: '4', side: 'right', inflammation: 'false' }),
    { birads: 4, side: 'right', inflammation: false });
});
test('blank and foreign attributes are omitted', () => {
  assert.deepEqual(parseAttributes(entry, { birads: '', sizeMm: ' ', category: 'BI-RADS 4', side: 'left' }), { side: 'left' });
});
test('invalid numbers and negative sizes cannot be submitted', () => {
  for (const sizeMm of ['NaN', 'Infinity', '-1', 'abc']) assert.throws(() => parseAttributes(entry, { sizeMm }));
});
test('new dictionary fields derive numeric and boolean types from new rules', () => {
  const newEntry = { attributes: ['score', 'newSign'], rules: [{ all: [{ attr: 'score', gt: 2 }, { attr: 'newSign', eq: false }] }] };
  assert.deepEqual(parseAttributes(newEntry, { score: '3.5', newSign: 'true' }), { score: 3.5, newSign: true });
});
test('types can also come from membership conditions and extraction notes', () => {
  assert.equal(fieldType({ rules: [{ all: [{ attr: 'grade', in: [1, 2] }] }] }, 'grade'), 'number');
  assert.equal(fieldType({ extraction: ['newSign=true: положительный признак'] }, 'newSign'), 'boolean');
});
test('unsupported boolean values fail validation', () => {
  assert.throws(() => parseAttributes(entry, { inflammation: 'maybe' }));
});
