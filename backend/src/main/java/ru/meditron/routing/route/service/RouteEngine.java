package ru.meditron.routing.route.service;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import ru.meditron.routing.domain.Finding;
import ru.meditron.routing.domain.FindingStatus;
import ru.meditron.routing.domain.ProcessingStatus;
import ru.meditron.routing.domain.Protocol;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.exception.ConflictException;
import ru.meditron.routing.repository.FindingRepository;
import ru.meditron.routing.repository.ProtocolRepository;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.Appointment;
import ru.meditron.routing.route.domain.ChainType;
import ru.meditron.routing.route.domain.CloseReason;
import ru.meditron.routing.route.domain.PendingVisit;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.domain.RouteStage;
import ru.meditron.routing.route.domain.RouteTimer;
import ru.meditron.routing.route.domain.Tactic;
import ru.meditron.routing.route.repo.AppointmentRepository;
import ru.meditron.routing.route.repo.RouteRepository;
import ru.meditron.routing.time.ModelTime;

/**
 * Ядро маршрута: создание и сверка маршрутов с находками (раздел 4), реакция на события МИС
 * (разделы 5, 7, 10), тактика врача (5.2). Медицинские решения не принимает: только ведёт пациента
 * по утверждённым правилам.
 */
@Service
public class RouteEngine {

    public static final String HOSPITALIZATION_GROUP = "hospitalization";
    public static final String VISIT_GROUP = "visit";

    /** Этапы, на которых смена типа цепочки на более срочную ещё уместна. */
    private static final Set<RouteStage> EARLY = EnumSet.of(RouteStage.CREATED, RouteStage.NOTIFIED,
            RouteStage.OBSERVATION_WAITING_US, RouteStage.OBSERVATION_WAITING_VISIT);

    private final FindingRepository findings;
    private final ProtocolRepository protocols;
    private final RouteRepository routes;
    private final AppointmentRepository appointments;
    private final ChainService chains;
    private final NotificationService notifications;
    private final TaskService tasks;
    private final TimerService timers;
    private final RouteStateService state;
    private final JournalService journal;
    private final RouteConfig config;

    public RouteEngine(FindingRepository findings, ProtocolRepository protocols, RouteRepository routes,
                       AppointmentRepository appointments, ChainService chains, NotificationService notifications,
                       TaskService tasks, TimerService timers, RouteStateService state, JournalService journal,
                       RouteConfig config) {
        this.findings = findings;
        this.protocols = protocols;
        this.routes = routes;
        this.appointments = appointments;
        this.chains = chains;
        this.notifications = notifications;
        this.tasks = tasks;
        this.timers = timers;
        this.state = state;
        this.journal = journal;
        this.config = config;
    }

    // ------------------------------------------------------------------ 4. Создание и сверка

