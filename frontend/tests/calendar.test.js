import test from 'node:test';
import assert from 'node:assert/strict';
import { calendarDate, displayDate, monthCells, monthFor, parseDate, toISO } from '../src/lib/calendar.js';

test('manual dates round-trip to the API without a timezone shift', () => {
  for (const iso of ['2026-09-07', '2024-02-29', '0001-01-01', '0099-12-31', '9999-12-31']) {
    assert.equal(parseDate(displayDate(iso)), iso);
    assert.equal(toISO(monthFor(iso)), `${iso.slice(0, 7)}-01`);
  }
});
test('invalid and incomplete input cannot become an API date', () => {
  for (const input of ['', '07.09.', '7.9.2026', '31.04.2026', '29.02.2026', '29.02.1900', '00.01.2026', '01.00.2026', '01.13.2026', '01.01.0000', 'abc', '2026-09-07']) assert.equal(parseDate(input), null, input);
  assert.equal(parseDate('29.02.2000'), '2000-02-29');
});
test('calendar weeks start on Monday and contain every day exactly once', () => {
  const february = monthCells(calendarDate(2024, 1));
  assert.deepEqual(february.slice(0, 4), [null, null, null, '2024-02-01']);
  assert.equal(february.filter(Boolean).length, 29);
  assert.equal(new Set(february.filter(Boolean)).size, 29);
  assert.equal(monthCells(calendarDate(2026, 2))[6], '2026-03-01');
});
test('month navigation crosses years and uses the correct month length', () => {
  assert.equal(toISO(calendarDate(2026, -1)), '2025-12-01');
  assert.equal(toISO(calendarDate(2026, 12)), '2027-01-01');
  assert.equal(monthCells(calendarDate(2026, 1)).filter(Boolean).length, 28);
  assert.equal(monthCells(calendarDate(2026, 0)).filter(Boolean).length, 31);
});
