import test from 'node:test';
import assert from 'node:assert/strict';
import { evidenceRange, markedSegments } from '../src/lib/evidence.js';

test('Python offsets after an emoji select the exact quote', () => {
  assert.deepEqual(evidenceRange('🩺 Полип 8 мм.', { text: 'Полип', start: 2, end: 7 }), [3, 8]);
});
test('incorrect offsets fall back to the actual evidence, not unrelated text', () => {
  assert.deepEqual(evidenceRange('Текст: полип', { text: 'полип', start: 0, end: 5 }), [7, 12]);
});
test('missing evidence produces no highlight', () => {
  assert.equal(evidenceRange('Без патологии', { text: 'полип', start: 0, end: 5 }), null);
});
test('overlapping and duplicate findings keep all focus targets and all text', () => {
  const text = '🩺 полип эндометрия.';
  const marks = [{ id: 'one', evidence: { text: 'полип эндометрия' } },
    { id: 'two', evidence: { text: 'эндометрия' } }, { id: 'three', evidence: { text: 'полип эндометрия' } }];
  const segments = markedSegments(text, marks);
  assert.equal(segments.map((s) => s.text).join(''), text);
  assert.deepEqual(segments.find((s) => s.text === 'эндометрия').marks.map((m) => m.id), ['one', 'two', 'three']);
});
test('empty annotations preserve the complete original text', () => {
  assert.equal(markedSegments('Описание\n\nЗаключение', []).map((s) => s.text).join(''), 'Описание\n\nЗаключение');
});