    /**
     * Сверить маршруты пациента с его находками. Вызывается после любых действий координатора с находками
     * и после изменений протоколов. Маршрут строится только по подтверждённым находкам протоколов,
     * в которых не осталось неразобранных (SUGGESTED) находок (4.1); изменения после создания — 4.4.
     */
    public void reconcile(UUID patientId, String basis) {
        List<Finding> all = findings.findByPatientIdOrderByCreatedAtDesc(patientId);
        Map<UUID, Boolean> reviewed = new HashMap<>();
        for (Finding f : all) {
            if (f.getProtocol() != null) {
                reviewed.merge(f.getProtocol().getId(), f.getStatus() != FindingStatus.SUGGESTED, Boolean::logicalAnd);
            }
        }

        List<Finding> eligible = new ArrayList<>();
        for (Finding f : all) {
            if (f.getStatus() != FindingStatus.CONFIRMED) {
                continue;
            }
            Protocol p = f.getProtocol();
            if (p != null && (p.isSuperseded() || p.getStatus() == ProcessingStatus.ANNULLED
                    || !reviewed.getOrDefault(p.getId(), true))) {
                continue;
            }
            if ("MANUAL_REVIEW".equals(f.getRouteTemplateCode())) {
                ensureManualReviewTask(f);
                continue;
            }
            if (RoutePlanning.chainOf(f) == ChainType.EMERGENCY) {
                continue; // экстренные — через эскалацию (раздел 9)
            }
            if (f.getTargetSpecialty() == null || f.getTargetSpecialty().isBlank()) {
                continue;
            }
            eligible.add(f);
        }

        Map<UUID, Finding> byId = all.stream().collect(Collectors.toMap(Finding::getId, f -> f, (a, b) -> a));
        List<Route> open = routes.findByPatientIdAndOpenTrue(patientId);

        // 4.4: находки, которые больше не подтверждены, убираются из маршрутов.
        for (Route r : open) {
            List<String> kept = new ArrayList<>();
            List<Finding> removed = new ArrayList<>();
            for (String id : r.getFindingIds()) {
                Finding f = byId.get(UUID.fromString(id));
                if (f != null && (f.getStatus() == FindingStatus.CONFIRMED
                        || "URGENT_ESCALATION".equals(r.getTemplateCode()) && f.getStatus() == FindingStatus.SUGGESTED)
                        && (f.getProtocol() == null || !f.getProtocol().isSuperseded()
                            && f.getProtocol().getStatus() != ProcessingStatus.ANNULLED)
                        && ("URGENT_ESCALATION".equals(r.getTemplateCode()) || RoutePlanning.chainOf(f) != ChainType.EMERGENCY)
                        && !"MANUAL_REVIEW".equals(f.getRouteTemplateCode())
                        && (r.isSpecialtyAssignedByDoctor() || "URGENT_ESCALATION".equals(r.getTemplateCode())
                            || Objects.equals(r.getSpecialty(), f.getTargetSpecialty()))) {
                    kept.add(id);
                } else if (f != null) {
                    removed.add(f);
                }
            }
            if (kept.size() == r.getFindingIds().size()) {
                continue;
            }
            r.setFindingIds(kept);
            if (kept.isEmpty()) {
                state.close(r, closeReasonFor(removed), "COORDINATOR", basis + ": в маршруте не осталось находок");
            } else {
                List<Finding> rest = kept.stream().map(id -> byId.get(UUID.fromString(id))).toList();
                if (EARLY.contains(r.getStage()) && r.getTactic() == null) {
                    recalculateChain(r, rest, basis);
                }
                routes.save(r);
                journal.entry("COORDINATOR", "ROUTE_UPDATED").basis(basis + ": находка исключена")
                        .patient(patientId).route(r.getId()).detail("removed", ids(removed)).save();
            }
        }

        // Findings in a terminal clinical route are already handled. A transfer must not
        // recreate the original specialty; rejection/annulment closures may be reviewed again.
        Set<String> handled = routes.findByPatientIdOrderByCreatedAtDesc(patientId).stream()
                .filter(r -> !r.isOpen() && r.getCloseReason() != CloseReason.FINDING_REJECTED
                        && r.getCloseReason() != CloseReason.PROTOCOL_ANNULLED
                        && r.getCloseReason() != CloseReason.PROTOCOL_CORRECTED)
                .flatMap(r -> r.getFindingIds().stream()).collect(Collectors.toSet());
        eligible.removeIf(f -> handled.contains(f.getId().toString()));

        // 4.2–4.3: один маршрут на специалиста, без дублей.
        for (Map.Entry<String, List<Finding>> g : RoutePlanning.bySpecialty(eligible).entrySet()) {
            Optional<Route> existing = routes.findByPatientIdAndOpenTrue(patientId).stream()
                    .filter(r -> r.getSpecialty().equals(g.getKey())).findFirst();
            if (existing.isPresent()) {
                addFindings(existing.get(), g.getValue(), basis);
            } else {
                create(patientId, g.getKey(), g.getValue(), basis);
            }
        }
    }

    private CloseReason closeReasonFor(List<Finding> removed) {
        for (Finding f : removed) {
            String c = f.getComment() == null ? "" : f.getComment();
            if (c.startsWith("PROTOCOL_ANNULLED")) {
                return CloseReason.PROTOCOL_ANNULLED;
            }
            if (c.startsWith("PROTOCOL_CORRECTED")) {
                return CloseReason.PROTOCOL_CORRECTED;
            }
        }
        return CloseReason.FINDING_REJECTED;
    }

