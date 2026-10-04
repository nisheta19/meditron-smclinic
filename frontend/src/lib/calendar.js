// Dates are calendar values, not instants; UTC arithmetic avoids DST shifts.
export function calendarDate(year, month, day = 1) {
  const date = new Date(0);
  date.setUTCFullYear(year, month, day);
  return date;
}

export function toISO(date) {
  return `${String(date.getUTCFullYear()).padStart(4, '0')}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
}

export function displayDate(value) {
  return value ? value.split('-').reverse().join('.') : '';
}

export function parseDate(text) {
  const match = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(text);
  if (!match) return null;
  const [, day, month, year] = match.map(Number);
  if (year < 1 || month < 1 || month > 12 || day < 1) return null;
  const date = calendarDate(year, month - 1, day);
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? toISO(date) : null;
}

export function monthFor(value) {
  if (value) return calendarDate(Number(value.slice(0, 4)), Number(value.slice(5, 7)) - 1);
  const today = new Date();
  return calendarDate(today.getFullYear(), today.getMonth());
}

export function monthCells(month) {
  const year = month.getUTCFullYear(), index = month.getUTCMonth();
  const offset = (month.getUTCDay() + 6) % 7;
  const count = calendarDate(year, index + 1, 0).getUTCDate();
  return Array.from({ length: 42 }, (_, i) => i >= offset && i < offset + count ? toISO(calendarDate(year, index, i - offset + 1)) : null);
}
