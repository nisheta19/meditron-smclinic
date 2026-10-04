// Компоненты по макету Figma: чекбокс, строка поиска, чипы, список карточек-строк
import { useEffect, useState } from 'react';
import { ArrowDown, Check, Search, Sliders } from './Icons';
import Dropdown from './Dropdown';

export function Checkbox({ checked, mixed, onChange, label, size = 'row' }) {
  return (
    <button type="button" role="checkbox" aria-checked={mixed ? 'mixed' : !!checked} aria-label={label}
      className={`cbx ${size}`} onClick={(e) => { e.stopPropagation(); onChange(!checked); }}>
      {checked && <Check size={16} />}
      {mixed && !checked && <i className="cbx-dash" />}
    </button>
  );
}

/** Белая плашка поиска: поле, кнопка фильтров (sliders) и «Найти». Поиск применяется по кнопке и Enter */
export function SearchBar({ value, onSearch, placeholder = 'Поиск', filters, filtersActive = 0, onReset, action }) {
  const [text, setText] = useState(value);
  const [open, setOpen] = useState(false);
  useEffect(() => setText(value), [value]);
  return (
    <div className={`searchbar-wrap${filters && open ? ' open' : ''}`}>
      <form className="searchbar" role="search" onSubmit={(e) => { e.preventDefault(); onSearch(text.trim()); }}>
        <input type="search" value={text} placeholder={placeholder} aria-label={placeholder}
          onChange={(e) => { setText(e.target.value); if (!e.target.value) onSearch(''); }} />
        {action}
        {filters && (
          <button type="button" className={`icon-btn${open ? ' on' : ''}`} aria-expanded={open} aria-label="Фильтры" onClick={() => setOpen((v) => !v)}>
            <Sliders size={20} />{filtersActive > 0 && <span className="dot">{filtersActive}</span>}
          </button>
        )}
        <button type="submit" className="btn-main">Найти<Search size={12} /></button>
      </form>
      {filters && (
        // Панель всегда в DOM: высота раскрывается через grid-template-rows 0fr → 1fr, поля появляются лесенкой
        <div className="filter-collapse" data-open={open} inert={!open}>
          <div className="filter-clip">
            <div className="filter-panel">
              {filters}
              {onReset && filtersActive > 0 && <button type="button" className="link reset" onClick={onReset}>Сбросить фильтры</button>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Ряд чипов «Название · число» + чекбокс «выбрать всех» слева */
export function ChipRow({ items, value, onChange, selectAll, extra }) {
  return (
    <div className="chip-row">
      {selectAll}
      <div className="chips" role="tablist">
        {items.map(({ key, label, count }) => (
          <button key={key} role="tab" aria-selected={value === key} className="chip" onClick={() => onChange(key)}>
            {label}{count != null && <span className="chip-count">{count}</span>}
          </button>
        ))}
      </div>
      {extra && <div className="chip-extra">{extra}</div>}
    </div>
  );
}

/**
 * Список карточек-строк с заголовками колонок.
 * cols: [{ key, label, sort?: (row) => value, cell: (row) => node, width }]
 */
export function RowList({ cols, rows, rowKey, sort, onSort, selection, onRow, empty, loading }) {
  // Ширины в долях (fr) по макету: на 1280 px совпадают с Figma, на широком экране тянутся на всю ширину
  const template = cols.map((c) => c.width ?? 'minmax(0, 1fr)').join(' ');
  return (
    <div className={`rowlist${selection ? '' : ' plain'}`} style={{ '--cols': template }}>
      <div className="rowlist-head" role="row">
        {cols.map((c) => {
          const active = sort.key === c.key;
          return c.sort ? (
            <button key={c.key} className={`col-head${active ? ' active' : ''}`} onClick={() => onSort(c.key)}
              aria-sort={active ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
              {c.label}<ArrowDown size={12} className={active && sort.dir > 0 ? 'asc' : undefined} />
            </button>
          ) : <span key={c.key} className="col-head">{c.label}</span>;
        })}
      </div>
      <div className="mobile-sort">
        <span>Сортировка</span>
        <Dropdown compact ariaLabel="Сортировка" value={sort.key} onChange={onSort}
          options={cols.filter((c) => c.sort).map((c) => [c.key, c.label])} />
        <button className="chip" onClick={() => onSort(sort.key)} aria-label="Направление сортировки">{sort.dir > 0 ? '↑' : '↓'}</button>
      </div>
      {rows.map((r) => {
        const id = rowKey(r);
        return (
          <article key={id} className="row-card" tabIndex={0} onClick={() => onRow?.(r)} onKeyDown={(e) => e.key === 'Enter' && onRow?.(r)}>
            {selection && <Checkbox checked={selection.sel.has(id)} onChange={() => selection.toggle(id)} label="Выбрать" />}
            {cols.map((c) => <div key={c.key} className={`cell cell-${c.key}`}>{c.cell(r)}</div>)}
          </article>
        );
      })}
      {!rows.length && <div className="row-empty">{loading ? 'Загружаем…' : empty}</div>}
    </div>
  );
}

/** Ячейка из 2–3 строк: основная 16px, вторая серая, третья светло-серая */
export const Stack = ({ main, sub, faint, warn }) => (
  <div className="stack">
    <span className={`s-main${warn ? ' warn' : ''}`}>{main}</span>
    {sub && <span className="s-sub">{sub}</span>}
    {faint && <span className="s-faint">{faint}</span>}
  </div>
);

/** Этап: название, «N% пройдено» и полоска. При 0% зелёной заливки нет */
export const Progress = ({ value, name }) => (
  <div className="progress">
    {name && <span className="p-name" title={name}>{name}</span>}
    <span className="s-cap">{value}% пройдено</span>
    <span className="bar" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      {value > 0 && <i style={{ width: `max(${value}%, 12px)` }} />}
    </span>
  </div>
);