    private Route create(UUID patientId, String specialty, List<Finding> group, String basis) {
        Finding lead = RoutePlanning.mostUrgent(group);
        ChainType chain = RoutePlanning.chainOf(lead);
        Instant now = ModelTime.now();
        Route r = new Route();
        r.setPatientId(patientId);
        r.setSpecialty(specialty);
        r.setTemplateCode(lead.getRouteTemplateCode());
        r.setChainType(chain);
        r.setFindingIds(new ArrayList<>(ids(group)));
        if (lead.getProtocol() != null) {
            r.setProtocolId(lead.getProtocol().getId());
            r.setStudyType(lead.getProtocol().getStudyType() == null ? null : lead.getProtocol().getStudyType().name());
            r.setDetectedOn(lead.getProtocol().getStudyDate());
        } else {
            r.setDetectedOn(ModelTime.today());
        }
        r.setDueAt(now.plus(Duration.ofDays(RoutePlanning.minDays(group))));
        if (chain == ChainType.OBSERVATION) {
            r.setControlAt(r.getDueAt());
            r.setStage(RouteStage.OBSERVATION_WAITING_US);
            r.setPendingVisit(PendingVisit.ULTRASOUND);
        } else {
            r.setStage(RouteStage.CREATED);
            r.setPendingVisit(PendingVisit.CONSULTATION);
        }
        r.getStageHistory().add(Map.of("stage", r.getStage().name(), "at", now.toString(), "basis", basis));
        r.milestone("CREATED");
        r = routes.save(r);
        journal.entry("SYSTEM", "ROUTE_CREATED").basis(basis + "; правило " + lead.getMatchedRule())
                .patient(patientId).route(r.getId()).detail("specialty", specialty).detail("chain", chain)
                .detail("findings", ids(group)).save();
        chains.start(r, chain, now, true, "Маршрут создан");
        return r;
    }

    private void addFindings(Route r, List<Finding> group, String basis) {
        List<Finding> added = group.stream().filter(f -> !r.getFindingIds().contains(f.getId().toString())).toList();
        if (added.isEmpty()) {
            recalculateChain(r, group, basis);
            return;
        }
        added.forEach(f -> r.getFindingIds().add(f.getId().toString()));
        Instant newDue = ModelTime.now().plus(Duration.ofDays(RoutePlanning.minDays(added)));
        if (r.getDueAt() == null || newDue.isBefore(r.getDueAt())) {
            r.setDueAt(newDue);
        }
        ChainType addedChain = RoutePlanning.chainOf(RoutePlanning.mostUrgent(added));
        boolean upgrade = RoutePlanning.rank(addedChain) < RoutePlanning.rank(r.getChainType()) && EARLY.contains(r.getStage());
        if (upgrade) {
            r.setChainType(addedChain);
            r.setTemplateCode(RoutePlanning.mostUrgent(added).getRouteTemplateCode());
            if (addedChain != ChainType.OBSERVATION) {
                r.setControlAt(null);
                r.setPendingVisit(PendingVisit.CONSULTATION);
            }
        }
        routes.save(r);
        journal.entry("SYSTEM", "ROUTE_UPDATED").basis(basis + "; маршрут к этому специалисту уже открыт (4.3)")
                .patient(r.getPatientId()).route(r.getId()).detail("added", ids(added))
                .detail("dueAt", r.getDueAt()).detail("chainUpgraded", upgrade).save();
        if (upgrade) {
            if (r.getStage() != RouteStage.CREATED && r.getStage() != RouteStage.NOTIFIED) {
                state.moveTo(r, RouteStage.CREATED, "SYSTEM", "Тип маршрута стал срочнее");
            }
            chains.start(r, addedChain, ModelTime.now(), true, "Тип маршрута стал срочнее");
        }
    }

    private void recalculateChain(Route r, List<Finding> group, String basis) {
        if (group.isEmpty() || !EARLY.contains(r.getStage()) || r.getTactic() != null
                || r.isSpecialtyAssignedByDoctor() || r.hasMilestone("CONTROL_ULTRASOUND")) return;
        Finding lead = RoutePlanning.mostUrgent(group);
        ChainType chain = RoutePlanning.chainOf(lead);
        Instant due = r.getCreatedAt().plus(Duration.ofDays(RoutePlanning.minDays(group)));
        boolean dueChanged = !Objects.equals(due, r.getDueAt());
        boolean chainChanged = chain != r.getChainType();
        if (!chainChanged && !dueChanged) return;
        r.setDueAt(due);
        if (!chainChanged && chain != ChainType.OBSERVATION) {
            routes.save(r);
            return;
        }
        r.setChainType(chain);
        r.setTemplateCode(lead.getRouteTemplateCode());
        r.setDueAt(r.getCreatedAt().plus(Duration.ofDays(RoutePlanning.minDays(group))));
        r.setControlAt(chain == ChainType.OBSERVATION ? r.getDueAt() : null);
        r.setPendingVisit(chain == ChainType.OBSERVATION ? PendingVisit.ULTRASOUND : PendingVisit.CONSULTATION);
        state.moveTo(r, chain == ChainType.OBSERVATION ? RouteStage.OBSERVATION_WAITING_US : RouteStage.CREATED,
                "SYSTEM", basis + ": пересчитан тип цепочки");
        routes.save(r);
        chains.start(r, chain, ModelTime.now(), true, basis);
    }

