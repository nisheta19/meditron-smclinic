// Справочники и сценарии демо-режима. В рабочей системе словарь и шаблоны живут на backend
// (GET /api/dictionary/findings, GET /api/route-templates) и меняются без правки кода.

const S = (code, name, studyTypes, targetSpecialty, routeTemplateCode, targetDays, extra = {}) =>
  ({ code, name, studyTypes, targetSpecialty, routeTemplateCode, targetDays, synonyms: [], conditions: {}, urgent: false, active: true, ...extra });

export const DICTIONARY = [
  S('ENDOMETRIAL_POLYP', 'Полип эндометрия', ['PELVIS_FEMALE'], 'Оперирующий гинеколог', 'SURGICAL_STANDARD', 7, { synonyms: ['полип эндометрия', 'полипоз эндометрия'] }),
  S('UTERINE_FIBROID', 'Миома матки', ['PELVIS_FEMALE'], 'Оперирующий гинеколог', 'SURGICAL_STANDARD', 14, { synonyms: ['миома', 'миоматозный узел'], conditions: { minSizeMm: 30 } }),
  S('SUBMUCOUS_FIBROID', 'Субмукозная миома', ['PELVIS_FEMALE'], 'Оперирующий гинеколог', 'SURGICAL_STANDARD', 7, { synonyms: ['субмукозный узел'] }),
  S('OVARIAN_MASS', 'Образование яичника', ['PELVIS_FEMALE'], 'Оперирующий гинеколог', 'SURGICAL_STANDARD', 7, { synonyms: ['киста яичника', 'параовариальная киста', 'O-RADS'], conditions: { minLevel: 3 } }),
  S('GALLSTONES', 'Желчнокаменная болезнь', ['ABDOMEN'], 'Хирург', 'SURGICAL_STANDARD', 14, { synonyms: ['ЖКБ', 'конкременты желчного пузыря', 'холецистолитиаз'] }),
  S('GALLBLADDER_POLYP', 'Полип желчного пузыря', ['ABDOMEN'], 'Хирург', 'SURGICAL_STANDARD', 14, { conditions: { minSizeMm: 10 } }),
  S('HERNIA', 'Грыжа', ['ABDOMEN'], 'Хирург', 'SURGICAL_STANDARD', 14, { synonyms: ['паховая грыжа', 'пупочная грыжа'] }),
  S('HYDRONEPHROSIS', 'Гидронефроз', ['ABDOMEN'], 'Уролог', 'CONSULTATION', 7, { synonyms: ['расширение ЧЛС', 'пиелоэктазия'] }),
  S('ABDOMINAL_AORTIC_ANEURYSM', 'Аневризма брюшной аорты', ['ABDOMEN'], 'Сосудистый хирург', 'URGENT_ESCALATION', 0, { conditions: { minSizeMm: 55 }, urgent: true }),
  S('BREAST_MASS', 'Образование молочной железы', ['BREAST'], 'Маммолог-онколог', 'ONCOLOGY_FAST', 5, { synonyms: ['BI-RADS'], conditions: { minLevel: 3 } }),
  S('THYROID_NODULE', 'Узел щитовидной железы', ['THYROID'], 'Эндокринолог', 'CONSULTATION', 14, { synonyms: ['узловой зоб', 'TI-RADS'], conditions: { minLevel: 3, minSizeMm: 10 } }),
  S('PROSTATE_ENLARGEMENT', 'Гиперплазия предстательной железы', ['PROSTATE'], 'Уролог', 'CONSULTATION', 14, { synonyms: ['ДГПЖ', 'аденома'], conditions: { minVolumeMl: 30 } }),
  S('PERIPHERAL_ARTERY_STENOSIS', 'Стеноз артерий нижних конечностей', ['LOWER_LIMB_VESSELS'], 'Сосудистый хирург', 'SURGICAL_STANDARD', 14, { synonyms: ['стенозирующий атеросклероз'], conditions: { minStenosisPct: 50 } }),
  S('VARICOSE_VEINS', 'Варикозная болезнь', ['LOWER_LIMB_VESSELS'], 'Флеболог', 'CONSULTATION', 30, { synonyms: ['варикозная трансформация', 'ВБНК'] }),
  S('DEEP_VEIN_THROMBOSIS', 'Тромбоз глубоких вен', ['LOWER_LIMB_VESSELS'], 'Сосудистый хирург', 'URGENT_ESCALATION', 0, { synonyms: ['ТГВ', 'флеботромбоз'], urgent: true }),
];

