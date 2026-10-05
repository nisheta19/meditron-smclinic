package ru.meditron.routing.route.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import ru.meditron.routing.domain.Finding;
import ru.meditron.routing.domain.FindingLevel;
import ru.meditron.routing.domain.FindingStatus;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.exception.ConflictException;
import ru.meditron.routing.exception.NotFoundException;
import ru.meditron.routing.repository.FindingRepository;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.ChainType;
import ru.meditron.routing.route.domain.Escalation;
import ru.meditron.routing.route.domain.PendingVisit;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.domain.RouteStage;
import ru.meditron.routing.route.domain.RouteTimer;
import ru.meditron.routing.route.repo.EscalationRepository;
import ru.meditron.routing.route.repo.RouteRepository;
import ru.meditron.routing.time.ModelTime;

/**
 * Экстренная эскалация — лестница (раздел 9): подтверждение координатором → «Принял в работу» по уровням →
 * «Связался с пациентом» → закрытие с обязательным исходом. Пациенту система ничего не пишет.
 */
@Service
public class EscalationService {

    public static final String GROUP = "escalation";

    private final EscalationRepository escalations;
    private final FindingRepository findings;
    private final RouteRepository routes;
    private final TimerService timers;
    private final TaskService tasks;
    private final JournalService journal;
    private final RouteConfig config;
    private final RouteStateService state;
    private final ChainService chains;

    public EscalationService(EscalationRepository escalations, FindingRepository findings, RouteRepository routes,
                             TimerService timers, TaskService tasks, JournalService journal, RouteConfig config,
                             RouteStateService state, ChainService chains) {
        this.escalations = escalations;
        this.findings = findings;
        this.routes = routes;
        this.timers = timers;
        this.tasks = tasks;
        this.journal = journal;
        this.config = config;
        this.state = state;
        this.chains = chains;
    }

    /** 9.1: экстренная находка пришла от ML (SUGGESTED) — эскалация стартует сразу. */
    public void startForProtocol(UUID protocolId) {
        for (Finding f : findings.findByProtocolId(protocolId)) {
            if (f.getLevel() == FindingLevel.EMERGENCY && f.getStatus() == FindingStatus.SUGGESTED
                    && escalations.findFirstByFindingIdAndStepNot(f.getId(), Escalation.Step.CLOSED).isEmpty()) {
                start(f);
            }
        }
    }

    public Escalation start(Finding f) {
        Escalation e = new Escalation();
        e.setPatientId(f.getPatient().getId());
        e.setProtocolId(f.getProtocol() == null ? null : f.getProtocol().getId());
        e.setFindingId(f.getId());
        e.setFindingName(f.getName());
        e.setDutySpecialty(f.getTargetSpecialty());
        history(e, "STARTED", "SYSTEM", null);
        e = escalations.save(e);
        timers.schedule(RouteTimer.Kind.ESCALATION_CONFIRM, GROUP, ModelTime.now().plus(config.duration("/escalation/confirmTimeout")),
                e.getPatientId(), null, e.getId(), Map.of());
        journal.entry("SYSTEM", "ESCALATION_STARTED").basis("Экстренная находка " + f.getCode() + " (level EMERGENCY)")
                .patient(e.getPatientId()).finding(f.getId()).escalation(e.getId()).save();
        return e;
    }

