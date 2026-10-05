package ru.meditron.routing.route.service;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.meditron.routing.exception.NotFoundException;
import ru.meditron.routing.repository.FindingRepository;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.*;
import ru.meditron.routing.route.dto.RouteDtos.*;
import ru.meditron.routing.route.repo.*;
import ru.meditron.routing.time.ModelTime;

/** Чтение для фронта: маршруты, уведомления, задачи, эскалации, журнал, баннер (раздел 15). */
@Service
@Transactional(readOnly = true)
public class RouteQueryService {

    private static final DateTimeFormatter DMY = DateTimeFormatter.ofPattern("dd.MM.yyyy");
    private static final Map<RouteStage, String> TITLES = new EnumMap<>(RouteStage.class);

    static {
        TITLES.put(RouteStage.CREATED, "Создан");
        TITLES.put(RouteStage.NOTIFIED, "Уведомлён");
        TITLES.put(RouteStage.BOOKED, "Записан");
        TITLES.put(RouteStage.REBOOKING_REQUIRED, "Нужна повторная запись");
        TITLES.put(RouteStage.NO_SHOW, "Неявка");
        TITLES.put(RouteStage.AWAITING_TACTIC, "Ждёт решения врача");
        TITLES.put(RouteStage.ADDITIONAL_EXAM, "Дообследование");
        TITLES.put(RouteStage.PROCEDURE_REFERRED, "Направлен на процедуру");
        TITLES.put(RouteStage.PROCEDURE_DONE, "Процедура выполнена");
        TITLES.put(RouteStage.HOSPITALIZATION_REFERRED, "Направлен на госпитализацию");
        TITLES.put(RouteStage.HOSPITALIZATION_SCHEDULED, "Госпитализация назначена");
        TITLES.put(RouteStage.HOSPITALIZED, "Госпитализирован");
        TITLES.put(RouteStage.SURGERY_DONE, "Операция выполнена");
        TITLES.put(RouteStage.DISCHARGED, "Выписан");
        TITLES.put(RouteStage.CONTROL_PENDING, "Ждёт контрольного визита");
        TITLES.put(RouteStage.OBSERVATION_WAITING_US, "Ждёт контрольного УЗИ");
        TITLES.put(RouteStage.OBSERVATION_WAITING_VISIT, "Ждёт визита после УЗИ");
        TITLES.put(RouteStage.COMPLETED, "Завершён");
        TITLES.put(RouteStage.CLOSED, "Закрыт");
        TITLES.put(RouteStage.NOT_ENGAGED, "Не вовлечён");
    }

    private static final Map<CloseReason, String> REASONS = new EnumMap<>(CloseReason.class);

    static {
        REASONS.put(CloseReason.SURGERY_NOT_INDICATED, "операция не показана");
        REASONS.put(CloseReason.PATIENT_REFUSED, "отказ пациента");
        REASONS.put(CloseReason.OTHER_ORGANIZATION, "обратился в другую организацию");
        REASONS.put(CloseReason.TRANSFERRED, "передан в другой профиль");
        REASONS.put(CloseReason.PROTOCOL_ANNULLED, "протокол аннулирован");
        REASONS.put(CloseReason.FINDING_NOT_CONFIRMED, "находка не подтвердилась");
        REASONS.put(CloseReason.FINDING_REJECTED, "находка отклонена координатором");
        REASONS.put(CloseReason.PROTOCOL_CORRECTED, "протокол исправлен");
    }

    @org.springframework.beans.factory.annotation.Autowired
    private ru.meditron.routing.repository.PatientRepository patients;
    private final RouteRepository routes;
    private final RouteNotificationRepository notifications;
    private final StaffTaskRepository tasks;
    private final EscalationRepository escalations;
    private final JournalRepository journal;
    private final AppointmentRepository appointments;
    private final FindingRepository findings;
    private final RouteConfig config;
    private final EscalationService escalationService;

