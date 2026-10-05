/** Adapter for final/frontend/src/api/client.js and the nested backend response.
 * No demo imports, API requests, medical rules, fabricated routes or notification dates.
 */
const ORGAN = {
  PELVIS_FEMALE:'Органы малого таза', ABDOMEN:'Брюшная полость', BREAST:'Молочные железы',
  THYROID:'Щитовидная железа', PROSTATE:'Предстательная железа', LOWER_LIMB_VESSELS:'Сосуды нижних конечностей',
  KIDNEY:'Почки', SOFT_TISSUE:'Мягкие ткани'
};
const LEVEL = { EMERGENCY:'Экстренно', URGENT:'Срочно', PLANNED:'Планово' };
export const STAGE = {
  CREATED:'Создан', NOTIFIED:'Уведомлён', BOOKED:'Записан', REBOOKING_REQUIRED:'Нужна повторная запись', NO_SHOW:'Неявка',
  AWAITING_TACTIC:'Ждёт решения врача', ADDITIONAL_EXAM:'Дообследование', PROCEDURE_REFERRED:'Направлен на процедуру',
  PROCEDURE_DONE:'Процедура выполнена', HOSPITALIZATION_REFERRED:'Направлен на госпитализацию',
  HOSPITALIZATION_SCHEDULED:'Госпитализация назначена', HOSPITALIZED:'Госпитализирован', SURGERY_DONE:'Операция выполнена',
  DISCHARGED:'Выписан', CONTROL_PENDING:'Ждёт контрольного визита', OBSERVATION_WAITING_US:'Ждёт контрольного УЗИ',
  OBSERVATION_WAITING_VISIT:'Ждёт визита после УЗИ', COMPLETED:'Завершён', CLOSED:'Закрыт', NOT_ENGAGED:'Не вовлечён'
};
const TYPE = { SURGICAL:'Хирургический', DIAGNOSTIC:'Диагностический', OBSERVATION:'Наблюдение', CONSULTATION:'Консультация', EMERGENCY:'Экстренный' };
const TACTIC = { SURGERY_INDICATED:'Оперативное лечение показано', ADDITIONAL_EXAM:'Дообследование', OBSERVATION:'Наблюдение', SURGERY_NOT_INDICATED:'Операция не показана', PATIENT_REFUSED:'Отказ пациента', OTHER_PROFILE:'Другой профиль' };
const ROLE = { MANAGER:'менеджер', HOSPITALIZATION_MANAGER:'менеджер госпитализации', COORDINATOR:'координатор', DUTY_DOCTOR:'дежурный врач', ADMINISTRATOR:'администратор' };
const STEP = { PENDING:'Ожидает', NOTIFIED:'Уведомлён', BOOKED:'Записан', COMPLETED:'Выполнен', NO_SHOW:'Неявка', CANCELLED:'Отменён', SKIPPED:'Пропущен' };
const value = v => v == null || v === '' ? null : v;
const unit = (v,u) => value(v) === null ? null : `${v}${u}`;

