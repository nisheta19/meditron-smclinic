> Это исходное описание эталонной реализации из дополнения. Актуальные исправления, совместимость и результаты подключения описаны в [routes-integration.md](routes-integration.md).

# Эталонная реализация маршрутов (для сверки ИИ-ассистентом)

**Что это.** Вариант бэкенда по `docs/ROUTES-REQUIREMENTS.md` (v1.1), написанный Claude по запросу капитана команды. Это **предложение для сверки, а не готовый к слиянию код**. Ассистент коллеги, у которого есть сборка, должен:
1. прочитать ТЗ;
2. прочитать этот документ;
3. сравнить код с ТЗ и со своим вариантом (если он уже есть);
4. собрать, прогнать тесты, исправить найденное и решить, что взять.

**Ветка:** `feature/routes-reference` от коммита `30adbfe` («Add dashboard, improve ML extraction…»).

## 0. Честный статус (прочитать первым)

- **Код не компилировался с настоящими зависимостями.** В окружении автора нет Maven и библиотек (Spring, Lombok, Jackson, JPA). Сделана только проверка `javac` без зависимостей, с эмуляцией геттеров Lombok: синтаксических ошибок и обращений к несуществующим методам собственных классов нет. Ошибки, которые видны только при настоящей сборке (аннотации Spring Data, вывод типов с Lombok, тонкости JPA), возможны.
- **Юнит-тесты написаны, но не запускались** (нет JUnit в окружении автора). Чистые помощники (`TextRenderer`, `WorkingDays`, склонение сроков) проверены отдельным запуском.
- **Интеграционных тестов с базой нет.** Сценарные проверки — через `/api/sim/scenarios` (раздел 6 ниже).
- **`docs/openapi.yaml` и `docs/openapi-runtime.yaml` не обновлены.** Это TODO (раздел 7). Контроллеры размечены `@Operation`, поэтому springdoc отдаст актуальную схему на `/v3/api-docs`.

## 1. Как изолировано

**Весь новый код — в новых пакетах**, существующие таблицы не меняются:

| Пакет / файл | Что внутри |
|---|---|
| `ru.meditron.routing.route.config` | `RouteConfig` — чтение `route-config.yaml` |
| `ru.meditron.routing.route.domain` | Сущности `Route`, `RouteNotification`, `StaffTask`, `Escalation`, `RouteTimer`, `JournalEntry`, `Appointment`, `ProcessedEvent` и перечисления |
| `ru.meditron.routing.route.repo` | Репозитории Spring Data |
| `ru.meditron.routing.route.service` | Логика (раздел 2) |
| `ru.meditron.routing.route.web` | Контроллеры |
| `ru.meditron.routing.route.dto` | `RouteDtos` — все DTO модуля |
| `ru.meditron.routing.time.ModelTime` | Модельные часы |
| `ru.meditron.routing.event.RoutingEvents` | События, которыми старый код сообщает модулю о переменах |
| `resources/routing/route-config.yaml` | Все сроки, тексты, таймеры, лестница, локации, врачи |
| `test/.../route/*Test.java` | Юнит-тесты модуля |
| `docs/ROUTES-REQUIREMENTS.md` | ТЗ v1.1 |

**Точки касания старого кода** — минимальные, их легко просмотреть в `git diff 30adbfe -- backend/src/main/java/ru/meditron/routing/{config,domain,dto,service}`:

| Файл | Изменение |
|---|---|
| `domain/Finding`, `Patient`, `Protocol`, `MlResultLog` | Значение по умолчанию `createdAt` / `receivedAt`: `Instant.now()` → `ModelTime.now()` |
| `service/FindingService` | `Instant.now()` → `ModelTime.now()`; после каждого действия публикуется `FindingsChanged` |
| `service/MlIngestionService` | `Instant.now()` → `ModelTime.now()`; публикуются `ProtocolAccepted` (DONE), `ProtocolClosed` (ANNULLED / CORRECTED) |
| `service/DtoMapper` | `LocalDate.now()` → `ModelTime.today()` (возраст) |
| `service/PatientQueryService` | Карточка: `routes` (открытые), `history.routes` (закрытые), баннер. Модуль подключён через `ObjectProvider` |
| `dto/PatientCardDto` | Новое поле `unfinishedRouteBanner` |
| `config/SecurityConfig` | Адреса координатора — в защищённых (вход + CSRF при `auth.required=true`); `/api/integration/**` и `/api/sim/**` — без CSRF |
| `resources/application.yml` | Блок `routes` (путь к настройкам, период исполнения таймеров) |

Старый `POST /api/integration/events` (пересылка протоколов в ML) **не тронут**. События маршрута идут на новый `POST /api/integration/route-events`.