    public RouteQueryService(RouteRepository routes, RouteNotificationRepository notifications, StaffTaskRepository tasks,
                             EscalationRepository escalations, JournalRepository journal,
                             AppointmentRepository appointments, FindingRepository findings, RouteConfig config,
                             EscalationService escalationService) {
        this.routes = routes;
        this.notifications = notifications;
        this.tasks = tasks;
        this.escalations = escalations;
        this.journal = journal;
        this.appointments = appointments;
        this.findings = findings;
        this.config = config;
        this.escalationService = escalationService;
    }

    public int activeRouteCount(UUID patientId) { return routes.findByPatientIdAndOpenTrue(patientId).size(); }

    public List<RouteDto> patientRoutes(UUID patientId) {
        return routes.findByPatientIdOrderByCreatedAtDesc(patientId).stream()
                .sorted(Comparator.comparing((Route r) -> !r.isOpen()).thenComparing(Route::getCreatedAt, Comparator.reverseOrder()))
                .map(this::route).toList();
    }

    public List<RouteDto> list(String stage, String specialty, Boolean overdue, Boolean open) {
        return routes.findAll().stream()
                .filter(r -> stage == null || r.getStage().name().equals(stage))
                .filter(r -> specialty == null || r.getSpecialty().equals(specialty))
                .filter(r -> open == null || r.isOpen() == open)
                .map(this::route)
                .filter(d -> overdue == null || (d.overdueDays() != null) == overdue)
                .sorted(Comparator.comparing(RouteDto::createdAt, Comparator.reverseOrder()))
                .toList();
    }

    public RouteDto route(String id) {
        return route(find(id));
    }

    public Route find(String id) {
        try {
            return routes.findById(ru.meditron.routing.service.Ids.parse(id, "RESOURCE"))
                    .orElseThrow(() -> new NotFoundException("ROUTE_NOT_FOUND", "Маршрут " + id + " не найден"));
        } catch (IllegalArgumentException e) {
            throw new NotFoundException("ROUTE_NOT_FOUND", "Маршрут " + id + " не найден");
        }
    }

    public RouteDto route(Route r) {
        List<FindingRef> refs = r.getFindingIds().stream()
                .map(id -> findings.findById(ru.meditron.routing.service.Ids.parse(id, "RESOURCE")).orElse(null)).filter(Objects::nonNull)
                .map(f -> new FindingRef(f.getId().toString(), f.getCode(), f.getName(), f.getStatus().name())).toList();
        List<TaskDto> open = tasks.findByRouteIdAndStatus(r.getId(), StaffTask.Status.OPEN).stream().map(this::task).toList();
        AppointmentDto appt = appointments.findByRouteIdOrderByCreatedAtDesc(r.getId()).stream().findFirst()
                .map(a -> new AppointmentDto(a.getId().toString(), a.getPurpose() == null ? null : a.getPurpose().name(),
                        a.getDateTime(), a.getLocation(), a.isOnline(), a.getDoctorName(), a.getStatus().name()))
                .orElse(null);
        String title = TITLES.get(r.getStage());
        if (r.getStage() == RouteStage.CLOSED && r.getCloseReason() != null) {
            title = "Закрыт: " + REASONS.get(r.getCloseReason());
        } else if (r.getStage() == RouteStage.NO_SHOW) {
            title = "Неявка №" + r.getNoShowCount();
        }
        return new RouteDto(r.getId().toString(), r.getPatientId().toString(),
                r.getProtocolId() == null ? null : r.getProtocolId().toString(), r.getSpecialty(),
                config.routeType(r.getTemplateCode()), r.getChainType().name(), r.getStage().name(), title,
                r.getPendingVisit() == null ? null : r.getPendingVisit().name(), r.isOpen(),
                r.getCloseReason() == null ? null : r.getCloseReason().name(), r.getDueAt(), r.getControlAt(),
                r.getVisitAt(), overdueDays(r), r.isSlaOverdue(), r.getNoShowCount(),
                r.getTactic() == null ? null : r.getTactic().name(), r.getTacticSubtype(), r.getTacticComment(),
                refs, r.getStageHistory(), open, appt, r.getCreatedAt(), r.getClosedAt(), r.getHospitalizationDate(), r.getHospitalizationClinic());
    }

