import { NOT_TRIGGERED } from '../lib/format';

/** Текст протокола с подсветкой цитат-доказательств: находки — цветом статуса, «не сработало» — пунктиром */
export default function ProtocolText({ text, findings, notTriggered, names }) {
  if (!text) return <p className="muted">Полный текст протокола не передан сервисом распознавания.</p>;
  const locate = (ev) => {
    if (!ev?.text) return null;
    const start = ev.start ?? text.indexOf(ev.text);
    return start < 0 ? null : [start, ev.end ?? start + ev.text.length];
  };
  const marks = [
    ...findings.map((f) => [locate(f.evidence), { id: `ev-${f.id}`, cls: f.status.toLowerCase(), title: `${f.name}: ${f.status === 'SUGGESTED' ? 'ждёт проверки' : 'проверена'}` }]),
    ...notTriggered.map((n, i) => [locate(n.evidence), { id: `nt-${i}`, cls: 'nt', title: `${n.name ?? names[n.code] ?? n.code}: ${NOT_TRIGGERED[n.reason] ?? n.reason}` }]),
  ].filter(([r]) => r).sort((a, b) => a[0][0] - b[0][0]);

  const out = [];
  let pos = 0;
  for (const [[s, e], m] of marks) {
    if (s < pos) continue; // пересечения не подсвечиваем дважды
    out.push(text.slice(pos, s), <mark key={m.id} id={m.id} className={`ev ${m.cls}`} title={m.title}>{text.slice(s, e)}</mark>);
    pos = e;
  }
  out.push(text.slice(pos));
  return <div className="protocol-text">{out}</div>;
}

export const focusEvidence = (id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
};