    /** Координатор подтвердил (✓) или отклонил (✕) экстренную находку. Вызывается при сверке находок. */
    public void onFindingsChanged(UUID patientId) {
        List<Escalation> current = new ArrayList<>(escalations.findByPatientIdOrderByStartedAtDesc(patientId));
        Map<UUID, Finding> byId = new LinkedHashMap<>();
        for (Finding f : findings.findByPatientIdOrderByCreatedAtDesc(patientId)) {
            byId.put(f.getId(), f);
            if (f.getLevel() == FindingLevel.EMERGENCY && f.getStatus() == FindingStatus.CONFIRMED
                    && (f.getProtocol() == null || !f.getProtocol().isSuperseded()
                        && f.getProtocol().getStatus() != ru.meditron.routing.domain.ProcessingStatus.ANNULLED)
                    && current.stream().noneMatch(e -> e.getFindingId().equals(f.getId())
                        && (e.getStep() != Escalation.Step.CLOSED || e.getOutcome() != null))) {
                current.add(start(f));
            }
        }
        for (Escalation e : current) {
            if (e.getStep() == Escalation.Step.CLOSED) {
                continue;
            }
            Finding f = byId.get(e.getFindingId());
            if (f == null || f.getStatus() == FindingStatus.REMOVED || f.getLevel() != FindingLevel.EMERGENCY) {
                close(e, null, null, "Находка удалена");
            } else if (f.getStatus() == FindingStatus.REJECTED) {
                close(e, null, null, "Не подтверждено координатором");
            } else if (f.getStatus() == FindingStatus.CONFIRMED && e.getConfirmedAt() == null) {
                e.setConfirmedAt(ModelTime.now());
                e.setConfirmedBy(f.getReviewedBy());
                history(e, "CONFIRMED", "COORDINATOR", f.getReviewedBy());
                if (e.getStep() == Escalation.Step.AWAITING_CONFIRMATION
                        || e.getStep() == Escalation.Step.AWAITING_ACCEPT) timers.cancelEscalation(e.getId(), GROUP);
                if (e.getStep() == Escalation.Step.AWAITING_CONFIRMATION) {
                    e.setStep(Escalation.Step.AWAITING_ACCEPT);
                    e.setLadderLevel(0);
                    notifyLevel(e, 0, "Координатор подтвердил экстренную находку");
                } else if (e.getStep() == Escalation.Step.AWAITING_ACCEPT) {
                    scheduleAcceptTimeout(e); // уже ушло дежурному по таймауту подтверждения — лестница продолжается
                }
                escalations.save(e);
            }
        }
    }

    // ------------------------------------------------------------------ таймеры

    public void onConfirmTimeout(Escalation e) {
        if (e.getStep() != Escalation.Step.AWAITING_CONFIRMATION) {
            return;
        }
        e.setConfirmTimedOut(true);
        e.setStep(Escalation.Step.AWAITING_ACCEPT);
        e.setLadderLevel(0);
        for (String role : config.strings("/escalation/onConfirmTimeout")) {
            tasks.create("EMERGENCY_ACCEPT", role, e.getPatientId(), null, e.getId(), taskText(e, true), null,
                    "Координатор не подтвердил экстренную находку за 15 минут");
        }
        history(e, "CONFIRM_TIMEOUT", "SYSTEM", null);
        scheduleAcceptTimeout(e);
        escalations.save(e);
    }

    public void onAcceptTimeout(Escalation e, int level) {
        if (e.getStep() != Escalation.Step.AWAITING_ACCEPT || e.getLadderLevel() != level) {
            return;
        }
        JsonNode ladder = config.at("/escalation/ladder");
        if (level + 1 >= ladder.size()) {
            return;
        }
        e.setLadderLevel(level + 1);
        history(e, "ACCEPT_TIMEOUT", "SYSTEM", ladder.get(level).path("role").asText());
        notifyLevel(e, level + 1, "Нет «Принял в работу» на уровне " + ladder.get(level).path("role").asText());
        escalations.save(e);
    }

    public void onContactTimeout(Escalation e) {
        if (e.getStep() != Escalation.Step.AWAITING_CONTACT) {
            return;
        }
        tasks.create("EMERGENCY_CONTACT_OVERDUE", config.text("/escalation/contactTimeoutRole", "HEAD_OF_DEPARTMENT"),
                e.getPatientId(), null, e.getId(), "Нет отметки «Связался с пациентом» в течение часа: " + e.getFindingName(),
                null, "Таймаут контакта 1 ч");
        history(e, "CONTACT_TIMEOUT", "SYSTEM", null);
        escalations.save(e);
    }

