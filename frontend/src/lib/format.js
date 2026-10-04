// Подписи enum'ов из openapi.yaml, тона бейджей и форматирование
import { USE_MOCK, demo } from '../api';

export const STUDY = {
  PELVIS_FEMALE: 'УЗИ органов малого таза', ABDOMEN: 'УЗИ брюшной полости', BREAST: 'УЗИ молочных желёз',
  THYROID: 'УЗИ щитовидной железы', PROSTATE: 'УЗИ предстательной железы', LOWER_LIMB_VESSELS: 'УЗДС сосудов нижних конечностей',
  KIDNEY: 'УЗИ почек', SOFT_TISSUE: 'УЗИ мягких тканей',
};
export const REVIEW = { PENDING: ['Новые находки', 'amber'], ATTENTION: ['Нужна проверка', 'red'], OK: ['Проверено', 'ok'] };
export const FINDING = { SUGGESTED: ['Предложена', 'amber'], CONFIRMED: ['Подтверждена', 'ok'], REJECTED: ['Отклонена', 'neutral'], REMOVED: ['Удалена', 'neutral'] };
export const STEP = {
  PENDING: ['Ожидает', 'neutral'], NOTIFIED: ['Уведомлён', 'blue'], BOOKED: ['Записан', 'ok'], COMPLETED: ['Выполнен', 'ok'],
  NO_SHOW: ['Неявка', 'amber'], CANCELLED: ['Отменён', 'neutral'], SKIPPED: ['Пропущен', 'neutral'],
};
export const ROUTE = { ACTIVE: ['Активен', 'blue'], COMPLETED: ['Завершён', 'ok'], CANCELLED: ['Отменён', 'neutral'], NOT_ENGAGED: ['Не вовлечён', 'amber'] };
export const PROCESSING = { DONE: ['Распознан', 'ok'], FAILED: ['Не распознан', 'red'], ANNULLED: ['Аннулирован', 'neutral'] };
export const NOT_TRIGGERED = {
  NEGATION: 'Отрицание', NORMAL: 'Вариант нормы', POST_SURGERY: 'После операции',
  BELOW_THRESHOLD: 'Ниже порога словаря', OUT_OF_SCOPE: 'Нет в словаре',
};
export const CHANNEL = { PERSONAL_ACCOUNT: 'Личный кабинет', PUSH: 'Push', SMS: 'SMS' };
export const CANCEL_REASON = { PROTOCOL_ANNULLED: 'протокол аннулирован', PROTOCOL_UPDATED: 'протокол исправлен', FINDING_REMOVED: 'находка удалена', MANUAL: 'отменён вручную' };
export const ATTR = {
  birads: 'BI-RADS', biradsSub: 'Подкатегория BI-RADS', orads: 'O-RADS', tirads: 'TI-RADS (Kwak)', count: 'Количество',
  residualUrineMl: 'Остаточная моча, мл', volumeCm3: 'Объём, см³', ovaryVolumeCm3: 'Объём яичника, см³',
  maxStenosisPct: 'Максимальный стеноз, %', distanceToJunctionMm: 'До соустья, мм',
  menopause: 'Менопауза', recurrent: 'Повторное выявление', benignChanges: 'Доброкачественные изменения',
  suspiciousLymphNodes: 'Изменённые лимфоузлы', inflammation: 'Признаки воспаления', ductContent: 'Содержимое протока', skinThickening: 'Утолщение кожи',
  sizeMm: 'Размер, мм', side: 'Сторона', category: 'Категория', level: 'Уровень', multiple: 'Множественные', location: 'Локализация',
  stenosisPct: 'Стеноз, %', artery: 'Артерия', diameterMm: 'Диаметр, мм', volumeMl: 'Объём, мл', residualMl: 'Остаточная моча, мл',
  defectMm: 'Грыжевые ворота, мм', pelvisMm: 'Лоханка, мм', floatingMm: 'Флотация, мм', figo: 'FIGO', uncertain: 'Под вопросом',
};
const SIDE = { left: 'слева', right: 'справа', both: 'с обеих сторон' };
export const attrValue = (k, v) => (typeof v === 'boolean' ? (v ? 'да' : 'нет') : k === 'side' ? SIDE[v] ?? v
  : Array.isArray(v) ? v.join(', ') : v && typeof v === 'object' ? JSON.stringify(v) : v);

/** Текущее время: в демо-режиме — модельное */
export const now = () => (USE_MOCK ? Date.parse(demo.now()) : Date.now());

