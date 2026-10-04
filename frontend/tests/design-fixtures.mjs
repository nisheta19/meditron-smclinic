// Entirely fictional browser fixtures. No source medical documents are used.
const people = [
  ['Фамилия Имя Отчество', 67, '1959-02-10', 'Полип яичника', 'PELVIS_FEMALE'],
  ['Другой Николай Дмитриевич', 27, '1999-01-19', 'Варикозная болезнь', 'LOWER_LIMB_VESSELS'],
  ['Длиннофамильная Вера Сергеевна', 40, '1986-10-03', 'Миома матки', 'PELVIS_FEMALE'],
  ['Некоторый Иван Сергеевич', 57, '1969-04-12', 'Полип яичника', 'PELVIS_FEMALE'],
];
export const patients = people.map(([fullName, age, birthDate, name, studyType], i) => ({
  id: `design-${i}`, externalId: `design-patient-${i}`, fullName, age, birthDate, sex: 'F', studyType,
  reviewState: 'PENDING', receivedAt: '2026-10-02T05:41:00Z', activeFindings: 1,
  topFindings: [{ name, targetDays: 30 }], maxLevel: 'PLANNED',
}));
const lines = [
  'ЩИТОВИДНАЯ ЖЕЛЕЗА',
  'Учебный протокол для проверки интерфейса. Пациент вымышленный.',
  'РАСПОЛОЖЕНИЕ: обычное',
  'КОНТУРЫ: ровные, чёткие',
  'РАЗМЕРЫ:',
  'Правая доля: 15 × 18 × 40 мм. Объём доли 5,6 см куб.',
  'Левая доля: 16 × 19 × 42 мм. Объём доли 6,6 см куб.',
  'Перешеек толщиной 3 мм.',
  'Общий объём щитовидной железы: 12,2 см куб.',
  'ЭХОСТРУКТУРА: неоднородная.',
  'УЗЛОВЫЕ ОБРАЗОВАНИЯ:',
  'В правой доле узловые образования не определяются.',
  'В левой доле определяется узел 12 × 9 мм, с чёткими границами.',
  'В нижнем полюсе левой доли определяется второй узел 8 × 6 мм.',
  'Описания и размеры созданы только для визуального теста.',
  'ЭХОГЕННОСТЬ: смешанная.',
  'СОСУДИСТЫЙ РИСУНОК: умеренный.',
  'РЕГИОНАРНЫЕ ЛИМФОУЗЛЫ: без особенностей.',
  'ЗАКЛЮЧЕНИЕ:',
  'Узлы левой доли щитовидной железы.',
  'TI-RADS 3.',
  'РЕКОМЕНДАЦИИ:',
  'Консультация эндокринолога.',
];
const text = lines.join('\n');
export const protocol = {
  id: 'design-protocol', externalId: 'design-doc', version: 1, studyType: 'THYROID', status: 'DONE',
  receivedAt: '2026-07-13T10:14:00Z', studyDate: '2026-07-13', conclusionFound: true,
  conclusion: 'Учебное исследование. Данные вымышлены.', flags: [], text, notTriggered: [],
};
export const findings = [lines[12], lines[13]].map((quote, i) => ({
  id: `design-finding-${i}`, protocolId: protocol.id, code: 'THYROID_NODULE', name: 'Узел щитовидной железы',
  status: 'SUGGESTED', source: 'ML', attributes: { side: 'left', sizeMm: i ? 8 : 12, tirads: 3 },
  level: 'PLANNED', targetSpecialty: 'Эндокринолог', targetDays: 30,
  evidence: { text: quote, start: text.indexOf(quote), end: text.indexOf(quote) + quote.length }, flags: [],
}));
protocol.findings = findings;
export const patientCard = {
  patient: { ...patients[0], externalId: '123456789', heightCm: 172, weightKg: 74, bloodType: 'A(II) Rh+',
    email: 'namesurname@example.test', phone: '+7 000 000 00 00', snils: 'XXX-XXX-XXX YY' },
  currentProtocol: protocol, currentFindings: findings, routes: [],
  history: { protocols: Array.from({ length: 10 }, (_, i) => ({ ...protocol, id: `history-${i}`,
    externalId: `history-doc-${i}`, receivedAt: `2026-${String(6 - Math.floor(i / 2)).padStart(2, '0')}-${i % 2 ? '05' : '20'}T09:21:00Z`,
    conclusion: 'Результат учебного исследования', findings: [] })), findings: [], routes: [] },
};
