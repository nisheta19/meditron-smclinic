function key(value) {
  const match = /^(?:до )?(\d{2})\.(\d{2})\.(\d{4})(?: · (\d{2}):(\d{2}))?$/.exec(String(value));
  return match ? `${match[3]}${match[2]}${match[1]}${match[4] ?? '00'}${match[5] ?? '00'}` : String(value);
}
export function sortRows(rows, sort) {
  if (!sort) return rows;
  return [...rows].sort((a,b) => {
    const av = a[sort.key], bv = b[sort.key];
    const missing = v => v == null || v === '' || v === '—';
    if (missing(av) || missing(bv)) return missing(av) === missing(bv) ? 0 : missing(av) ? 1 : -1;
    return key(av).localeCompare(key(bv),'ru',{numeric:true}) * sort.direction;
  });
}