    private void notifyLevel(Escalation e, int level, String basis) {
        JsonNode step = config.at("/escalation/ladder").get(level);
        if (!(level == 0 && e.isConfirmTimedOut())) { // при таймауте подтверждения дежурный уже получил задачу
            tasks.create("EMERGENCY_ACCEPT", step.path("role").asText(), e.getPatientId(), null, e.getId(),
                    taskText(e, false), null, basis);
        }
        scheduleAcceptTimeout(e);
    }

    private void scheduleAcceptTimeout(Escalation e) {
        JsonNode step = config.at("/escalation/ladder").get(e.getLadderLevel());
        if (step != null && step.hasNonNull("timeout")) {
            timers.schedule(RouteTimer.Kind.ESCALATION_ACCEPT, GROUP,
                    ModelTime.now().plus(RouteConfig.parse(step.path("timeout").asText())),
                    e.getPatientId(), null, e.getId(), Map.of("level", e.getLadderLevel()));
        }
    }

    // ------------------------------------------------------------------ действия персонала

    public Escalation accept(String id, String role, String by) {
        Escalation e = find(id);
        if (e.getStep() != Escalation.Step.AWAITING_ACCEPT) {
            throw new ConflictException("ESCALATION_STEP", "Сейчас нельзя «Принял в работу»: шаг " + e.getStep());
        }
        e.setAcceptedAt(ModelTime.now());
        e.setAcceptedBy(by);
        e.setAcceptedRole(role);
        e.setStep(Escalation.Step.AWAITING_CONTACT);
        timers.cancelEscalation(e.getId(), GROUP);
        timers.schedule(RouteTimer.Kind.ESCALATION_CONTACT, GROUP, ModelTime.now().plus(config.duration("/escalation/contactTimeout")),
                e.getPatientId(), null, e.getId(), Map.of());
        history(e, "ACCEPTED", role, by);
        journal.entry(role == null ? "DUTY_DOCTOR" : role, "ESCALATION_ACCEPTED").by(by).basis("Решение человека")
                .patient(e.getPatientId()).escalation(e.getId()).save();
        return escalations.save(e);
    }

    public Escalation contacted(String id, String by) {
        Escalation e = find(id);
        if (e.getStep() != Escalation.Step.AWAITING_CONTACT) {
            throw new ConflictException("ESCALATION_STEP", "Сначала нужно «Принял в работу»");
        }
        e.setContactedAt(ModelTime.now());
        e.setContactedBy(by);
        e.setStep(Escalation.Step.AWAITING_OUTCOME);
        timers.cancelEscalation(e.getId(), GROUP);
        history(e, "CONTACTED", e.getAcceptedRole(), by);
        journal.entry(e.getAcceptedRole() == null ? "DUTY_DOCTOR" : e.getAcceptedRole(), "ESCALATION_CONTACTED").by(by)
                .basis("Решение человека").patient(e.getPatientId()).escalation(e.getId()).save();
        return escalations.save(e);
    }

    /** 9.3: закрытие только с исходом; дальше маршрут по исходу. */
    public Escalation closeWithOutcome(String id, String outcome, String comment, String by) {
        Escalation e = find(id);
        if (e.getStep() != Escalation.Step.AWAITING_OUTCOME) {
            throw new ConflictException("ESCALATION_STEP", "Эскалацию нельзя закрыть на шаге " + e.getStep());
        }
        JsonNode o = config.at("/escalation/outcomes/" + outcome);
        if (o.isMissingNode()) {
            throw new BadRequestException("UNKNOWN_OUTCOME", "Неизвестный исход: " + outcome);
        }
        if (o.path("commentRequired").asBoolean(false) && (comment == null || comment.isBlank())) {
            throw new BadRequestException("COMMENT_REQUIRED", "Для исхода «" + o.path("title").asText() + "» комментарий обязателен");
        }
        close(e, outcome, comment, null);
        journal.entry(e.getAcceptedRole() == null ? "DUTY_DOCTOR" : e.getAcceptedRole(), "ESCALATION_CLOSED").by(by)
                .basis("Исход: " + o.path("title").asText()).patient(e.getPatientId()).escalation(e.getId())
                .detail("comment", comment).save();
        routeAfterOutcome(e, outcome, comment);
        return escalations.save(e);
    }

