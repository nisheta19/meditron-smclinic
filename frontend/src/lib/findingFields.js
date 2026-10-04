const comparisonOps = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte'];

export function fieldType(entry, key) {
  for (const rule of entry.rules ?? []) for (const condition of rule.all ?? []) {
    if (condition.attr !== key) continue;
    const value = comparisonOps.map((op) => condition[op]).find((v) => v != null) ?? condition.in?.[0];
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') return 'number';
  }
  if (/(Mm|Ml|Cm3|Pct)$/.test(key) || ['birads', 'orads', 'tirads', 'figo', 'count'].includes(key)) return 'number';
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  if (new RegExp(`${escaped}\\s*=\\s*(true|false)`).test(JSON.stringify(entry.extraction ?? [])) || key === 'uncertain') return 'boolean';
  return 'text';
}

export function parseAttributes(entry, values) {
  const attributes = {};
  for (const key of entry.attributes ?? []) {
    const raw = values[key];
    if (raw == null || String(raw).trim() === '') continue;
    const type = fieldType(entry, key);
    if (type === 'number') {
      const value = Number(raw);
      if (!Number.isFinite(value) || value < 0) throw new Error('Введите неотрицательное число');
      attributes[key] = value;
    } else if (type === 'boolean') {
      if (!['true', 'false'].includes(String(raw))) throw new Error('Выберите «Да» или «Нет»');
      attributes[key] = String(raw) === 'true';
    } else attributes[key] = String(raw).trim();
  }
  return attributes;
}