    private void ensureManualReviewTask(Finding f) {
        if (tasks.existsForFinding(f.getId(), "MANUAL_REVIEW")) {
            return;
        }
        String text = "Разобрать вручную находку вне словаря: "
                + (f.getAttributes() != null && f.getAttributes().get("text") != null ? f.getAttributes().get("text") : f.getName());
        tasks.createForFinding("MANUAL_REVIEW", "COORDINATOR", f.getPatient().getId(), f.getId(), text,
                "Находка UNRECOGNIZED_ABNORMALITY подтверждена (шаблон MANUAL_REVIEW)");
    }

    // ------------------------------------------------------------------ Новый протокол

    /** Контрольное УЗИ при наблюдении = новый протокол того же типа исследования (6.3). */
    public void onProtocolAccepted(UUID patientId, UUID protocolId) {
        Protocol p = protocols.findById(protocolId).orElse(null);
        if (p == null || p.getStudyType() == null) {
            return;
        }
        for (Route r : routes.findByPatientIdAndOpenTrue(patientId)) {
            boolean waitingUs = r.getStage() == RouteStage.OBSERVATION_WAITING_US
                    || r.getStage() == RouteStage.BOOKED && r.getPendingVisit() == PendingVisit.ULTRASOUND;
            if (!waitingUs || !p.getStudyType().name().equals(r.getStudyType()) || protocolId.equals(r.getProtocolId())) {
                continue;
            }
            appointments.findFirstByRouteIdAndStatusOrderByCreatedAtDesc(r.getId(), Appointment.Status.BOOKED)
                    .ifPresent(a -> a.setStatus(Appointment.Status.COMPLETED));
            r.setPendingVisit(PendingVisit.CONSULTATION);
            r.setVisitAt(ModelTime.now());
            r.setDueAt(ModelTime.now().plus(config.duration("/observation/visitAfterUltrasound")));
            r.milestone("CONTROL_ULTRASOUND");
            state.moveTo(r, RouteStage.OBSERVATION_WAITING_VISIT, "MIS", "Поступил протокол контрольного УЗИ " + p.getExternalId());
            chains.start(r, ChainType.NEAR, ModelTime.now(), true, "Контрольное УЗИ выполнено");
        }
    }

    // ------------------------------------------------------------------ 10. События МИС

    public void booked(Route r, Instant dateTime, String location, boolean online, String doctor, String basis) {
        if (dateTime == null || !dateTime.isAfter(ModelTime.now()))
            throw new BadRequestException("INVALID_DATE", "Дата записи должна быть в будущем");
        if (online && !ScheduleService.onlineAllowed(r, config))
            throw new BadRequestException("IN_PERSON_REQUIRED", "Для этого визита требуется очная запись");
        if (!RouteStateService.WAITING_FOR_BOOKING.contains(r.getStage())) {
            throw invalid(r, "BOOKED");
        }
        PendingVisit purpose = r.getPendingVisit() == null ? PendingVisit.CONSULTATION : r.getPendingVisit();
        Appointment a = new Appointment();
        a.setRouteId(r.getId());
        a.setPatientId(r.getPatientId());
        a.setPurpose(purpose);
        a.setDateTime(dateTime);
        a.setLocation(location);
        a.setOnline(online);
        a.setDoctorName(doctor);
        appointments.save(a);
        chains.stop(r);
        timers.cancelRoute(r.getId(), VISIT_GROUP);
        r.milestone("BOOKED");
        state.moveTo(r, RouteStage.BOOKED, "MIS", basis);
        String place = online ? config.text("/schedule/onlineLabel", "онлайн") : location;
        notifications.sendAuto(r, purpose == PendingVisit.CONTROL ? "CONTROL_BOOKED" : "BOOKING_CONFIRMED",
                NotificationService.appointmentValues(dateTime, place), "Запись подтверждена");
    }

    public void bookingCancelled(Route r, String basis) {
        if (r.getStage() != RouteStage.BOOKED) {
            throw invalid(r, "BOOKING_CANCELLED");
        }
        appointments.findFirstByRouteIdAndStatusOrderByCreatedAtDesc(r.getId(), Appointment.Status.BOOKED)
                .ifPresent(a -> a.setStatus(Appointment.Status.CANCELLED));
        state.moveTo(r, RouteStage.REBOOKING_REQUIRED, "MIS", basis);
        chains.start(r, nearOrUrgent(r), ModelTime.now(), false, "Пациент отменил запись");
    }

