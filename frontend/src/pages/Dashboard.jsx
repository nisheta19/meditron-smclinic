// «Дашборд» по макету Figma (кадр «MacBook Air - 18»): карта сети клиник, результативность уведомлений,
// «Доходят до конца» и четыре показателя за период.
// Всегда статичная демо-страница: одинакова с заглушками и с реальным backend (флаг мока не влияет).
// Фильтры (город, период, пол, возраст, патология, срочность) пересчитывают демо-цифры на месте —
// без перезагрузки и пересоздания блоков: числа плавно «докручиваются», полоски меняют длину.
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import { nWord } from '../lib/format';
import { go, useAsync } from '../lib/hooks';
import { EMPTY_FILTERS, activeCount } from '../lib/patientFilters';
import { ArrowLeft, Bell, Link2, Loader, Smile } from '../components/Icons';
import { SearchBar } from '../components/kit';
import PatientFilters from '../components/PatientFilters';
import Dropdown from '../components/Dropdown';
import { MAP_COLORS, MAP_DOTS, MAP_SIZE, WAVE } from '../components/dashboard/art';

const CITIES = { msk: 'Москва' };
const PERIODS = { week: 'За неделю', month: 'За месяц', all: 'За всё время' };
const DELTA = { week: 'за неделю', month: 'за месяц' };
// Базовые значения: «За неделю» — из макета; остальные периоды — того же порядка
const BASE = {
  week: { reach: 67, done: 1367, of: 2067, came: 57, viaLink: 67, opened: 78, pushes: 1.2, deltas: [-15, 10, 10, -21], funnel: [67, 42, 78] },
  month: { reach: 64, done: 5480, of: 8563, came: 61, viaLink: 63, opened: 74, pushes: 1.4, deltas: [4, -2, 3, 8], funnel: [64, 45, 71] },
  all: { reach: 62, done: 21904, of: 35329, came: 59, viaLink: 60, opened: 72, pushes: 1.5, deltas: null, funnel: [61, 44, 69] },
};
// Доля пациентов в выборке для демо-пересчёта счётчиков
const SHARE = { sex: { F: 0.58, M: 0.42 }, urgency: { urgent: 0.04, soon: 0.21, planned: 0.75 },
  age: { minor: 0.03, early: 0.08, young: 0.31, middle: 0.29, elderly: 0.21, senile: 0.07, late: 0.01 } };

/** Детерминированный «шум» от набора фильтров: одни и те же фильтры — одни и те же цифры */
function seed(str) {
  let h = 2166136261;
  for (const ch of str) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return (k) => ((Math.imul(h ^ (k * 2654435761), 1597334677) >>> 0) % 1000) / 1000;
}
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

function compute(period, f) {
  const b = BASE[period];
  const key = JSON.stringify(f);
  if (key === JSON.stringify(EMPTY_FILTERS)) return { ...b };
  const r = seed(key);
  const shift = (v, k, spread = 12) => Math.round(clamp(v + (r(k) - 0.5) * 2 * spread, 8, 97));
  const share = (SHARE.sex[f.sex] ?? 1) * (SHARE.age[f.age] ?? 1) * (SHARE.urgency[f.urgency] ?? 1) * (f.pathology ? 0.04 + r(9) * 0.12 : 1);
  const of = Math.max(3, Math.round(b.of * share));
  const reach = shift(b.reach, 1);
  return {
    reach, of, done: Math.round((of * reach) / 100),
    came: shift(b.came, 2), viaLink: shift(b.viaLink, 3), opened: shift(b.opened, 4),
    pushes: Math.round(clamp(b.pushes + (r(5) - 0.5) * 0.8, 1, 3) * 10) / 10,
    deltas: b.deltas && b.deltas.map((d, i) => Math.round(d + (r(10 + i) - 0.5) * 10)),
    funnel: b.funnel.map((v, i) => shift(v, 20 + i, 10)),
  };
}