    private void routeAfterOutcome(Escalation e, String outcome, String comment) {
        String profile = config.profileForDuty(e.getDutySpecialty()).orElse(e.getDutySpecialty());
        boolean continuing = !"PATIENT_REFUSED".equals(outcome) && !"FINDING_NOT_CONFIRMED".equals(outcome);
        Route r = continuing ? routes.findByPatientIdAndOpenTrue(e.getPatientId()).stream()
                .filter(existing -> java.util.Objects.equals(profile, existing.getSpecialty())).findFirst().orElseGet(Route::new)
                : new Route();
        if (r.getId() != null) {
            timers.cancelRoute(r.getId(), null);
            tasks.cancelForRoute(r.getId(), "Маршрут продолжен после экстренного события");
        }
        r.setPatientId(e.getPatientId());
        r.setProtocolId(e.getProtocolId());
        r.setSpecialty(profile);
        r.setTemplateCode("URGENT_ESCALATION");
        r.setChainType(ChainType.NEAR);
        if (!r.getFindingIds().contains(e.getFindingId().toString()))
            r.getFindingIds().add(e.getFindingId().toString());
        r.setDetectedOn(ModelTime.today());
        findings.findById(e.getFindingId()).ifPresent(f -> {
            if (f.getProtocol() != null) {
                r.setDetectedOn(f.getProtocol().getStudyDate());
                r.setStudyType(f.getProtocol().getStudyType() == null ? null : f.getProtocol().getStudyType().name());
            }
        });
        r.setDueAt(ModelTime.now());
        r.milestone("CREATED");
        String basis = "Исход экстренной эскалации: " + outcome;
        switch (outcome) {
            case "COMING_TODAY" -> {
                r.setStage(RouteStage.BOOKED);
                r.setPendingVisit(PendingVisit.CONSULTATION);
            }
            case "HOSPITALIZED" -> {
                r.setStage(RouteStage.HOSPITALIZED);
                r.milestone("HOSPITALIZED");
            }
            case "AMBULANCE" -> {
                r.setStage(RouteStage.CONTROL_PENDING);
                r.setPendingVisit(PendingVisit.CONTROL);
                r.setDueAt(ModelTime.now().plus(config.duration("/escalation/ambulanceCallAfter")));
            }
            case "PATIENT_REFUSED", "FINDING_NOT_CONFIRMED" -> {
                r.setStage(RouteStage.CLOSED);
                r.setOpen(false);
                r.setClosedAt(ModelTime.now());
                r.setCloseReason("PATIENT_REFUSED".equals(outcome)
                        ? ru.meditron.routing.route.domain.CloseReason.PATIENT_REFUSED
                        : ru.meditron.routing.route.domain.CloseReason.FINDING_NOT_CONFIRMED);
                r.setTacticComment(comment);
            }
            default -> throw new IllegalStateException(outcome);
        }
        r.getStageHistory().add(Map.of("stage", r.getStage().name(), "at", ModelTime.now().toString(), "basis", basis));
        Route saved = routes.save(r);
        e.setRouteId(saved.getId());
        journal.entry("SYSTEM", "ROUTE_CREATED").basis(basis).patient(e.getPatientId()).route(saved.getId())
                .escalation(e.getId()).detail("specialty", profile).save();
        if ("AMBULANCE".equals(outcome)) {
            timers.schedule(RouteTimer.Kind.AMBULANCE_CALL, ChainService.GROUP,
                    ModelTime.now().plus(config.duration("/escalation/ambulanceCallAfter")),
                    saved.getPatientId(), saved.getId(), null, Map.of());
        }
    }