    public void noShow(Route r, String basis) {
        if (r.getStage() != RouteStage.BOOKED) {
            throw invalid(r, "NO_SHOW");
        }
        appointments.findFirstByRouteIdAndStatusOrderByCreatedAtDesc(r.getId(), Appointment.Status.BOOKED)
                .ifPresent(a -> a.setStatus(Appointment.Status.NO_SHOW));
        r.setNoShowCount(r.getNoShowCount() + 1);
        state.moveTo(r, RouteStage.NO_SHOW, "MIS", basis + " (неявка №" + r.getNoShowCount() + ")");
        chains.start(r, nearOrUrgent(r), ModelTime.now(), false, "Неявка");
        timers.schedule(RouteTimer.Kind.NO_SHOW_MESSAGE, ChainService.GROUP,
                ModelTime.now().plus(config.duration("/messages/noShowMessageDelay")), r.getPatientId(), r.getId(), null, Map.of());
    }

    public void visitCompleted(Route r, String doctor, String basis) {
        boolean controlBooked = r.getStage() == RouteStage.CONTROL_PENDING
                && appointments.findFirstByRouteIdAndStatusOrderByCreatedAtDesc(r.getId(), Appointment.Status.BOOKED).isPresent();
        if (r.getStage() != RouteStage.BOOKED && !controlBooked) {
            throw invalid(r, "VISIT_COMPLETED");
        }
        appointments.findFirstByRouteIdAndStatusOrderByCreatedAtDesc(r.getId(), Appointment.Status.BOOKED)
                .ifPresent(a -> a.setStatus(Appointment.Status.COMPLETED));
        r.setVisitAt(ModelTime.now());
        PendingVisit purpose = r.getPendingVisit() == null ? PendingVisit.CONSULTATION : r.getPendingVisit();
        if (purpose == PendingVisit.CONTROL) {
            if (r.hasMilestone("DISCHARGED")) {
                r.milestone("CONTROL_VISIT");
            }
            state.complete(r, basis + ": контрольный визит состоялся");
            return;
        }
        if (purpose == PendingVisit.CONSULTATION) {
            r.milestone("VISIT");
        }
        state.moveTo(r, RouteStage.AWAITING_TACTIC, "MIS", basis + ": приём состоялся, ждёт решения врача");
    }

    /** Тактика врача (5.2). */
    public void tactic(Route r, Tactic tactic, String subtype, Instant dueDate, Instant controlDate,
                       String newSpecialty, String comment, String basis) {
        if (r.getStage() != RouteStage.AWAITING_TACTIC) {
            throw invalid(r, "TACTIC_SELECTED");
        }
        r.setTactic(tactic);
        r.setTacticSubtype(subtype);
        r.setTacticComment(comment);
        journal.entry("DOCTOR", "TACTIC_SELECTED").basis(basis).patient(r.getPatientId()).route(r.getId())
                .detail("tactic", tactic).detail("subtype", subtype).detail("comment", comment).save();
        switch (tactic) {
            case SURGERY_INDICATED -> {
                r.milestone("SURGERY_RECOMMENDED");
                routes.save(r); // ждём событие «направление на госпитализацию создано»
            }
            case ADDITIONAL_EXAM -> {
                if ("PROCEDURE".equals(subtype)) {
                    state.moveTo(r, RouteStage.PROCEDURE_REFERRED, "DOCTOR", "Направлен на диагностическую процедуру");
                } else if ("TESTS".equals(subtype)) {
                    Instant due = dueDate != null ? dueDate : ModelTime.now().plus(config.duration("/additionalExam/defaultDue"));
                    r.setDueAt(due);
                    r.setPendingVisit(PendingVisit.REPEAT_CONSULTATION);
                    state.moveTo(r, RouteStage.ADDITIONAL_EXAM, "DOCTOR", "Дообследование: ждём повторный приём");
                    timers.schedule(RouteTimer.Kind.VISIT_DEADLINE, VISIT_GROUP, due, r.getPatientId(), r.getId(), null,
                            Map.of("reason", "ADDITIONAL_EXAM"));
                } else {
                    throw new BadRequestException("SUBTYPE_REQUIRED", "Для дообследования нужен подтип TESTS или PROCEDURE");
                }
            }
            case OBSERVATION -> {
                Instant control = controlDate != null ? controlDate
                        : ModelTime.now().plus(Duration.ofDays(minTargetDays(r, 180)));
                r.setChainType(ChainType.OBSERVATION);
                r.setControlAt(control);
                r.setDueAt(control);
                r.setPendingVisit(PendingVisit.ULTRASOUND);
                state.moveTo(r, RouteStage.OBSERVATION_WAITING_US, "DOCTOR", "Динамическое наблюдение");
                chains.start(r, ChainType.OBSERVATION, ModelTime.now(), true, "Тактика: динамическое наблюдение");
            }
            case SURGERY_NOT_INDICATED -> state.close(r, CloseReason.SURGERY_NOT_INDICATED, "DOCTOR", basis);
            case PATIENT_REFUSED -> {
                if (comment == null || comment.isBlank()) {
                    throw new BadRequestException("COMMENT_REQUIRED", "При отказе пациента комментарий врача обязателен");
                }
                state.close(r, CloseReason.PATIENT_REFUSED, "DOCTOR", basis);
            }
            case OTHER_PROFILE -> {
                if (newSpecialty == null || newSpecialty.isBlank()) {
                    throw new BadRequestException("SPECIALTY_REQUIRED", "Укажите специалиста другого профиля");
                }
                state.close(r, CloseReason.TRANSFERRED, "DOCTOR", basis + ": передан к " + newSpecialty);
                transfer(r, newSpecialty);
            }
        }
    }

