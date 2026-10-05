package ru.meditron.routing.route.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import ru.meditron.routing.domain.Finding;
import ru.meditron.routing.domain.FindingStatus;
import ru.meditron.routing.domain.Patient;
import ru.meditron.routing.dto.ConfirmFindingsRequest;
import ru.meditron.routing.dto.MlResultRequest;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.exception.NotFoundException;
import ru.meditron.routing.repository.FindingRepository;
import ru.meditron.routing.repository.PatientRepository;
import ru.meditron.routing.repository.ProtocolRepository;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.Escalation;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.domain.RouteNotification;
import ru.meditron.routing.route.dto.RouteDtos.CrmCallback;
import ru.meditron.routing.route.dto.RouteDtos.RouteEvent;
import ru.meditron.routing.route.dto.RouteDtos.ScenarioRunDto;
import ru.meditron.routing.route.repo.*;
import ru.meditron.routing.service.FindingService;
import ru.meditron.routing.service.MlIngestionService;
import ru.meditron.routing.time.ModelTime;

/**
 * Сценарии для видео (раздел 14): проигрываются сами, с паузой между шагами, или по шагу на запрос.
 * Пациенты берутся из встроенных демо-файлов независимо от DEMO_SEED; пациентов из скрипта коллег не трогают.
 * Перед запуском состояние пациента сценария и модельное время сбрасываются.
 */
@Service
public class ScenarioService {

    private static final Logger log = LoggerFactory.getLogger(ScenarioService.class);

    private record Step(String title, Consumer<Ctx> action) {
    }

    private record Definition(String code, String title, String externalId, String demoFile, List<Step> steps) {
    }

    /** Состояние одного запуска. */
    private static final class Ctx {
        final String runId = UUID.randomUUID().toString();
        final Definition def;
        final List<String> log = Collections.synchronizedList(new ArrayList<>());
        UUID patientId;
        volatile int step;
        volatile boolean finished;
        volatile String error;
        String doctor = "Координатор (сценарий)";

        Ctx(Definition def) {
            this.def = def;
        }
    }