    /** Исход «скорая»: через 7 дней — звонок координатора и цепочка ближнего срока (9.3). */
    public void onAmbulanceCall(Route r) {
        if (!r.isOpen() || r.getStage() != RouteStage.CONTROL_PENDING) {
            return;
        }
        chains.start(r, ChainType.NEAR, ModelTime.now(), false, "Контрольный визит после экстренного случая");
        tasks.create("CALL_PATIENT", "COORDINATOR", r.getPatientId(), r.getId(), null,
                "Пациента увезла скорая 7 дней назад: узнать, выписан ли, и записать на контрольный визит. "
                        + chains.callScript(r), Duration.ofDays(1), "Исход экстренной эскалации «Вызвана скорая»");
    }

    /** Протокол аннулирован или исправлен — эскалация по нему закрывается (5.4). */
    public void onProtocolClosed(UUID protocolId, String note) {
        for (Escalation e : escalations.findByProtocolId(protocolId)) {
            if (e.getStep() != Escalation.Step.CLOSED) {
                close(e, null, null, note);
            }
        }
    }

    private void close(Escalation e, String outcome, String comment, String note) {
        timers.cancelEscalation(e.getId(), null);
        tasks.cancelForEscalation(e.getId(), note != null ? note : "Эскалация закрыта");
        e.setStep(Escalation.Step.CLOSED);
        e.setClosedAt(ModelTime.now());
        e.setOutcome(outcome);
        e.setOutcomeComment(comment);
        e.setCloseNote(note);
        history(e, "CLOSED", "SYSTEM", outcome != null ? outcome : note);
        escalations.save(e);
        if (note != null) {
            journal.entry("SYSTEM", "ESCALATION_CLOSED").basis(note).patient(e.getPatientId()).escalation(e.getId()).save();
        }
    }

    private Escalation find(String id) {
        return escalations.findById(ru.meditron.routing.service.Ids.parse(id, "RESOURCE"))
                .orElseThrow(() -> new NotFoundException("ESCALATION_NOT_FOUND", "Эскалация " + id + " не найдена"));
    }

    private String taskText(Escalation e, boolean unconfirmed) {
        return (unconfirmed ? "Экстренная находка, координатор не подтвердил за 15 минут: " : "Экстренная находка: ")
                + e.getFindingName() + " — " + e.getDutySpecialty() + ". Нажмите «Принял в работу». Пациенту система не пишет";
    }

    private void history(Escalation e, String step, String role, String by) {
        Map<String, Object> h = new LinkedHashMap<>();
        h.put("step", step);
        h.put("at", ModelTime.now().toString());
        h.put("role", role);
        h.put("by", by);
        e.getHistory().add(h);
    }

    public Instant deadline(Escalation e) {
        Instant base;
        Duration d;
        switch (e.getStep()) {
            case AWAITING_CONFIRMATION -> { base = e.getStartedAt(); d = config.duration("/escalation/confirmTimeout"); }
            case AWAITING_CONTACT -> { base = e.getAcceptedAt(); d = config.duration("/escalation/contactTimeout"); }
            case AWAITING_ACCEPT -> {
                JsonNode step = config.at("/escalation/ladder").get(e.getLadderLevel());
                if (step == null || !step.hasNonNull("timeout") || e.getHistory().isEmpty()) {
                    return null;
                }
                base = Instant.parse(String.valueOf(e.getHistory().get(e.getHistory().size() - 1).get("at")));
                d = RouteConfig.parse(step.path("timeout").asText());
            }
            default -> { return null; }
        }
        return base == null ? null : base.plus(d);
    }
}