const consult = (dueInDays) => ({ type: 'SPECIALIST_CONSULTATION', name: 'Консультация специалиста', dueInDays });

export const TEMPLATES = [
  { code: 'SURGICAL_STANDARD', name: 'Хирургический маршрут', steps: [consult(7),
    { type: 'HOSPITALIZATION_REFERRAL', name: 'Направление на госпитализацию', dueInDays: 21 },
    { type: 'HOSPITALIZATION', name: 'Госпитализация и операция', dueInDays: 35 },
    { type: 'FOLLOW_UP', name: 'Контрольный визит после выписки', dueInDays: 49 }] },
  { code: 'CONSULTATION', name: 'Консультация и наблюдение', steps: [consult(14),
    { type: 'FOLLOW_UP', name: 'Контрольный приём', dueInDays: 90 }] },
  { code: 'ONCOLOGY_FAST', name: 'Онкологический приоритетный', steps: [consult(5),
    { type: 'BIOPSY', name: 'Биопсия', dueInDays: 10 },
    { type: 'FOLLOW_UP', name: 'Консультация по результатам биопсии', dueInDays: 17 }] },
  { code: 'URGENT_ESCALATION', name: 'Экстренная эскалация', steps: [
    { type: 'ESCALATION', name: 'Эскалация дежурному врачу', dueInDays: 0 }] },
];

// Что происходило с пациентом после поступления протокола: [день от поступления, действие, аргумент]
export const SCENARIOS = {
  'ml-sample-omt-2': [[0.1, 'confirm'], [0.1, 'route'], [0.1, 'notify'], [2, 'step', 'BOOKED'], [8, 'step', 'COMPLETED']],
  'ml-sample-veins-4': [[1, 'confirm'], [1, 'route'], [1, 'notify']],
  'ml-sample-thyroid-3': [[0.2, 'confirm'], [0.2, 'route'], [0.2, 'notify'], [1, 'step', 'BOOKED']],
  'ml-demo-01': [[0.1, 'confirm'], [0.1, 'route'], [0.1, 'notify'], [1, 'step', 'BOOKED']],
  'ml-demo-02a': [[0.1, 'confirm'], [0.1, 'route'], [0.1, 'notify'], [2, 'step', 'BOOKED'], [7, 'step', 'COMPLETED'], [7, 'finish']],
  'ml-demo-02b': [[0.1, 'confirm'], [0.1, 'route'], [0.1, 'notify'], [1, 'step', 'BOOKED'], [6, 'step', 'COMPLETED'], [8, 'step', 'COMPLETED'], [15, 'step', 'BOOKED']],
  'ml-demo-05': [[0.1, 'confirm'], [0.1, 'route'], [0.1, 'notify', 'PUSH'], [1, 'step', 'BOOKED'], [3, 'step', 'NO_SHOW']],
  'ml-demo-07': [[0.2, 'confirm'], [0.2, 'route'], [0.2, 'notify']],
  'ml-demo-08': [[0.1, 'confirm'], [0.1, 'route']],
  'ml-demo-09': [[0.1, 'confirm'], [0.1, 'route'], [0.1, 'notify'], [3, 'step', 'BOOKED'], [10, 'step', 'COMPLETED']],
  'ml-demo-12': [[0.02, 'confirm'], [0.02, 'route']],
  'ml-demo-14v1': [[0.1, 'confirm'], [0.1, 'route'], [0.1, 'notify']],
};

// Автонапоминания по сценарию 2 кейса (дни от первого уведомления)
export const LADDER = [
  [1, 'Напоминаем: по результату исследования вам рекомендована консультация специалиста. Выберите удобный формат, очно или онлайн: sm.example/r/…'],
  [3, 'По результатам исследования остаётся рекомендация проконсультироваться с врачом. Подобрать специалиста и время: sm.example/r/…'],
  [14, 'Напоминаем о рекомендации обратиться к профильному врачу. Если консультация уже была в другой клинике, отметьте это в личном кабинете.'],
];