export const fmtDate = (v) => (v ? new Date(v).toLocaleDateString('ru-RU') : '—');
export const fmtDateTime = (v) => (v ? new Date(v).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—');
export const ago = (v) => {
  if (!v) return 'нет';
  const h = Math.floor((now() - Date.parse(v)) / 36e5);
  return h < 1 ? 'только что' : h < 24 ? `${h} ч назад` : `${Math.floor(h / 24)} дн. назад`;
};

export const cmp = (a, b) => (a == null ? 1 : b == null ? -1 : typeof a === 'string' ? a.localeCompare(b, 'ru') : a - b);

// ---------- Тексты строк списка (как в макете) ----------
export const plural = (n, [one, few, many]) => {
  const a = Math.abs(n) % 100, b = a % 10;
  return a > 10 && a < 20 ? many : b === 1 ? one : b >= 2 && b <= 4 ? few : many;
};
export const nWord = (n, forms) => `${n} ${plural(n, forms)}`;
export const DAYS = ['день', 'дня', 'дней'];
export const targetDaysText = (days) => days == null ? null : days === 0 ? 'Немедленно' : `В течение ${nWord(days, ['дня', 'дней', 'дней'])}`;
// Presentation of the displayed interval; does not reclassify the backend's medical level.
export const deadlineTone = (days) => !Number.isFinite(days) ? '' : days <= 0 ? 'red' : days <= 3 ? 'amber' : '';
export const ageText = (n) => (n == null ? '' : nWord(n, ['год', 'года', 'лет']));
export const notesText = (n) => nWord(n, ['уведомление', 'уведомления', 'уведомлений']);
export const fmtStamp = (v) => (v ? `${fmtDate(v)} · ${new Date(v).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}` : '');
export const daysAgo = (v) => {
  if (!v) return 'Не уведомлён';
  const d = Math.floor((now() - Date.parse(v)) / 864e5);
  return d < 1 ? 'Сегодня' : `${nWord(d, DAYS)} назад`;
};

/** Срок записи: [текст, цвет самого текста]. */
export function deadlineText({ dueDate, currentStepStatus, routeStatus }, stepType) {
  if (routeStatus === 'COMPLETED') return ['Маршрут завершён', ''];
  if (routeStatus === 'CANCELLED') return ['Маршрут отменён', ''];
  if (['BOOKED', 'COMPLETED'].includes(currentStepStatus)) return ['Записан', ''];
  if (stepType === 'ESCALATION') return ['Немедленно', 'red'];
  if (!dueDate) return ['—', ''];
  const today = new Date(now()).toISOString().slice(0, 10);
  const left = Math.round((Date.parse(dueDate) - Date.parse(today)) / 864e5);
  if (left < 0) return [`Просрочено ${nWord(-left, DAYS)}`, deadlineTone(left)];
  if (left === 0) return ['Последний день', deadlineTone(left)];
  return [`${plural(left, ['Остался', 'Осталось', 'Осталось'])} ${nWord(left, DAYS)}`, deadlineTone(left)];
}
/** «Кудрявцев Сергей Михайлович» → «Кудрявцев С. М.» — как в макете списка */
export const shortName = (full = '') => {
  const [last, ...rest] = full.trim().split(/\s+/);
  // Сокращаем только слова-имена: «Пациент 007» из демо-данных backend остаётся как есть
  return [last, ...rest.map((w) => (/^\p{L}+$/u.test(w) ? `${w[0]}.` : w))].join(' ');
};
/** «Консультация: хирург» → «Хирург»; остальные этапы — как есть, с заглавной */
export const stepLabel = (name = '') => { const t = name.replace(/^Консультация:\s*/i, ''); return t ? t[0].toUpperCase() + t.slice(1) : t; };

// ---------- Поля backend сверх openapi v0.2.0 ----------
/** Уровень срочности находки (FindingLevel backend) */
export const LEVEL = { EMERGENCY: ['Экстренно', 'red'], URGENT: ['Срочно', 'amber'], PLANNED: ['Планово', 'neutral'] };
/** Флаги качества протокола и находки (раздел flags словаря) */
export const FLAG = {
  DISCREPANCY: 'Расхождение', INCOMPLETE: 'Неполное описание', NO_CONCLUSION: 'Нет заключения', PREP_VIOLATED: 'Нарушена подготовка',
  OUTDATED_TERM: 'Устаревший термин', INCORRECT_TERM: 'Некорректный термин', TEMPLATE_NORM: 'Шаблонная норма',
  SYSTEM_UNKNOWN: 'Система не указана', SYSTEM_CONVERTED: 'Система переведена', DUPLICATE: 'Дубликат',
  MINOR: 'Несовершеннолетний', MERGED_GYNECOLOGY: 'Объединено',
};
export const flagLabel = (f) => FLAG[f.code] ?? (f.name ? f.name[0] + f.name.slice(1).toLowerCase() : f.code);