## 2. Где что из ТЗ

| Раздел ТЗ | Класс |
|---|---|
| 3. Модельное время | `ModelTime`; продвижение и исполнение — `SimController` → `TimerRunner`; реальное время — `RouteModuleConfig.tick` (`routes.tick-ms`) |
| 4.1–4.3. Создание, один маршрут на специалиста, без дублей | `RouteEngine.reconcile` → `create` / `addFindings`; чистые правила — `RoutePlanning` |
| 4.4. Изменения после создания | `RouteEngine.reconcile`: находки не в статусе CONFIRMED убираются, пустой маршрут закрывается (`FINDING_REJECTED` / `PROTOCOL_CORRECTED` / `PROTOCOL_ANNULLED`) |
| 4.5. Тип цепочки | `RoutePlanning.chainOf` |
| 5. Этапы, тактика, закрытие | `RouteEngine` (события, `tactic`), `RouteStateService` (смена этапа, закрытие, завершение) |
| 5.4. Аннулирование и исправление | `RouteListeners.onProtocolClosed` → `EscalationService.onProtocolClosed` + `RouteEngine.reconcile` |
| 6.1–6.4. Цепочки, неявка, отмена | `ChainService` (шаги из YAML), `RouteEngine.noShow` / `bookingCancelled` |
| 6.5. Остановка цепочки, лимит сообщений | `ChainService.stop`, `NotificationService.sendAuto` (откладывание через таймер `DEFERRED_MESSAGE`) |
| 6.6–6.8. Тексты, падежи | `route-config.yaml` (`templates`, `specialists`), `TextRenderer`, `NotificationService.values` |
| 6.7. Ручная отправка | `NotificationService.sendManual`: только шаблоны; без `confirm` и при сообщении за сутки — 409 `CONFIRM_REQUIRED` |
| 7. Госпитализация, процедура, контроль | `RouteEngine.hospitalization*`, `discharged`, `procedureDone`; рабочие дни — `WorkingDays` |
| 8. CRM | `RouteNotification` (полная и короткая версия, ссылки, кнопки); статусы и ответы — `RouteEventService.crm` |
| 9. Лестница эскалации | `EscalationService` |
| 10. События МИС | `RouteEventService.handle` (идемпотентность — `ProcessedEvent`), `IntegrationRouteController` |
| 11. Расписание | `ScheduleService` (детерминированные слоты, кодируются в `slotId`) |
| 12. Задачи | `TaskService`, `StaffTask` |
| 13. Журнал | `JournalService`, `JournalEntry` (`@Immutable`); отклонённое событие пишется в отдельной транзакции |
| 14. Сценарии | `ScenarioService` |
| 15. API, баннер | `RouteController`, `StaffController`, `IntegrationRouteController`, `SimController`, `RouteQueryService.banner` |
| 17. Дашборд | `DashboardService` (вехи в `Route.milestones`) |

## 3. API (кратко)

- **Маршруты и уведомления:** `GET /api/patients/{id}/routes`, `GET /api/routes?stage&specialty&overdue&open`, `GET /api/routes/{id}`, `GET /api/routes/{id}/notifications`, `GET /api/patients/{id}/notifications`, `POST /api/routes/{id}/notifications {templateCode, confirm, doctor}`, `GET /api/notification-templates`, `GET /api/route-templates`.
- **Задачи, эскалации, журнал:** `GET /api/tasks`, `POST /api/tasks/{id}/done`, `GET /api/escalations`, `POST /api/escalations/{id}/accept|contacted|close`, `GET /api/patients/{id}/journal`, `GET /api/journal`.
- **Дашборд:** `GET /api/dashboard/funnel|losses|escalations|patients` (фильтры: `dateFrom`, `dateTo`, `studyType`, `routeType`).
- **Интеграция:** `POST /api/integration/route-events`, `POST /api/integration/crm/callbacks`, `GET /api/schedule/slots`, `POST /api/schedule/bookings`.
- **Демо:** `GET/POST /api/sim/clock[/advance|/reset]`, `GET /api/sim/crm/outbox`, `GET /api/sim/scenarios`, `POST /api/sim/scenarios/{name}/start`, `POST /api/sim/scenarios/{runId}/next`, `GET /api/sim/scenarios/runs/{runId}`.

Ручного составления, отмены и смены этапа маршрута нет: по ТЗ это запрещено.

## 4. Решения автора там, где ТЗ допускает толкование

Проверить и, если нужно, согласовать с медэкспертом (Вита):

