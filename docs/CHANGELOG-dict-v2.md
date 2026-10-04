# findings-dictionary.yaml: dict-v1-ml → dict-v2

Все правила утверждены медэкспертом. Обоснования и источники лежат в `razmetka-uzi.xlsx`, листы «Чек-лист по КР» и «Экстренные».

## Для ML (Даша)

**Новые коды (27).**
- ОМТ: ADENOMYOSIS, TUBO_OVARIAN_ABSCESS, HYDROSALPINX, CERVICAL_RETENTION_CYSTS, ENDOCERVICITIS, INTRAUTERINE_SYNECHIAE, UTERINE_CAVITY_FLUID, PCOM, LOW_OVARIAN_RESERVE, AMENORRHEA_HISTORY, UTERINE_PROLAPSE, PELVIC_VARICOSE_VEINS, IUD_MALPOSITION.
- ОБП: BILIARY_SLUDGE, GALLBLADDER_HYDROPS, CHRONIC_CHOLECYSTITIS, HEPATIC_STEATOSIS, LIVER_HEMANGIOMA, COLON_DIVERTICULA.
- Щитовидная железа: THYROID_DIFFUSE_AIT, THYROID_ENLARGEMENT.
- Сосуды и мягкие ткани: SUPERFICIAL_THROMBOPHLEBITIS, POST_THROMBOTIC_CHANGES, SAPHENOUS_DILATION, SOFT_TISSUE_INFLAMMATION.
- Простата: BPH (ДГПЖ без остаточной мочи; «по типу простатита» — атрибут).
- UNRECOGNIZED_ABNORMALITY — отклонение из заключения, которого нет в словаре (например, аневризма). Такие находки уходят координатору.

**Включены коды:** CERVICAL_POLYP, VENOUS_INSUFFICIENCY, ARTERIAL_STENOSIS, BPH_URINARY_RETENTION.

**Изменения в существующих кодах.**
- **DEEP_VEIN_THROMBOSIS:** «тромбофлебит» убран из синонимов. Тромбоз БПВ, МПВ и притоков теперь относится к SUPERFICIAL_THROMBOPHLEBITIS. Для него нужно извлекать `location` и `distanceToJunctionMm`.
- **TI-RADS:** добавлены поля `tiradsRaw` и `tiradsSystem` (EU | ACR | KWAK | UNKNOWN), в `tirads` теперь пишется категория по шкале EU. Kwak 4a → 4, Kwak 4b и 4c → 5.
- **Новые атрибуты:**
  - UTERINE_FIBROID: `degeneration`, `pedicleTorsion`, `uterusWeeks`, `compression`;
  - OVARIAN_LESION: `lesionType`, `bilateral`;
  - ENDOMETRIAL_HYPERPLASIA: `cycleDay`, `bleeding`, `heterogeneous`, `thin`;
  - GALLSTONES: `porcelain`, `sludge`;
  - GALLBLADDER_POLYP: `withStones`;
  - ACUTE_CHOLECYSTITIS: `murphy`, `doubleContour`;
  - FREE_FLUID: `beyondPelvis`;
  - HERNIA: `obstruction`, `content`;
  - BREAST_LESION: `benignChanges`, `ductContent`, `skinThickening`.
- **HERNIA:** «признаков ущемления нет» не означает NEGATION. Нужно вернуть грыжу с `incarcerated=false`.
- **Новые общие блоки:**
  - `ml.notFindings` — что не возвращать как находку;
  - `ml.patientContext` — менопауза, день цикла, кровотечение, ХГЧ, подготовка к исследованию;
  - `flags` — каждый флаг с указанием, кто его ставит (ML или бэкенд).
- **Флаг DISCREPANCY:** если находка есть только в описании или описание тяжелее заключения, ML возвращает находку по описанию и ставит этот флаг.

## Для бэкенда (Вита)

