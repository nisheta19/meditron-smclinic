// Contract offsets count Unicode code points; JavaScript slice uses UTF-16 units.
export function evidenceRange(text, evidence) {
  if (!evidence?.text) return null;
  const points = Array.from(text);
  const { start, end } = evidence;
  if (Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start && end <= points.length
      && points.slice(start, end).join('') === evidence.text) {
    return [points.slice(0, start).join('').length, points.slice(0, end).join('').length];
  }
  const found = text.indexOf(evidence.text);
  return found < 0 ? null : [found, found + evidence.text.length];
}

export function markedSegments(text, marks) {
  const valid = marks.map((m) => ({ ...m, range: evidenceRange(text, m.evidence) })).filter((m) => m.range);
  const boundaries = [...new Set([0, text.length, ...valid.flatMap((m) => m.range)])].sort((a, b) => a - b);
  return boundaries.slice(0, -1).map((start, i) => {
    const end = boundaries[i + 1];
    return { start, end, text: text.slice(start, end), marks: valid.filter((m) => m.range[0] <= start && m.range[1] >= end) };
  });
}