    private void transfer(Route from, String specialty) {
        Optional<Route> existing = routes.findByPatientIdAndOpenTrue(from.getPatientId()).stream()
                .filter(r -> r.getSpecialty().equals(specialty)).findFirst();
        if (existing.isPresent()) {
            Route r = existing.get();
            r.setSpecialtyAssignedByDoctor(true);
            from.getFindingIds().stream().filter(id -> !r.getFindingIds().contains(id)).forEach(r.getFindingIds()::add);
            routes.save(r);
            return;
        }
        Route r = new Route();
        r.setPatientId(from.getPatientId());
        r.setProtocolId(from.getProtocolId());
        r.setSpecialtyAssignedByDoctor(true);
        r.setSpecialty(specialty);
        r.setTemplateCode(from.getTemplateCode());
        r.setChainType(ChainType.NEAR);
        r.setStage(RouteStage.CREATED);
        r.setPendingVisit(PendingVisit.CONSULTATION);
        r.setStudyType(from.getStudyType());
        r.setDetectedOn(from.getDetectedOn());
        r.setFindingIds(new ArrayList<>(from.getFindingIds()));
        r.setDueAt(ModelTime.now().plus(Duration.ofDays(minTargetDays(from, 30))));
        r.getStageHistory().add(Map.of("stage", "CREATED", "at", ModelTime.now().toString(), "basis", "Направление в другой профиль"));
        r.milestone("CREATED");
        Route saved = routes.save(r);
        journal.entry("DOCTOR", "ROUTE_CREATED").basis("Тактика «направление в другой профиль»; без подтверждения координатором")
                .patient(r.getPatientId()).route(saved.getId()).detail("specialty", specialty).save();
        chains.start(saved, ChainType.NEAR, ModelTime.now(), true, "Направление в другой профиль");
    }

    /** Минимальный targetDays находок маршрута из словаря (срок наблюдения по умолчанию, 5.2). */
    private long minTargetDays(Route r, int fallback) {
        return r.getFindingIds().stream().map(id -> findings.findById(UUID.fromString(id)).orElse(null))
                .filter(Objects::nonNull).map(Finding::getTargetDays).filter(Objects::nonNull)
                .min(Integer::compare).orElse(fallback);
    }

    // ------------------------------------------------------------------ 7. Госпитализация, процедура, контроль

    public void hospitalizationReferred(Route r, String basis) {
        if (r.getStage() != RouteStage.AWAITING_TACTIC || r.getTactic() != Tactic.SURGERY_INDICATED) {
            throw invalid(r, "HOSPITALIZATION_REFERRED");
        }
        r.milestone("REFERRED");
        r.setSlaOverdue(false);
        state.moveTo(r, RouteStage.HOSPITALIZATION_REFERRED, "MIS", basis);
        scheduleHospitalizationControl(r);
    }

    private void scheduleHospitalizationControl(Route r) {
        timers.cancelRoute(r.getId(), HOSPITALIZATION_GROUP);
        Instant now = ModelTime.now();
        for (var step : config.at("/hospitalization/tasks")) {
            Map<String, Object> payload = new LinkedHashMap<>();
            step.fields().forEachRemaining(e -> payload.put(e.getKey(), e.getValue().asText()));
            timers.schedule(RouteTimer.Kind.HOSPITALIZATION_TASK, HOSPITALIZATION_GROUP,
                    now.plus(RouteConfig.parse(step.path("at").asText())), r.getPatientId(), r.getId(), null, payload);
        }
        timers.schedule(RouteTimer.Kind.HOSPITALIZATION_SLA, HOSPITALIZATION_GROUP,
                WorkingDays.plus(now, config.integer("/hospitalization/dateDeadlineWorkingDays", 3)),
                r.getPatientId(), r.getId(), null, Map.of());
    }

