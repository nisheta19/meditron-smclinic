// Догрузка данных для строк списка. В TrackingItem и PatientShort (openapi v0.2.0) нет возраста,
// типа исследования, этапов маршрута и числа уведомлений — берём их из карточки пациента и истории уведомлений.
// Если backend добавит эти поля в списки, этот модуль можно убрать (см. README).
import { api } from '../api';
import { useAsync } from './hooks';

async function pool(items, fn, n = 6) {
  const out = [];
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) { const k = i++; out[k] = await fn(items[k]).catch(() => null); }
  }));
  return out;
}

/** Карточки пациентов по id: { [patientId]: PatientCard } */
export function useCards(ids) {
  const uniq = [...new Set(ids)].sort();
  return useAsync(async () => {
    const cards = await pool(uniq, (id) => api.patient(id));
    return Object.fromEntries(uniq.map((id, i) => [id, cards[i]]));
  }, [uniq.join(',')]);
}

/** Число уведомлений по маршрутам: { [routeId]: number } */
export function useNoteCounts(routeIds) {
  const uniq = [...new Set(routeIds)].sort();
  return useAsync(async () => {
    const lists = await pool(uniq, (id) => api.notifications(id));
    return Object.fromEntries(uniq.map((id, i) => [id, lists[i]?.length ?? 0]));
  }, [uniq.join(',')]);
}

/** Маршрут, его находка и протокол из карточки пациента */
export function routeInfo(card, routeId) {
  if (!card) return null;
  const route = [...card.routes, ...card.history.routes].find((r) => r.id === routeId);
  if (!route) return null;
  const finding = [...card.currentFindings, ...card.history.findings].find((f) => f.id === route.findingIds[0]);
  const protocol = [card.currentProtocol, ...card.history.protocols].find((p) => p && p.id === finding?.protocolId) ?? card.currentProtocol;
  const done = route.steps.filter((s) => ['COMPLETED', 'SKIPPED'].includes(s.status)).length;
  const step = route.steps.find((s) => s.id === route.currentStepId);
  return { route, finding, protocol, step, progress: Math.round((done / route.steps.length) * 100) };
}
