// Документация API по контракту docs/openapi.yaml. Открывается только по адресу /open-api (или #/open-api):
// из интерфейса платформы ссылок сюда нет намеренно.
import { Fragment, useMemo, useState } from 'react';
import { parse } from 'yaml';
import source from '../../docs/openapi.yaml?raw';
import { Chevron, Logo, Search } from '../components/Icons';

const METHODS = ['get', 'post', 'put', 'patch', 'delete'];
const IN = { path: 'путь', query: 'запрос', header: 'заголовок' };
const refName = (ref) => ref.split('/').pop();
const resolve = (spec, ref) => ref.replace(/^#\//, '').split('/').reduce((o, k) => o?.[k], spec);
const flash = (id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
};

export default function ApiDocs() {
  const spec = useMemo(() => parse(source), []);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(() => new Set());
  const yamlUrl = useMemo(() => URL.createObjectURL(new Blob([source], { type: 'text/yaml' })), []);

  const ops = useMemo(() => Object.entries(spec.paths).flatMap(([path, item]) => METHODS.filter((m) => item[m]).map((m) => ({
    ...item[m], method: m, path, id: `op-${m}-${path}`.replace(/[^\w-]/g, '_'),
    parameters: [...(item.parameters ?? []), ...(item[m].parameters ?? [])],
  }))), [spec]);
  const tags = spec.tags?.map((t) => t.name) ?? [...new Set(ops.flatMap((o) => o.tags ?? ['Прочее']))];
  const needle = q.trim().toLowerCase();
  const shown = ops.filter((o) => !needle || `${o.method} ${o.path} ${o.summary ?? ''} ${o.description ?? ''}`.toLowerCase().includes(needle));
  const schemas = Object.entries(spec.components?.schemas ?? {}).filter(([n]) => !needle || n.toLowerCase().includes(needle));

  const toggle = (id) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const reveal = (id) => { setOpen((s) => new Set(s).add(id)); requestAnimationFrame(() => flash(id)); };
  const ctx = { spec, onRef: (name) => flash(`schema-${name}`), deref: (x) => (x?.$ref ? resolve(spec, x.$ref) : x) };

  return (
    <div className="docs">
      <aside className="docs-nav">
        <div className="docs-brand"><Logo height={22} /><span>API</span></div>
        <label className="docs-search">
          <Search size={14} />
          <input type="search" placeholder="Поиск по методам и схемам" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <nav aria-label="Разделы API">
          {tags.map((tag) => {
            const list = shown.filter((o) => (o.tags ?? ['Прочее']).includes(tag));
            return list.length > 0 && (
              <Fragment key={tag}>
                <p className="docs-tag">{tag}</p>
                {list.map((o) => (
                  <button key={o.id} className="docs-link" onClick={() => reveal(o.id)}>
                    <Method m={o.method} /><span>{o.path.replace(/^\/api/, '')}</span>
                  </button>
                ))}
              </Fragment>
            );
          })}
          {schemas.length > 0 && <p className="docs-tag">Схемы</p>}
          {schemas.map(([name]) => <button key={name} className="docs-link schema" onClick={() => flash(`schema-${name}`)}>{name}</button>)}
        </nav>
      </aside>

      <main className="docs-main">
        <header className="docs-head">
          <h1>{spec.info.title}</h1>
          <p className="docs-meta">
            <span className="badge ok">v{spec.info.version}</span>
            <span>OpenAPI {spec.openapi}</span>
            {spec.servers?.map((s) => <code key={s.url}>{s.url}</code>)}
          </p>
          {spec.info.description && <p className="docs-desc">{spec.info.description.trim()}</p>}
          <div className="docs-actions">
            <button className="chip" onClick={() => setOpen(new Set(ops.map((o) => o.id)))}>Развернуть всё</button>
            <button className="chip" onClick={() => setOpen(new Set())}>Свернуть всё</button>
            <a className="chip" href={yamlUrl} download="openapi.yaml">Скачать openapi.yaml</a>
          </div>
        </header>

        {tags.map((tag) => {
          const list = shown.filter((o) => (o.tags ?? ['Прочее']).includes(tag));
          return list.length > 0 && (
            <section key={tag} className="docs-section">
              <h2>{tag}</h2>
              {list.map((o) => <Operation key={o.id} op={o} open={open.has(o.id)} onToggle={() => toggle(o.id)} ctx={ctx} />)}
            </section>
          );
        })}
        {!shown.length && !schemas.length && <p className="row-empty">Ничего не найдено по запросу «{q}».</p>}

        {schemas.length > 0 && (
          <section className="docs-section">
            <h2>Схемы</h2>
            {schemas.map(([name, s]) => (
              <article key={name} id={`schema-${name}`} className="docs-card">
                <h3><code>{name}</code></h3>
                {s.description && <p className="docs-desc">{s.description.trim()}</p>}
                <SchemaView schema={s} ctx={ctx} root />
              </article>
            ))}
          </section>
        )}
      </main>
    </div>
  );
}

const Method = ({ m }) => <span className={`method ${m}`}>{m.toUpperCase()}</span>;

function Operation({ op, open, onToggle, ctx }) {
  const params = op.parameters.map(ctx.deref);
  const body = op.requestBody && ctx.deref(op.requestBody);
  return (
    <article id={op.id} className={`docs-op ${op.method}${open ? ' open' : ''}`}>
      <button className="docs-op-head" aria-expanded={open} onClick={onToggle}>
        <Method m={op.method} /><code className="docs-path">{op.path}</code>
        <span className="docs-sum">{op.summary}</span><Chevron size={12} />
      </button>
      {open && (
        <div className="docs-op-body">
          {op.description && <p className="docs-desc">{op.description.trim()}</p>}
          {params.length > 0 && <>
            <h4>Параметры</h4>
            <div className="docs-table">
              {params.map((p) => (
                <div key={`${p.in}-${p.name}`} className="docs-row">
                  <span className="docs-name"><code>{p.name}</code>{p.required && <i title="Обязательный">*</i>}<small>{IN[p.in] ?? p.in}</small></span>
                  <span className="docs-type"><TypeLabel schema={p.schema} ctx={ctx} /></span>
                  <span className="docs-note">{p.description}<Extras schema={p.schema} /></span>
                </div>
              ))}
            </div>
          </>}
          {body && <>
            <h4>Тело запроса{body.required && <i className="docs-req"> обязательно</i>}</h4>
            {Object.entries(body.content ?? {}).map(([mime, c]) => (
              <div key={mime} className="docs-media"><small>{mime}</small><SchemaView schema={c.schema} ctx={ctx} /></div>
            ))}
          </>}
          <h4>Ответы</h4>
          {Object.entries(op.responses ?? {}).map(([code, r0]) => {
            const r = ctx.deref(r0);
            const schema = Object.values(r.content ?? {})[0]?.schema;
            return (
              <div key={code} className="docs-resp">
                <span className={`code c${code[0]}`}>{code}</span>
                <div>{r.description && <p>{r.description}</p>}{schema && <SchemaView schema={schema} ctx={ctx} />}</div>
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}

/** Тип одной строкой: string (date), массив Finding, ссылка на схему */
function TypeLabel({ schema: s, ctx }) {
  if (!s) return <span className="muted">любой</span>;
  if (s.$ref) { const n = refName(s.$ref); return <button className="docs-ref" onClick={() => ctx.onRef(n)}>{n}</button>; }
  if (s.type === 'array') return <>массив <TypeLabel schema={s.items} ctx={ctx} /></>;
  if (s.allOf) return <>{s.allOf.map((x, i) => <Fragment key={i}>{i > 0 && ' + '}<TypeLabel schema={x} ctx={ctx} /></Fragment>)}</>;
  const t = s.type ?? (s.properties ? 'object' : 'any');
  return <span className="docs-t">{t}{s.format && ` (${s.format})`}{s.nullable && ' | null'}{s.additionalProperties && ' (свободные поля)'}</span>;
}

const Extras = ({ schema: s }) => (s ? <>
  {s.enum && <span className="docs-enum">{s.enum.map((v) => <code key={String(v)}>{String(v)}</code>)}</span>}
  {s.default !== undefined && <small>по умолчанию: <code>{String(s.default)}</code></small>}
  {s.example !== undefined && <small>пример: <code>{String(s.example)}</code></small>}
  {(s.minimum !== undefined || s.maximum !== undefined) && <small>диапазон: {s.minimum ?? '−∞'}…{s.maximum ?? '∞'}</small>}
</> : null);

/** Схема: поля объекта таблицей (вложенные объекты — с отступом), остальное — тип и значения enum */
function SchemaView({ schema: s, ctx, root }) {
  if (!s) return null;
  if (s.$ref && !root) return <p className="docs-inline">Схема <TypeLabel schema={s} ctx={ctx} /></p>;
  if (s.allOf) return <>{s.allOf.map((x, i) => <SchemaView key={i} schema={x} ctx={ctx} />)}</>;
  if (s.type === 'array') return <div className="docs-inline">Массив элементов: <TypeLabel schema={s.items} ctx={ctx} />{s.items?.properties && <SchemaView schema={s.items} ctx={ctx} />}</div>;
  if (!s.properties) return <p className="docs-inline"><TypeLabel schema={s} ctx={ctx} /><Extras schema={s} /></p>;
  const required = new Set(s.required ?? []);
  return (
    <div className="docs-table">
      {Object.entries(s.properties).map(([name, p]) => (
        <Fragment key={name}>
          <div className="docs-row">
            <span className="docs-name"><code>{name}</code>{required.has(name) && <i title="Обязательное">*</i>}</span>
            <span className="docs-type"><TypeLabel schema={p} ctx={ctx} /></span>
            <span className="docs-note">{p.description?.trim()}<Extras schema={p.type === 'array' ? p.items : p} /></span>
          </div>
          {(p.properties || p.items?.properties) && <div className="docs-nested"><SchemaView schema={p.items?.properties ? p.items : p} ctx={ctx} /></div>}
        </Fragment>
      ))}
    </div>
  );
}
