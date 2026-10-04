// Static visual from the supplied dashboard frame. No API, navigation or demo calculations.
import { Search, Sliders } from '../components/Icons';
import { MAP_COLORS, MAP_DOTS, MAP_SIZE, WAVE } from '../components/dashboard/art';
import './Dashboard.css';

const dots = MAP_DOTS.split(';').flatMap(row => {
  const [y, xs] = row.split('|');
  return xs.split(',').map(value => { const [x, color = 0] = value.split(':'); return { x, y, color }; });
});

const iconPaths = {
  smile: ['M22 12A10 10 0 1 1 2 12A10 10 0 1 1 22 12', 'M8 14S9.5 16 12 16S16 14 16 14', 'M9 9H9.01', 'M15 9H15.01'],
  link: ['M15 7H18A5 5 0 0 1 18 17H15M9 17H6A5 5 0 0 1 6 7H9', 'M8 12H16'],
  loader: ['M12 2V6', 'M12 18V22', 'M4.93 4.93L7.76 7.76', 'M16.24 16.24L19.07 19.07', 'M2 12H6', 'M18 12H22', 'M4.93 19.07L7.76 16.24', 'M16.24 7.76L19.07 4.93'],
  bell: ['M18 8A6 6 0 0 0 6 8C6 15 3 17 3 17H21S18 15 18 8', 'M13.73 21A2 2 0 0 1 10.27 21'],
};
function MetricIcon({ name }) {
  return <svg className={`dash-icon ${name}`} width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {iconPaths[name].map((d, i) => <path key={i} d={d} />)}
  </svg>;
}
const StubArrow = ({ label }) => <button type="button" className="dash-go" disabled aria-label={label} title="Заглушка">
  <svg width="44" height="44" viewBox="0 0 44 44" fill="none" stroke="#979797" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M17.065 26.381L26.139 17.306M17.064 17.306H26.139V26.381" />
  </svg>
</button>;
const StubSelect = ({ children, label }) => <button type="button" className="dash-select" disabled aria-label={label} title="Заглушка">
  <span>{children}</span><svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true"><path d="m4 7 6 6 6-6" /></svg>
</button>;
function Metric({ icon, title, value, delta, tone }) {
  return <section className="dash-card dash-metric">
    <MetricIcon name={icon} /><StubArrow label={`Подробнее: ${title}`} />
    <h3>{title}</h3><strong className={tone}>{value}</strong><span className="dash-delta">{delta}</span>
  </section>;
}

export default function Dashboard() {
  return <div className="dashboard" aria-label="Демонстрационный дашборд, статичные данные макета">
    <div className="searchbar" role="search">
      <input type="search" placeholder="Поиск" aria-label="Поиск — заглушка" disabled />
      <button type="button" className="icon-btn" disabled aria-label="Фильтры — заглушка"><Sliders size={20} /></button>
      <button type="button" className="btn-main" disabled>Найти<Search size={12} /></button>
    </div>
    <div className="dash-controls"><StubSelect label="Город — заглушка">Москва</StubSelect><StubSelect label="Период — заглушка">За неделю</StubSelect></div>
    <div className="dash">
      <section className="dash-card dash-map">
        <h2>Карта сети клиник</h2><StubArrow label="Карта сети клиник — заглушка" />
        <svg className="dash-mapsvg" viewBox={`0 0 ${MAP_SIZE.w} ${MAP_SIZE.h}`} role="img" aria-label="Карта сети клиник, Москва">
          {dots.map(({ x, y, color }, i) => <circle key={i} cx={x} cy={y} r="1.98" fill={MAP_COLORS[color]} />)}
        </svg>
      </section>
      <section className="dash-card dash-hero">
        <h2>Доходят до конца</h2><p>1367 из 2067 пациентов</p><strong>67%</strong>
        <svg className="dash-wave" viewBox={`0 0 ${WAVE.w} ${WAVE.h}`} preserveAspectRatio="none" aria-hidden="true">
          <path d={WAVE.fill} fill="#5ac4a3" /><path d={WAVE.stroke} fill="none" stroke="#b0e7d5" strokeWidth="10" strokeLinecap="round" />
        </svg>
      </section>
      <Metric icon="smile" title="Пришли на консультацию" value="57%" delta="-15% за неделю" tone="orange" />
      <Metric icon="link" title="Записались через ссылку СМ-клиники" value="67%" delta="+10% за неделю" tone="green" />
      <section className="dash-card dash-funnel">
        <h2>Результативность уведомлений</h2>
        <div className="funnel-bars">{[[67, 266], [42, 186], [78, 347]].map(([value, width], i) =>
          <div key={i} className="funnel-bar" style={{ width: `${width / 456 * 100}%` }}>
            <span>{i + 1} уведомление</span><b className={`funnel-pct c${i}`}>{value}%</b>
          </div>)}
        </div>
        <div className="funnel-axis"><span>0%</span><span>50%</span><span>100%</span></div>
      </section>
      <Metric icon="loader" title="Открыли уведомление" value="78%" delta="+10% за неделю" tone="green" />
      <Metric icon="bell" title="Пуши на пациента" value="1.2" delta="-21% за неделю" tone="orange" />
    </div>
  </div>;
}