    private final Map<String, Definition> scenarios = new LinkedHashMap<>();
    private final Map<String, Ctx> runs = new ConcurrentHashMap<>();
    private final ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "scenario-runner");
        t.setDaemon(true);
        return t;
    });

    @org.springframework.beans.factory.annotation.Autowired
    private RouteWriteLock writeLock;
    private final PatientRepository patients;
    private final ProtocolRepository protocols;
    private final FindingRepository findings;
    private final FindingService findingService;
    private final MlIngestionService ingestion;
    private final ObjectMapper json;
    private final RouteRepository routes;
    private final RouteNotificationRepository notifications;
    private final StaffTaskRepository tasks;
    private final EscalationRepository escalations;
    private final RouteTimerRepository timers;
    private final AppointmentRepository appointments;
    private final RouteEventService events;
    private final EscalationService escalationService;
    private final TimerRunner timerRunner;
    private final ScheduleService schedule;
    private final RouteConfig config;
    private final TransactionTemplate tx;

    public ScenarioService(PatientRepository patients, ProtocolRepository protocols, FindingRepository findings,
                           FindingService findingService, MlIngestionService ingestion, ObjectMapper json,
                           RouteRepository routes, RouteNotificationRepository notifications, StaffTaskRepository tasks,
                           EscalationRepository escalations, RouteTimerRepository timers,
                           AppointmentRepository appointments, RouteEventService events,
                           EscalationService escalationService, TimerRunner timerRunner, ScheduleService schedule,
                           RouteConfig config, PlatformTransactionManager txManager) {
        this.patients = patients;
        this.protocols = protocols;
        this.findings = findings;
        this.findingService = findingService;
        this.ingestion = ingestion;
        this.json = json;
        this.routes = routes;
        this.notifications = notifications;
        this.tasks = tasks;
        this.escalations = escalations;
        this.timers = timers;
        this.appointments = appointments;
        this.events = events;
        this.escalationService = escalationService;
        this.timerRunner = timerRunner;
        this.schedule = schedule;
        this.config = config;
        this.tx = new TransactionTemplate(txManager);
        define();
    }

    // ------------------------------------------------------------------ определения (раздел 14)

    private void define() {
        add(new Definition("happy-path", "Счастливый путь: полип эндометрия", "mis-0001", "01-", List.of(
                new Step("Координатор подтвердил находки → маршрут создан", this::confirmAll),
                new Step("+1 мин: первое сообщение пациенту", c -> advance(Duration.ofMinutes(2))),
                new Step("CRM: доставлено", c -> crm(c, "DELIVERED")),
                new Step("CRM: прочитано", c -> crm(c, "READ")),
                new Step("Пациент записался по ссылке", this::bookFirstSlot),
                new Step("Приём состоялся", c -> event(c, "VISIT_COMPLETED", Map.of())),
                new Step("Врач: оперативное лечение показано", c -> event(c, "TACTIC_SELECTED", Map.of("tactic", "SURGERY_INDICATED"))),
                new Step("Направление на госпитализацию создано", c -> event(c, "HOSPITALIZATION_REFERRED", Map.of())),
                new Step("Назначена дата госпитализации", c -> event(c, "HOSPITALIZATION_DATE_SET", Map.of("date", ModelTime.today().plusDays(5).toString()))),
                new Step("+5 дней: госпитализирован", c -> { advance(Duration.ofDays(5)); event(c, "HOSPITALIZED", Map.of()); }),
                new Step("Операция выполнена", c -> event(c, "SURGERY_DONE", Map.of())),
                new Step("+1 день: выписан без записи на контроль (сообщение и задача)", c -> {
                    advance(Duration.ofDays(1));
                    event(c, "DISCHARGED", Map.of("controlVisitBooked", false));
                }),
                new Step("Пациент записался на контрольный приём", this::bookFirstSlot),
                new Step("+7 дней: контрольный визит состоялся → маршрут завершён", c -> {
                    advance(Duration.ofDays(7));
                    event(c, "VISIT_COMPLETED", Map.of());
                }))));

        add(new Definition("not-engaged", "Пациент не вовлекается: ЖКБ", "mis-0002", "02-", List.of(
                new Step("Координатор подтвердил находки → маршрут создан", this::confirmAll),
                new Step("+1 мин: первое сообщение", c -> advance(Duration.ofMinutes(2))),
                new Step("+24 ч: напоминание", c -> advance(Duration.ofHours(24))),
                new Step("+72 ч от начала: напоминание", c -> advance(Duration.ofHours(48))),
                new Step("5-й день: задача координатору позвонить", c -> advance(Duration.ofDays(2))),
                new Step("14-й день: сообщение с кнопками", c -> advance(Duration.ofDays(9))),
                new Step("30-й день: «не вовлечён»", c -> advance(Duration.ofDays(16))))));

        add(new Definition("no-show", "Неявка: BI-RADS 4", "mis-0004", "04-", List.of(
                new Step("Координатор подтвердил находки → маршрут создан", this::confirmAll),
                new Step("+1 мин: первое сообщение", c -> advance(Duration.ofMinutes(2))),
                new Step("Пациент записался", this::bookFirstSlot),
                new Step("Пациент не пришёл", c -> event(c, "NO_SHOW", Map.of())),
                new Step("+30 мин: сообщение после неявки", c -> advance(Duration.ofMinutes(31))),
                new Step("+24 ч: напоминание", c -> advance(Duration.ofHours(24))),
                new Step("Пациент перезаписался", this::bookFirstSlot),
                new Step("Приём состоялся", c -> event(c, "VISIT_COMPLETED", Map.of())))));

        add(new Definition("emergency", "Экстренная находка: тромбофлебит у соустья", "mis-0008", "08-", List.of(
                new Step("Эскалация запущена (пациенту система не пишет)", this::startEscalation),
                new Step("Координатор подтвердил экстренную находку", this::confirmAll),
                new Step("Дежурный врач: «Принял в работу»", c -> escalation(c, "accept")),
                new Step("Дежурный врач: «Связался с пациентом»", c -> escalation(c, "contacted")),
                new Step("Исход: приедет в клинику сегодня", c -> escalation(c, "close")),
                new Step("Приём состоялся", c -> event(c, "VISIT_COMPLETED", Map.of())),
                new Step("Врач: оперативное лечение показано", c -> event(c, "TACTIC_SELECTED", Map.of("tactic", "SURGERY_INDICATED"))))));

        add(new Definition("emergency-timeout", "Экстренная: координатор не подтвердил за 15 минут", "mis-0008", "08-", List.of(
                new Step("Эскалация запущена", this::startEscalation),
                new Step("+16 мин: задачи дежурному врачу и старшему координатору", c -> advance(Duration.ofMinutes(16))),
                new Step("+11 мин: никто не принял — задача переходит дальше по лестнице", c -> advance(Duration.ofMinutes(11))))));
    }

    private void add(Definition d) {
        scenarios.put(d.code(), d);
    }

    // ------------------------------------------------------------------ запуск

    public List<Map<String, Object>> list() {
        List<Map<String, Object>> out = new ArrayList<>();
        scenarios.values().forEach(d -> out.add(Map.of("code", d.code(), "title", d.title(),
                "patientExternalId", d.externalId(), "steps", d.steps().stream().map(Step::title).toList())));
        return out;
    }

    public ScenarioRunDto start(String code, Integer delaySeconds, boolean manual) {
        Definition d = scenarios.get(code);
        if (d == null) {
            throw new NotFoundException("SCENARIO_NOT_FOUND", "Сценарий " + code + " не найден");
        }
        Ctx c = new Ctx(d);
        runs.put(c.runId, c);
        prepare(c);
        if (!manual) {
            int delay = delaySeconds != null ? delaySeconds : config.integer("/scenarios/defaultStepDelaySeconds", 3);
            executor.submit(() -> {
                while (!c.finished) {
                    runNext(c);
                    sleep(delay);
                }
            });
        }
        return dto(c);
    }

    public ScenarioRunDto next(String runId) {
        Ctx c = runs.get(runId);
        if (c == null) {
            throw new NotFoundException("RUN_NOT_FOUND", "Запуск " + runId + " не найден");
        }
        runNext(c);
        return dto(c);
    }

    public ScenarioRunDto status(String runId) {
        Ctx c = runs.get(runId);
        if (c == null) {
            throw new NotFoundException("RUN_NOT_FOUND", "Запуск " + runId + " не найден");
        }
        return dto(c);
    }

    private synchronized void runNext(Ctx c) {
        if (c.finished) {
            return;
        }
        Step s = c.def.steps().get(c.step);
        try {
            tx.executeWithoutResult(status -> { writeLock.acquire(); s.action().accept(c); });
            timerRunner.runDue();
            c.log.add(ModelTime.now() + " — " + s.title());
        } catch (RuntimeException e) {
            c.error = s.title() + ": " + e.getMessage();
            c.finished = true;
            log.warn("Сценарий {} остановлен на шаге «{}»: {}", c.def.code(), s.title(), e.getMessage());
            return;
        }
        c.step++;
        if (c.step >= c.def.steps().size()) {
            c.finished = true;
        }
    }

    /** Сброс пациента сценария и модельного времени; загрузка пациента из демо-файла, если его нет. */
    private void prepare(Ctx c) {
        ModelTime.reset();
        tx.executeWithoutResult(status -> {
            writeLock.acquire();
            Patient p = patients.findByExternalId(c.def.externalId()).orElse(null);
            if (p == null) {
                loadDemo(c.def.demoFile());
                p = patients.findByExternalId(c.def.externalId())
                        .orElseThrow(() -> new IllegalStateException("Демо-пациент " + c.def.externalId() + " не загрузился"));
            }
            c.patientId = p.getId();
            for (Route r : routes.findByPatientIdOrderByCreatedAtDesc(p.getId())) {
                appointments.deleteAll(appointments.findByRouteIdOrderByCreatedAtDesc(r.getId()));
            }
            notifications.deleteAll(notifications.findByPatientIdOrderBySentAtDesc(p.getId()));
            tasks.deleteAll(tasks.findByPatientIdOrderByCreatedAtDesc(p.getId()));
            escalations.deleteAll(escalations.findByPatientIdOrderByStartedAtDesc(p.getId()));
            timers.deleteAll(timers.findByPatientId(p.getId()));
            routes.deleteAll(routes.findByPatientIdOrderByCreatedAtDesc(p.getId()));
            for (Finding f : findings.findByPatientIdOrderByCreatedAtDesc(p.getId())) {
                if (f.getStatus() == FindingStatus.CONFIRMED || f.getStatus() == FindingStatus.REJECTED) {
                    f.setStatus(FindingStatus.SUGGESTED);
                    f.setReviewedBy(null);
                    f.setReviewedAt(null);
                }
            }
        });
        c.log.add("Подготовка: пациент " + c.def.externalId() + ", модельное время сброшено");
    }

    private void loadDemo(String prefix) {
        try {
            for (Resource r : new PathMatchingResourcePatternResolver().getResources("classpath:demo/*.json")) {
                if (r.getFilename() != null && r.getFilename().startsWith(prefix)) {
                    try (InputStream in = r.getInputStream()) {
                        ingestion.ingest(json.readValue(in, MlResultRequest.class));
                    }
                    return;
                }
            }
        } catch (Exception e) {
            throw new IllegalStateException("Не удалось загрузить демо-файл " + prefix + "*: " + e.getMessage(), e);
        }
        throw new IllegalStateException("Нет демо-файла " + prefix + "*.json");
    }

    // ------------------------------------------------------------------ действия шагов

    private void confirmAll(Ctx c) {
        List<String> ids = findings.findByPatientIdOrderByCreatedAtDesc(c.patientId).stream()
                .filter(f -> f.getStatus() == FindingStatus.SUGGESTED).map(f -> f.getId().toString()).toList();
        if (ids.isEmpty()) {
            throw new BadRequestException("NOTHING_TO_CONFIRM", "Нет находок для подтверждения");
        }
        findingService.confirm(c.patientId.toString(), new ConfirmFindingsRequest(ids, c.doctor));
    }

    private void startEscalation(Ctx c) {
        protocols.findByPatientIdOrderByReceivedAtDesc(c.patientId).stream().findFirst()
                .ifPresent(p -> escalationService.startForProtocol(p.getId()));
    }

    private void escalation(Ctx c, String action) {
        Escalation e = escalations.findByPatientIdOrderByStartedAtDesc(c.patientId).stream()
                .filter(x -> x.getStep() != Escalation.Step.CLOSED).findFirst()
                .orElseThrow(() -> new IllegalStateException("Нет открытой эскалации"));
        switch (action) {
            case "accept" -> escalationService.accept(e.getId().toString(), "DUTY_DOCTOR", "Дежурный врач (сценарий)");
            case "contacted" -> escalationService.contacted(e.getId().toString(), "Дежурный врач (сценарий)");
            case "close" -> escalationService.closeWithOutcome(e.getId().toString(), "COMING_TODAY", null, "Дежурный врач (сценарий)");
            default -> throw new IllegalArgumentException(action);
        }
    }

    private Route route(Ctx c) {
        return routes.findByPatientIdAndOpenTrue(c.patientId).stream()
                .max(Comparator.comparing(Route::getCreatedAt))
                .orElseThrow(() -> new IllegalStateException("У пациента нет открытого маршрута"));
    }

    private void event(Ctx c, String type, Map<String, Object> fields) {
        Route r = route(c);
        Object controlBooked = fields.get("controlVisitBooked");
        events.handle(new RouteEvent("scenario-" + UUID.randomUUID(), type, ModelTime.now(), null, r.getId().toString(),
                null, null, null, null, "Врач (сценарий)", (String) fields.get("tactic"), (String) fields.get("subtype"),
                null, null, null, (String) fields.get("comment"), null, (String) fields.get("date"), null, null,
                controlBooked instanceof Boolean b ? b : null, null));
    }

    private void bookFirstSlot(Ctx c) {
        Route r = route(c);
        var slots = schedule.slotsForRoute(r.getId().toString(), 1);
        if (slots.isEmpty()) {
            throw new IllegalStateException("Нет свободных слотов для " + r.getSpecialty());
        }
        events.handle(new RouteEvent("scenario-" + UUID.randomUUID(), "BOOKED", ModelTime.now(), null, r.getId().toString(),
                slots.get(0).id(), null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null));
    }

    private void crm(Ctx c, String status) {
        Route r = route(c);
        RouteNotification n = notifications.findByRouteIdOrderBySentAtDesc(r.getId()).stream().findFirst()
                .orElseThrow(() -> new IllegalStateException("Сообщений по маршруту ещё нет"));
        events.crm(new CrmCallback("scenario-" + UUID.randomUUID(), n.getId().toString(), status, ModelTime.now(), null, null));
    }

    private void advance(Duration d) {
        ModelTime.advance(d);
    }

    private ScenarioRunDto dto(Ctx c) {
        return new ScenarioRunDto(c.runId, c.def.code(), c.def.title(), c.step, c.def.steps().size(),
                c.log.isEmpty() ? null : c.log.get(c.log.size() - 1), c.finished, c.error, List.copyOf(c.log));
    }

    private static void sleep(int seconds) {
        try {
            Thread.sleep(seconds * 1000L);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