    /** «Просрочен на N дней»: открыт, срок прошёл, пациент не записан. */
    public static Integer overdueDays(Route r) {
        if (!r.isOpen() || r.getDueAt() == null || !RouteStateService.WAITING_FOR_BOOKING.contains(r.getStage())) {
            return null;
        }
        Instant now = ModelTime.now();
        if (!now.isAfter(r.getDueAt())) {
            return null;
        }
        return (int) Math.max(1, Duration.between(r.getDueAt(), now).toDays());
    }

    // ------------------------------------------------------------------ уведомления

    public List<NotificationDto> routeNotifications(String routeId) {
        Route r = find(routeId);
        return notifications.findByRouteIdOrderBySentAtDesc(r.getId()).stream().map(n -> notification(n, r)).toList();
    }

    public List<NotificationDto> patientNotifications(UUID patientId) {
        return notifications.findByPatientIdOrderBySentAtDesc(patientId).stream()
                .map(n -> notification(n, routes.findById(n.getRouteId()).orElse(null))).toList();
    }

    public NotificationDto notification(RouteNotification n, Route r) {
        boolean booked = appointments.findByRouteIdOrderByCreatedAtDesc(n.getRouteId()).stream()
                .anyMatch(a -> a.getCreatedAt().isAfter(n.getSentAt()));
        String title = config.template(n.getTemplateCode()).map(t -> t.path("title").asText()).orElse(n.getTemplateCode());
        return new NotificationDto(n.getId().toString(), n.getRouteId().toString(), r == null ? null : r.getSpecialty(),
                n.getTemplateCode(), title, n.getFullText(), n.getShortText(), n.getLinks(), n.getButtons(), n.isManual(),
                n.getSentBy(), n.getSentAt(), n.getDelivery().name(), n.getDeliveredAt(), n.getReadAt(), n.getFailedAt(), booked, n.getPatientId().toString(),
                patients.findById(n.getPatientId()).map(p -> p.getExternalId()).orElse(null), n.getPreferredChannel());
    }

    public List<NotificationDto> outbox() {
        return notifications.findAllByOrderBySentAtDesc().stream()
                .map(n -> notification(n, routes.findById(n.getRouteId()).orElse(null))).toList();
    }

    public List<TemplateDto> templates() {
        List<TemplateDto> out = new ArrayList<>();
        config.root().path("templates").fields().forEachRemaining(e -> out.add(new TemplateDto(e.getKey(),
                e.getValue().path("title").asText(e.getKey()), e.getValue().path("manual").asBoolean(true))));
        return out;
    }

    // ------------------------------------------------------------------ задачи, эскалации, журнал

    public List<TaskDto> tasks(String role, String status, String patientId) {
        List<StaffTask> all = patientId != null ? tasks.findByPatientIdOrderByCreatedAtDesc(ru.meditron.routing.service.Ids.parse(patientId, "RESOURCE"))
                : tasks.findAllByOrderByCreatedAtDesc();
        return all.stream().filter(t -> role == null || t.getRole().equals(role))
                .filter(t -> status == null || t.getStatus().name().equals(status)).map(this::task).toList();
    }

    public TaskDto task(StaffTask t) {
        boolean overdue = t.getStatus() == StaffTask.Status.OPEN && t.getDueAt() != null && ModelTime.now().isAfter(t.getDueAt());
        return new TaskDto(t.getId().toString(), t.getType(), t.getRole(), str(t.getPatientId()), str(t.getRouteId()),
                str(t.getEscalationId()), t.getText(), t.getCreatedAt(), t.getDueAt(), overdue, t.getStatus().name(),
                t.getDoneBy(), t.getDoneAt(), t.getComment());
    }

    public List<EscalationDto> escalations(String patientId, Boolean open) {
        List<Escalation> all = patientId != null ? escalations.findByPatientIdOrderByStartedAtDesc(ru.meditron.routing.service.Ids.parse(patientId, "RESOURCE"))
                : escalations.findAllByOrderByStartedAtDesc();
        return all.stream().filter(e -> open == null || (e.getStep() != Escalation.Step.CLOSED) == open)
                .map(this::escalation).toList();
    }

