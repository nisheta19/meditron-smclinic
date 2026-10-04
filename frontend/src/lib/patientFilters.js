// Фильтры списков: пол, возрастная категория, патология (тип находки), срочность
export const SEX = { F: 'Женский', M: 'Мужской' };

// Границы включительно: 18 лет — уже «ранняя молодость», несовершеннолетние — до 17 лет
export const AGE_GROUPS = [
  ['minor', 'Несовершеннолетние, 0–17', 0, 17],
  ['early', 'Ранняя молодость, 18–24', 18, 24],
  ['young', 'Молодой возраст, 25–44', 25, 44],
  ['middle', 'Средний возраст, 45–59', 45, 59],
  ['elderly', 'Пожилой возраст, 60–74', 60, 74],
  ['senile', 'Старческий возраст, 75–89', 75, 89],
  ['late', 'Поздняя старость, 90+', 90, Infinity],
];
export const ageGroup = (age) => (age == null ? null : AGE_GROUPS.find(([, , a, b]) => age >= a && age <= b)?.[0]);

// Срочность: уровень находки от backend (EMERGENCY / URGENT / PLANNED); если его нет —
// по словарю: экстренная — флаг urgent, срочная — консультация в течение 7 дней
export const URGENCY = { urgent: 'Экстренная', soon: 'Срочная', planned: 'Плановая' };
const RANK = { urgent: 0, soon: 1, planned: 2 };
export const LEVEL_TO_URGENCY = { EMERGENCY: 'urgent', URGENT: 'soon', PLANNED: 'planned' };
export const urgencyOf = (entry) => (!entry ? null : entry.level ? LEVEL_TO_URGENCY[entry.level] ?? null
  : entry.urgent ? 'urgent' : entry.targetDays <= 7 ? 'soon' : 'planned');
/** Самая высокая срочность среди находок */
export const topUrgency = (codes, dict) => codes.map((c) => urgencyOf(dict[c])).filter(Boolean).sort((a, b) => RANK[a] - RANK[b])[0] ?? null;

export const EMPTY_FILTERS = { sex: '', age: '', pathology: '', urgency: '' };
export const activeCount = (f) => Object.values(f).filter(Boolean).length;

/** row: { sex, age, codes: string[], urgency } */
export const matchFilters = (f, row) =>
  (!f.sex || row.sex === f.sex)
  && (!f.age || ageGroup(row.age) === f.age)
  && (!f.pathology || row.codes.includes(f.pathology))
  && (!f.urgency || row.urgency === f.urgency);