1. **Перезапуск цепочки** после отмены, неявки, просрочки дообследования или наблюдения **не повторяет первое сообщение** (`INITIAL`). Идут напоминания 24 ч → 72 ч → звонок → 14 дней → 30 дней. После контрольного УЗИ при наблюдении цепочка стартует **с** первым сообщением.
2. **Новый маршрут при «направлении в другой профиль»:** срок = минимальный `targetDays` находок маршрута (по умолчанию 30 дней).
3. **Визит за результатом процедуры и контрольный визит после выписки:** если пациент не записался, ставится только метка «Просрочено», автоматических напоминаний нет. Для выписки без записи по ТЗ есть сообщение `CONTROL_RECOMMENDED` и задача координатору.
4. **Тип маршрута для фильтра дашборда:** `CONSULT_OBSERVATION` → `CONSULTATION`, отдельно от трёх типов ТЗ (хирургический, наблюдение, диагностика). Меняется в `route-config.yaml → routeTypes`.
5. **Маршрут после экстренной эскалации** создаётся при закрытии с исходом:
   - «Приедет сегодня» → этап `BOOKED`;
   - «Госпитализация» → `HOSPITALIZED`;
   - «Скорая» → `CONTROL_PENDING` и задача на звонок через 7 дней;
   - «Отказ» и «Не подтвердилась» → сразу закрытый маршрут с причиной (для журнала и дашборда).
6. **«Не вовлечён»** — этап, а маршрут остаётся открытым: пациент может записаться позже, и маршрут продолжится.
7. **`ModelTime` — статический сдвиг на весь процесс.** Сценарий сбрасывает его для всех. Это демо-инструмент: в проде сдвиг не используется.
8. **Сбор вех воронки:** «Получили уведомление» — любое сообщение маршрута в статусе `DELIVERED` или `READ` (не только первое).
9. **При поступлении протоколов с экстренной находкой** (в том числе демо 08 и 09 при `DEMO_SEED=true`) эскалация стартует сразу, и через 15 минут реального времени появятся задачи. Так и задумано.
10. **Флага включения и выключения модуля нет.** Модуль выключается удалением пакета `route`: карточка и старые эндпоинты продолжат работать.

## 5. Известные риски

- `RouteTimer`, `Route.milestones` и другие `jsonb`-поля полагаются на отслеживание изменений JSON-типов Hibernate 6 (как в существующем коде с `flags`).
- `TimerRunner.runDue` выполняет каждый таймер в своей транзакции и защищён `synchronized`. При нескольких экземплярах бэкенда нужна блокировка в БД, но для хакатона это не нужно.
- `ScenarioService` удаляет маршруты, сообщения, задачи, эскалации и таймеры **своего** пациента и возвращает его находки в `SUGGESTED`. Записи журнала остаются: журнал неизменяем.
- `Spring Data`: производные запросы (`findFirstByFindingIdAndStepNot`, `findByPatientIdAndOpenTrue` и др.) нужно проверить при старте приложения.

## 6. Как проверить вживую

1. Собрать и запустить бэкенд (`DEMO_SEED` не важен), убедиться, что старые тесты и новые `route/*Test` зелёные.
2. `GET /api/sim/scenarios` — пять сценариев: `happy-path`, `not-engaged`, `no-show`, `emergency`, `emergency-timeout`.
3. `POST /api/sim/scenarios/happy-path/start` с телом `{"manual": true}`, затем повторять `POST /api/sim/scenarios/{runId}/next` и смотреть:
   - `GET /api/patients/{id}` — `routes`, баннер;
   - `GET /api/routes/{routeId}/notifications`;
   - `GET /api/tasks`;
   - `GET /api/journal`;
   - `GET /api/dashboard/funnel`.
4. Отдельно проверить:
   - повтор того же `eventId` на `/api/integration/route-events` → 200 `duplicate`;
   - неподходящее событие → 409, и запись `EVENT_REJECTED` в журнале;
   - ручную отправку без `confirm` после автоматического сообщения → 409 `CONFIRM_REQUIRED`;
   - что `/api/integration/events` по-прежнему уходит в ML.

## 7. TODO для того, кто собирает

- [ ] Собрать, исправить ошибки компиляции, если будут.
- [ ] Запустить тесты; дописать сервисные тесты с Mockito или Testcontainers из раздела 18 ТЗ (создание и сверка маршрута, лестница эскалации, госпитализация, идемпотентность, аннулирование).
- [ ] Обновить `docs/openapi.yaml`: заменить старые схемы `Route`, `RouteStep`, `StepStatus` моделью из `RouteDtos`; экспортировать `docs/openapi-runtime.yaml` из `/v3/api-docs`.
- [ ] Пройти чек-лист раздела 19 ТЗ.
- [ ] Перечислить пункты раздела 4 этого документа, которые не согласованы с медэкспертом.