    public EscalationDto escalation(Escalation e) {
        String role = switch (e.getStep()) {
            case AWAITING_CONFIRMATION -> "COORDINATOR";
            case AWAITING_ACCEPT -> config.at("/escalation/ladder").get(e.getLadderLevel()).path("role").asText();
            case AWAITING_CONTACT, AWAITING_OUTCOME -> e.getAcceptedRole();
            case CLOSED -> null;
        };
        return new EscalationDto(e.getId().toString(), e.getPatientId().toString(), str(e.getProtocolId()),
                e.getFindingId().toString(), e.getFindingName(), e.getDutySpecialty(), e.getStep().name(), role,
                escalationService.deadline(e), e.isConfirmTimedOut(), e.getStartedAt(), e.getConfirmedAt(),
                e.getAcceptedAt(), e.getAcceptedBy(), e.getContactedAt(), e.getClosedAt(), e.getOutcome(),
                e.getOutcomeComment(), e.getCloseNote(), str(e.getRouteId()), e.getHistory());
    }

    public List<JournalDto> journal(UUID patientId, String action, int limit) {
        List<JournalEntry> all = patientId != null ? journal.findByPatientIdOrderByAtDesc(patientId) : journal.findAllByOrderByAtDesc();
        if (limit < 1 || limit > 5000) throw new ru.meditron.routing.exception.BadRequestException("INVALID_LIMIT", "limit от 1 до 5000");
        return all.stream().filter(j -> action == null || j.getAction().equals(action)).limit(limit)
                .map(j -> new JournalDto(j.getId().toString(), j.getAt(), j.getActor(), j.getActorName(), j.getAction(),
                        j.getBasis(), str(j.getPatientId()), str(j.getRouteId()), str(j.getFindingId()), str(j.getTaskId()),
                        str(j.getEscalationId()), j.getDetails())).toList();
    }

    // ------------------------------------------------------------------ 15.3. Баннер

    /** Баннер «Незавершённый клинический маршрут» — самый свежий подходящий маршрут пациента. */
    public String banner(UUID patientId) {
        for (Route r : routes.findByPatientIdOrderByCreatedAtDesc(patientId)) {
            String head = "Незавершённый клинический маршрут. " + date(r.getDetectedOn()) + ": " + findingNames(r)
                    + (r.getStudyType() == null ? "" : " (" + r.getStudyType() + ")") + ". ";
            String spec = config.specialistCases(r.getSpecialty())[0];
            if (r.getStage() == RouteStage.NOT_ENGAGED) {
                return head + "Консультация " + spec + " в системе не зафиксирована";
            }
            if (overdueDays(r) != null) {
                return head + "Срок консультации " + spec + " истёк " + DMY.format(r.getDueAt().atZone(ModelTime.ZONE));
            }
            if (r.getCloseReason() == CloseReason.PATIENT_REFUSED) {
                return head + "Пациент отказался от консультации " + spec + " (" + closed(r) + ")";
            }
            if (r.getCloseReason() == CloseReason.OTHER_ORGANIZATION) {
                return head + "Пациент сообщил, что обратился в другую организацию (" + closed(r) + ")";
            }
        }
        return null;
    }

    private String findingNames(Route r) {
        List<String> names = r.getFindingIds().stream().map(id -> findings.findById(ru.meditron.routing.service.Ids.parse(id, "RESOURCE")).orElse(null))
                .filter(Objects::nonNull).map(f -> f.getName()).distinct().toList();
        return names.isEmpty() ? "находка" : String.join(", ", names).toLowerCase(new java.util.Locale("ru"));
    }

    private static String closed(Route r) {
        return r.getClosedAt() == null ? "" : DMY.format(r.getClosedAt().atZone(ModelTime.ZONE));
    }

    private static String date(LocalDate d) {
        return d == null ? "" : DMY.format(d);
    }

    private static String str(UUID id) {
        return id == null ? null : id.toString();
    }
}
