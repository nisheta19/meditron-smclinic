import { NOT_TRIGGERED } from '../lib/format';
import { markedSegments } from '../lib/evidence';

/** Текст протокола с подсветкой цитат-доказательств: находки — цветом статуса, «не сработало» — пунктиром */
export default function ProtocolText({ text, findings, notTriggered, names }) {
  if (!text) return <p className="muted">Полный текст протокола не передан сервисом распознавания.</p>;
  const marks = [
    ...findings.map((f) => ({ evidence: f.evidence, id: `ev-${f.id}`, cls: f.status.toLowerCase(), title: f.name })),
    ...notTriggered.map((n, i) => ({ evidence: n.evidence, id: `nt-${i}`, cls: 'nt', title: `${n.name ?? names[n.code] ?? n.code}: ${NOT_TRIGGERED[n.reason] ?? n.reason}` })),
  ];
  return <div className="protocol-text">{markedSegments(text, marks).map((segment) => segment.marks.length
    ? <mark key={segment.start} data-evidence-ids={segment.marks.map((m) => m.id).join(' ')} className={`ev ${segment.marks[0].cls}`}
        title={segment.marks.map((m) => m.title).join('; ')}>{segment.text}</mark>
    : segment.text)}</div>;
}

export const focusEvidence = (id) => {
  const el = [...document.querySelectorAll('[data-evidence-ids]')].find((node) => node.dataset.evidenceIds.split(' ').includes(id));
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
};