    public void hospitalizationDateSet(Route r, String basis) {
        if (r.getStage() != RouteStage.HOSPITALIZATION_REFERRED) {
            throw invalid(r, "HOSPITALIZATION_DATE_SET");
        }
        timers.cancelRoute(r.getId(), HOSPITALIZATION_GROUP);
        tasks.cancelForRoute(r.getId(), "Дата госпитализации назначена", "SCHEDULE_HOSPITALIZATION", "MANAGER_ATTENTION");
        r.setSlaOverdue(false);
        r.milestone("DATE_SET");
        state.moveTo(r, RouteStage.HOSPITALIZATION_SCHEDULED, "MIS", basis);
    }

    public void hospitalizationFailed(Route r, String basis) {
        if (r.getStage() != RouteStage.HOSPITALIZATION_SCHEDULED) {
            throw invalid(r, "HOSPITALIZATION_FAILED");
        }
        state.moveTo(r, RouteStage.HOSPITALIZATION_REFERRED, "MIS", basis + ": госпитализация не состоялась");
        tasks.create("SCHEDULE_HOSPITALIZATION", "HOSPITALIZATION_MANAGER", r.getPatientId(), r.getId(), null,
                "Госпитализация не состоялась — назначить новую дату", Duration.ofDays(1), basis);
        scheduleHospitalizationControl(r);
    }

    public void hospitalized(Route r, String basis) {
        if (r.getStage() != RouteStage.HOSPITALIZATION_SCHEDULED && r.getStage() != RouteStage.HOSPITALIZATION_REFERRED) {
            throw invalid(r, "HOSPITALIZED");
        }
        timers.cancelRoute(r.getId(), HOSPITALIZATION_GROUP);
        r.milestone("HOSPITALIZED");
        state.moveTo(r, RouteStage.HOSPITALIZED, "MIS", basis);
    }

    public void surgeryDone(Route r, String basis) {
        if (r.getStage() != RouteStage.HOSPITALIZED) {
            throw invalid(r, "SURGERY_DONE");
        }
        r.milestone("OPERATED");
        state.moveTo(r, RouteStage.SURGERY_DONE, "MIS", basis);
    }

    /** Выписка (7.2): запись на контроль есть — CONTROL_BOOKED, нет — CONTROL_RECOMMENDED + задача. */
    public void discharged(Route r, boolean controlBooked, Instant controlDateTime, String location, String basis) {
        if (r.getStage() != RouteStage.HOSPITALIZED && r.getStage() != RouteStage.SURGERY_DONE) {
            throw invalid(r, "DISCHARGED");
        }
        r.milestone("DISCHARGED");
        state.moveTo(r, RouteStage.DISCHARGED, "MIS", basis);
        boolean diagnostic = config.strings("/control/diagnosticTemplates").contains(r.getTemplateCode());
        String key = diagnostic ? "/control/afterDiagnostic" : "/control/afterSurgery";
        Duration target = config.duration(key + "/target");
        r.setControlAt(ModelTime.now().plus(target));
        r.setDueAt(r.getControlAt().plus(config.duration(key + "/window")));
        r.setPendingVisit(PendingVisit.CONTROL);
        state.moveTo(r, RouteStage.CONTROL_PENDING, "SYSTEM", "Ожидает контрольного визита");
        if (controlBooked && controlDateTime != null) {
            Appointment a = new Appointment();
            a.setRouteId(r.getId());
            a.setPatientId(r.getPatientId());
            a.setPurpose(PendingVisit.CONTROL);
            a.setDateTime(controlDateTime);
            a.setLocation(location);
            appointments.save(a);
            notifications.sendAuto(r, "CONTROL_BOOKED", NotificationService.appointmentValues(controlDateTime,
                    location == null ? "" : location), "Выписка с записью на контроль");
        } else {
            notifications.sendAuto(r, "CONTROL_RECOMMENDED", Map.of("term", NotificationService.term(target.toDays())),
                    "Выписка без записи на контроль");
            tasks.create("BOOK_CONTROL_VISIT", "COORDINATOR", r.getPatientId(), r.getId(), null,
                    "Записать пациента на контрольный приём через " + NotificationService.term(target.toDays()),
                    target, "Выписка без записи на контрольный визит");
        }
    }

