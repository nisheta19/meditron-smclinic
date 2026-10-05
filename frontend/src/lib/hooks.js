import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { cmp } from './format';

/** Счётчик ревизии: увеличивается при демо-действиях, все загрузки перезапрашиваются */
export const Revision = createContext(0);
export const Toast = createContext(() => {});
export const useToast = () => useContext(Toast);

/** Загрузка данных: { data, error, loading, reload } */
export function useAsync(fn, deps) {
  const rev = useContext(Revision);
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true }));
    fn().then((data) => live && setState({ data, error: null, loading: false }), (error) => live && setState((s) => ({ ...s, error, loading: false })));
    return () => { live = false; };
  }, [...deps, rev, tick]); // eslint-disable-line react-hooks/exhaustive-deps
  return { ...state, reload: useCallback(() => setTick((t) => t + 1), []) };
}

export function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

/**
 * Сортировка по колонке: cols = [{ key, get }]. initial — порядок по умолчанию; пока пользователь сам не нажал
 * на заголовок (touched = false), ни одна стрелка не подсвечивается
 */
export function useSort(rows, cols, initial) {
  const [sort, setSort] = useState({ ...initial, touched: false });
  const sorted = useMemo(() => {
    const col = cols.find((c) => c.key === sort.key);
    return col ? [...(rows ?? [])].sort((a, b) => cmp(col.get(a), col.get(b)) * sort.dir) : rows ?? [];
  }, [rows, cols, sort]);
  const toggle = (key) => setSort((s) => ({ key, dir: s.touched && s.key === key ? -s.dir : 1, touched: true }));
  return { sorted, sort, toggle };
}

export function useSelection() {
  const [sel, setSel] = useState(() => new Set());
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const setAll = (ids, on) => setSel((s) => { const n = new Set(s); ids.forEach((id) => (on ? n.add(id) : n.delete(id))); return n; });
  return { sel, toggle, setAll, clear: () => setSel(new Set()) };
}

/** Хэш-роутинг: #/patients/pat-0001 → ['patients', 'pat-0001'] */
export function useRoute() {
  const read = () => location.hash.replace(/^#\/?/, '').split('?')[0].split('/').filter(Boolean);
  const [parts, setParts] = useState(read);
  useEffect(() => { const h = () => setParts(read()); addEventListener('hashchange', h); return () => removeEventListener('hashchange', h); }, []);
  return parts;
}
export const go = (path) => { location.hash = `#/${path}`; };
/** Параметр из хэша: #/findings?q=… → hashParam('q') */
export const hashParam = (name) => new URLSearchParams(location.hash.split('?')[1] ?? '').get(name) ?? '';

/** Действие с тостом: run(() => api.x(), 'Готово'). При ошибке — тост; rethrow оставляет диалог открытым */
export function useAction() {
  const toast = useToast();
  return async (fn, ok, rethrow = false) => {
    try {
      const r = await fn();
      if (ok) toast(ok);
      return r;
    } catch (e) {
      toast(e.message, 'error');
      if (rethrow) throw e;
    }
  };
}

/** Совпадает ли медиазапрос (обновляется при изменении размера окна) */
export function useMedia(query) {
  const [match, setMatch] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const mq = matchMedia(query), h = () => setMatch(mq.matches);
    mq.addEventListener('change', h); h();
    return () => mq.removeEventListener('change', h);
  }, [query]);
  return match;
}