- **Уровни:** `urgent: true/false` заменено на `level: EMERGENCY | URGENT | PLANNED`. Уровень задаётся у находки и может переопределяться в правиле.
- **Новые операторы условий:** `lt`, `ne`, `missing: true`, `orMissing: true`.
- **Атрибуты контекста:** `patient.sex` (F | M), `protocol.studyType`.
- **Отсутствующие атрибуты (как работает бэкенд):** булев атрибут, которого нет, считается `false`; небулев делает условие невыполненным; `missing` и `orMissing` видят отсутствие любого атрибута. TRIGGER или SKIP в `ifMissing` применяется, только если ни одно правило не сработало, а какое-то было пропущено из-за отсутствующего небулева атрибута. **Для ML:** булевы признаки можно не присылать, если их нет в тексте, но `uncertain: true` при неуверенной формулировке присылать обязательно.
- **Новые блоки:**
  - `backend.mergeRules` — объединение гинекологических находок, детский специалист для пациентов младше 18 лет, флаги NO_CONCLUSION и DUPLICATE;
  - `backend.escalation` — таймеры экстренных и срочных находок.
- **Новый шаблон маршрута:** MANUAL_REVIEW.
- **Новый флаг бэкенда:** MERGED_GYNECOLOGY — находка объединена с блоком оперирующего гинеколога.
- **Важные изменения порогов:**
  - миома: субмукозный узел — это FIGO 0–2, а не ≤ 3;
  - полип ЖП: порог ≥ 8 мм вместо 10;
  - камни ЖП без осложнений: хирург через 30 дней вместо 7;
  - BI-RADS 2–3: наблюдение вместо NO_ROUTE;
  - остаточная моча: 50 мл (14 дней) и 300 мл (7 дней) вместо 100;
  - камни почки без обструкции: 30 дней;
  - свободная жидкость: сгустки, жидкость за пределами малого таза, ≥ 200 мл или «значительное количество» — ЭКСТРЕННО; со взвесью > 20 мл или анэхогенная > 50 мл — СРОЧНО, 1–3 дня; остальное — не находка.

---

# dict-v2 → dict-v2.1 (по замечаниям ML)

Изменения касаются в основном того, **что куда возвращает ML**. Правила маршрутизации почти не менялись.

## Для ML

- **Новый блок `ml.returnPolicy`** — единое правило, одинаковое для словаря, требований и разметки.
  - В `findings` попадает всё, что утверждается и для чего есть код, даже ниже порога: узел TI-RADS 2, наботовы кисты, BI-RADS 2, «фолликулярная киста», «небольшой выпот».
  - В `notTriggered NORMAL` идут физиологические состояния: жёлтое тело или фолликул ≤ 3 см без слова «киста», O-RADS 1, BI-RADS 1, ВМС на месте.
  - В `notTriggered NEGATION` попадает отрицание самой находки, в `POST_SURGERY` — состояние после операции.
  - Отрицание признака находку не отменяет: грыжа «без ущемления» — это `findings` с `incarcerated: false`.
  - Гранулярность: одна находка = код + сторона + location + тип или категория.
- **`ml.notFindings`:** убраны наботовы кисты (для них есть код `CERVICAL_RETENTION_CYSTS`, возвращать всегда), жёлтое тело (оно теперь в NORMAL) и физиологический выпот (теперь `FREE_FLUID` в `findings`).
- **`BREAST_LESION`:** BI-RADS 1 без других изменений идёт в `notTriggered NORMAL`; BI-RADS ≥ 2 и импланты Br2 — в `findings`.
- **`PCOM`:** возвращать, если в тексте есть объём ≥ 10 см³, фолликулов ≥ 20 или слово «поликистоз». Исключения (КОК, доминантная структура, возраст > 40) отсекает бэкенд.
- **`ARTERIAL_STENOSIS`:** добавлен атрибут `growth`.

## Для бэкенда

- **`LOW_OVARIAN_RESERVE`:** при КАФ ≥ 7 правило даёт `NO_ROUTE`, даже если врач прямо написал «снижение резерва».

## Разметка

- **Лист «Разметка».** Новые типы строк: «Находка ниже порога», «Физиологическая норма», «Не находка», «Служебное». Новая колонка «Ответ ML (ожидаемо)». Переразмечены 20 строк, добавлены строки для вторичных находок (ДГПЖ при остаточной моче, второй код щитовидной железы, BI-RADS по сторонам, POST_SURGERY).
- **Лист «Синтетика».** Одна строка — один ожидаемый элемент ответа ML, атрибуты строго ключами YAML. Добавлено 5 протоколов (29–33) для кодов без примеров. Эталон в машинном виде — `synthetic-gold.json`.