/** Плавное изменение числа (без пересоздания элемента) */
function useTween(target, ms = 600) {
  const [v, setV] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const start = performance.now(), a = from.current;
    if (a === target) return undefined;
    let raf;
    const step = (t) => {
      const k = Math.min(1, (t - start) / ms), e = 1 - (1 - k) ** 3;
      const cur = a + (target - a) * e;
      from.current = cur; setV(cur);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}
const Num = ({ value, digits = 0, suffix = '' }) => <>{useTween(value).toFixed(digits)}{suffix}</>;

export default function Dashboard() {
  const [city, setCity] = useState('msk');
  const [period, setPeriod] = useState('week');
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const dict = useAsync(() => api.dictionary().catch(() => []), []);
  const pathologies = (dict.data ?? []).filter((d) => d.active !== false).map((d) => [d.code, d.name]).sort((a, b) => a[1].localeCompare(b[1], 'ru'));
  const d = useMemo(() => compute(period, filters), [period, filters]);
  const delta = (i) => (d.deltas ? `${d.deltas[i] > 0 ? '+' : ''}${d.deltas[i]}% ${DELTA[period]}` : null);

  return (
    <>
      <SearchBar value="" onSearch={(q) => q && go(`findings?q=${encodeURIComponent(q)}`)} placeholder="Поиск"
        filtersActive={activeCount(filters)} onReset={() => setFilters(EMPTY_FILTERS)}
        filters={<PatientFilters value={filters} onChange={setFilters} pathologies={pathologies} />} />
      <div className="dash-controls">
        <Dropdown compact ariaLabel="Город" value={city} onChange={setCity} options={CITIES} />
        <Dropdown compact ariaLabel="Период" value={period} onChange={setPeriod} options={PERIODS} />
      </div>

      {/* Одна сетка 3 колонки × 3 ряда: «Результативность уведомлений» стоит в одном ряду с «Открыли уведомление» и «Пуши» */}
      <div className="dash">
        <section className="dash-card dash-map">
          <h2>Карта сети клиник</h2>
          <GoButton to="archive" label="Открыть картотеку" />
          <ClinicMap />
        </section>

        <section className="dash-card dash-hero">
          <h2>Доходят до конца</h2>
          <p><Num value={d.done} /> из <Num value={d.of} /> {nWord(d.of, ['пациента', 'пациентов', 'пациентов']).split(' ')[1]}</p>
          <strong><Num value={d.reach} suffix="%" /></strong>
          <svg className="dash-wave" viewBox={`0 0 ${WAVE.w} ${WAVE.h}`} preserveAspectRatio="none" aria-hidden="true">
            <path d={WAVE.fill} fill="#5ac4a3" />
            <path d={WAVE.stroke} fill="none" stroke="#b0e7d5" strokeWidth="10" strokeLinecap="round" />
          </svg>
        </section>

        <Metric icon={Smile} title="Пришли на консультацию" value={d.came} delta={delta(0)} tone="orange" />
        <Metric icon={Link2} title="Записались через ссылку СМ-клиники" value={d.viaLink} delta={delta(1)} tone="green" />

        <section className="dash-card dash-funnel">
          <h2>Результативность уведомлений</h2>
          <div className="funnel-bars">
            {d.funnel.map((value, i) => (
              <div key={i} className="funnel-row">
                <div className="funnel-bar" style={{ width: `max(${value}%, 200px)` }}>
                  <span>{nWord(i + 1, ['уведомление', 'уведомления', 'уведомлений'])}</span>
                  <b className={`funnel-pct c${i}`}><Num value={value} suffix="%" /></b>
                </div>
              </div>
            ))}
          </div>
          <div className="funnel-axis"><span>0%</span><span>50%</span><span>100%</span></div>
        </section>

        <Metric icon={Loader} title="Открыли уведомление" value={d.opened} delta={delta(2)} tone="green" />
        <Metric icon={Bell} title="Пуши на пациента" value={d.pushes} digits={1} unit="" delta={delta(3)} tone="orange" />
      </div>
    </>
  );
}

function Metric({ icon: Icon, title, value, digits = 0, unit = '%', delta, tone }) {
  return (
    <section className="dash-card dash-metric">
      <Icon size={24} className="dash-icon" />
      <GoButton to="findings" label={`Подробнее: ${title}`} />
      <h3>{title}</h3>
      <strong className={tone}><Num value={value} digits={digits} suffix={unit} /></strong>
      {delta && <span className="dash-delta">{delta}</span>}
    </section>
  );
}

const GoButton = ({ to, label }) => (
  <button className="dash-go" aria-label={label} title={label} onClick={() => go(to)}><ArrowLeft size={22} /></button>
);

/** Точечная карта из макета: серые точки — город; клиники — «соты» из 7 цветных точек.
    Наведение подсвечивает одну клинику целиком (все 7 точек), а не отдельную точку и не всю карту. */
function ClinicMap() {
  const { city, clinics } = useMemo(() => {
    const dots = MAP_DOTS.split(';').flatMap((row) => {
      const [y, xs] = row.split('|');
      return xs.split(',').map((v) => { const [x, c = 0] = v.split(':'); return [+x, +y, +c]; });
    });
    // Соты = связные группы цветных точек одного цвета (соседи ближе 9 px)
    const col = dots.filter((p) => p[2]);
    const parent = col.map((_, i) => i);
    const root = (i) => (parent[i] === i ? i : (parent[i] = root(parent[i])));
    col.forEach((a, i) => col.forEach((b, j) => {
      if (j > i && a[2] === b[2] && Math.hypot(a[0] - b[0], a[1] - b[1]) < 9) parent[root(i)] = root(j);
    }));
    const groups = {};
    col.forEach((p, i) => (groups[root(i)] ??= []).push(p));
    const list = Object.values(groups).map((pts) => ({
      pts, color: pts[0][2],
      cx: pts.reduce((n, p) => n + p[0], 0) / pts.length, cy: pts.reduce((n, p) => n + p[1], 0) / pts.length,
    })).sort((a, b) => a.cy - b.cy || a.cx - b.cx);
    return { city: dots.filter((p) => p[2] === 0), clinics: list };
  }, []);

  return (
    <svg className="dash-mapsvg" viewBox={`0 0 ${MAP_SIZE.w} ${MAP_SIZE.h}`} role="img" aria-label="Карта клиник сети, Москва">
      <g fill={MAP_COLORS[0]} pointerEvents="none">
        {city.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="2" />)}
      </g>
      {clinics.map((c, i) => (
        <g key={i} className="clinic" fill={MAP_COLORS[c.color]} style={{ transformOrigin: `${c.cx}px ${c.cy}px` }}>
          <title>Клиника {i + 1}</title>
          <circle className="clinic-hit" cx={c.cx} cy={c.cy} r="11" />{/* зона наведения на всю «соту» */}
          {c.pts.map(([x, y], j) => <circle key={j} cx={x} cy={y} r="2" />)}
        </g>
      ))}
    </svg>
  );
}