    /** Процедура выполнена (7.3): визит за результатом через 10±3 дней, всегда очно. */
    public void procedureDone(Route r, String basis) {
        if (r.getStage() != RouteStage.PROCEDURE_REFERRED) {
            throw invalid(r, "PROCEDURE_DONE");
        }
        state.moveTo(r, RouteStage.PROCEDURE_DONE, "MIS", basis);
        r.setControlAt(ModelTime.now().plus(config.duration("/control/afterDiagnostic/target")));
        r.setDueAt(r.getControlAt().plus(config.duration("/control/afterDiagnostic/window")));
        r.setPendingVisit(PendingVisit.RESULT);
        state.moveTo(r, RouteStage.CONTROL_PENDING, "SYSTEM", "Ожидает визита за результатом");
    }

    // ------------------------------------------------------------------ Ответы пациента (8.3)

    public void patientReply(Route r, String reply, String basis) {
        if (!r.isOpen()) throw new ConflictException("ROUTE_CLOSED", "Маршрут закрыт");
        switch (reply) {
            case "OTHER_ORGANIZATION" -> state.close(r, CloseReason.OTHER_ORGANIZATION, "CRM", basis);
            case "NOT_PLANNING" -> state.close(r, CloseReason.PATIENT_REFUSED, "CRM", basis);
            case "CALLBACK_REQUEST" -> tasks.create("CALL_PATIENT", "COORDINATOR", r.getPatientId(), r.getId(), null,
                    chains.callScript(r), Duration.ofDays(1), basis);
            case "BOOK" -> journal.entry("CRM", "PATIENT_OPENED_BOOKING").basis(basis).patient(r.getPatientId())
                    .route(r.getId()).save();
            default -> throw new BadRequestException("UNKNOWN_REPLY", "Неизвестный ответ пациента: " + reply);
        }
    }

    // ------------------------------------------------------------------ Таймеры ядра

    public void onVisitDeadline(Route r) {
        if (r.isOpen() && r.getStage() == RouteStage.ADDITIONAL_EXAM) {
            chains.start(r, ChainType.NEAR, ModelTime.now(), false, "Срок повторного приёма после дообследования прошёл");
        }
    }

    public void onNoShowMessage(Route r) {
        if (r.isOpen() && r.getStage() == RouteStage.NO_SHOW) {
            notifications.sendAuto(r, "NO_SHOW", Map.of(), "Через 30 минут после неявки");
        }
    }

    public void onHospitalizationTask(Route r, Map<String, Object> p) {
        if (r.isOpen() && r.getStage() == RouteStage.HOSPITALIZATION_REFERRED) {
            String type = String.valueOf(p.get("task"));
            tasks.create(type, String.valueOf(p.get("role")), r.getPatientId(), r.getId(), null,
                    "SCHEDULE_HOSPITALIZATION".equals(type) ? "Назначить дату госпитализации"
                            : "Дата госпитализации не назначена более 5 дней — требуется внимание руководителя",
                    p.get("dueIn") == null ? null : RouteConfig.parse(String.valueOf(p.get("dueIn"))),
                    "Таймер госпитализации, шаг " + p.get("at"));
        }
    }

    public void onHospitalizationSla(Route r) {
        if (r.isOpen() && r.getStage() == RouteStage.HOSPITALIZATION_REFERRED) {
            r.setSlaOverdue(true);
            routes.save(r);
            journal.entry("SYSTEM", "HOSPITALIZATION_SLA_OVERDUE").basis("Норматив 3 рабочих дня на назначение даты")
                    .patient(r.getPatientId()).route(r.getId()).save();
        }
    }

    // ------------------------------------------------------------------ Помощники

    private ChainType nearOrUrgent(Route r) {
        return r.getChainType() == ChainType.URGENT ? ChainType.URGENT : ChainType.NEAR;
    }

    private ConflictException invalid(Route r, String event) {
        journal.entry("MIS", "EVENT_REJECTED").basis("Событие " + event + " не подходит к этапу " + r.getStage())
                .patient(r.getPatientId()).route(r.getId()).saveIndependent();
        return new ConflictException("EVENT_NOT_APPLICABLE",
                "Событие " + event + " не подходит к текущему этапу маршрута: " + r.getStage());
    }

    private static List<String> ids(List<Finding> fs) {
        return fs.stream().map(f -> f.getId().toString()).toList();
    }
}