export function fromFinalPatient(response, { notifications = [], timeZone = 'Europe/Moscow' } = {}) {
  if (!response) return null;
  const p = response.patient ?? response;
  const date = v => {
    if (!v) return null;
    const plain = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
    if (plain) return `${plain[3]}.${plain[2]}.${plain[1]}`;
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString('ru-RU',{timeZone});
  };
  const stamp = v => {
    const day = date(v);
    return day ? `${day} · ${new Date(v).toLocaleTimeString('ru-RU',{timeZone,hour:'2-digit',minute:'2-digit'})}` : null;
  };
  const protocols = [response.currentProtocol, ...(response.history?.protocols ?? [])].filter(Boolean);
  const protocolById = new Map(protocols.map(item => [item.id,item]));
  const allFindings = new Map([...(response.history?.findings ?? []), ...(response.currentFindings ?? [])].map(f => [f.id,f]));
  const clinical = [...(response.clinicalRoutes ?? []), ...(response.history?.clinicalRoutes ?? [])];
  const visibleIds = new Set([...(response.currentFindings ?? []).map(f => f.id), ...clinical.filter(r => r.open).flatMap(r => (r.findings ?? []).map(f => f.id))]);
  const findings = [...allFindings.values()].filter(f => visibleIds.has(f.id) && f.status !== 'REMOVED').map(f => ({
    id:f.id, name:f.name, organ:ORGAN[protocolById.get(f.protocolId)?.studyType] ?? null,
    status:f.status === 'REJECTED' ? 'Отклонена' : LEVEL[f.level] ?? null, urgent:f.status !== 'REJECTED' && f.level === 'EMERGENCY', source:f
  }));
  const mappedClinical = clinical.map(r => ({
    id:r.id, specialist:r.specialty, type:TYPE[r.routeType] ?? r.routeType,
    stage:r.stageTitle ?? STAGE[r.stage] ?? r.stage,
    due:date(r.dueAt) ? `до ${date(r.dueAt)}` : null,
    visit:stamp(r.appointment?.status === 'BOOKED' ? r.appointment.dateTime : r.visitAt),
    overdue:r.open && (r.overdueDays > 0 || r.slaOverdue === true), source:r,
    details:{
      findings:(r.findings ?? []).map(f => {
        const organ = ORGAN[protocolById.get(allFindings.get(f.id)?.protocolId ?? r.protocolId)?.studyType];
        return [f.name,organ].filter(Boolean).join(' · ');
      }),
      stages:(r.stageHistory ?? []).map(s => [stamp(s.at)?.replace(/\.\d{4}/,''), STAGE[s.stage] ?? s.stage].filter(Boolean).join(' ')),
      conclusion:[TACTIC[r.tactic] ?? r.tactic, r.tacticComment].filter(Boolean).join(' · ') || null,
      task:(r.openTasks ?? []).map(t => [t.text, ROLE[t.role] ?? t.role, date(t.dueAt) ? `до ${date(t.dueAt)}` : null].filter(Boolean).join(' — ')).join('\n') || null
    }
  }));
  const routes = response.clinicalRoutes != null ? mappedClinical.filter(r => r.source.open) : (response.routes ?? []).map(r => {
    const step = r.steps?.find(s => s.id === r.currentStepId);
    return {
      id:r.id, specialist:step?.name ?? null, type:null, stage:STEP[step?.status] ?? null,
      due:step?.dueDate ? `до ${date(step.dueDate)}` : null,
      visit:stamp(step?.completedAt), overdue:r.overdue === true, source:r
    };
  });
  const name = [p.lastName,p.firstName,p.middleName].filter(Boolean);
  const bmi = Number(p.heightCm) > 0 && Number(p.weightKg) > 0
    ? (p.weightKg / (p.heightCm/100)**2).toFixed(1).replace('.',',') : null;
  return {
    id:value(p.externalId), name:name.length ? name : [p.fullName].filter(Boolean),
    email:value(p.email), phone:value(p.phone), snils:value(p.snils), age:value(p.age),
    birthDate:date(p.birthDate), sex:({F:'Женский',M:'Мужской'})[p.sex] ?? null,
    height:unit(p.heightCm,' см'), weight:unit(p.weightKg,' кг'), bmi, blood:value(p.bloodType),
    routes, findings,
    notifications:notifications.map(n => ({
      id:n.id, message:n.fullText ?? n.text, route:n.specialty ?? mappedClinical.find(r => r.id === n.routeId)?.specialist ?? routes.find(r => r.id === n.routeId)?.specialist ?? null,
      sent:stamp(n.sentAt), read:stamp(n.readAt), booked:typeof n.bookedAfter === 'boolean' ? n.bookedAfter : typeof n.booked === 'boolean' ? n.booked : null, source:n
    })),
    history:[...protocols.map(proto => ({
      id:proto.id, date:stamp(proto.receivedAt), title:'Исследование',
      subtitle:proto.status === 'DONE' ? 'Результат' : proto.status === 'FAILED' ? 'Ошибка обработки' : proto.status === 'ANNULLED' ? 'Аннулирован' : null,
      source:proto, kind:'protocol', at:proto.receivedAt
    })), ...mappedClinical.filter(r => r.source.visitAt || !r.source.open).map(r => ({
      id:`route-${r.id}`, date:stamp(r.source.closedAt ?? r.source.visitAt), title:r.specialist, subtitle:r.source.open ? 'Приём состоялся' : r.stage,
      source:r.source, kind:'route', at:r.source.closedAt ?? r.source.visitAt, details:r.details
    }))].sort((a,b) => String(b.at ?? '').localeCompare(String(a.at ?? '')))
  };
}
