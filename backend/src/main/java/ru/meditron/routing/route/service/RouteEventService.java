package ru.meditron.routing.route.service;

import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.exception.NotFoundException;
import ru.meditron.routing.route.domain.ProcessedEvent;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.domain.RouteNotification;
import ru.meditron.routing.route.domain.Tactic;
import ru.meditron.routing.route.dto.RouteDtos.CrmCallback;
import ru.meditron.routing.route.dto.RouteDtos.RouteEvent;
import ru.meditron.routing.route.repo.ProcessedEventRepository;
import ru.meditron.routing.route.repo.RouteNotificationRepository;
import ru.meditron.routing.route.repo.RouteRepository;
import ru.meditron.routing.time.ModelTime;

/**
 * Приём событий маршрута от МИС (раздел 10) и обратных вызовов CRM (8.2–8.3).
 * Повтор того же eventId не меняет состояние. Это НЕ /api/integration/events (тот пересылает протоколы в ML).
 */
@Service
public class RouteEventService {
    @org.springframework.beans.factory.annotation.Autowired
    private ru.meditron.routing.route.service.RouteWriteLock writeLock;


    @org.springframework.beans.factory.annotation.Autowired
    private ru.meditron.routing.repository.PatientRepository patients;
    @org.springframework.beans.factory.annotation.Autowired
    private com.fasterxml.jackson.databind.ObjectMapper json;
    private final ProcessedEventRepository processed;
    private final RouteRepository routes;
    private final RouteNotificationRepository notifications;
    private final RouteEngine engine;
    private final ScheduleService schedule;
    private final JournalService journal;

    public RouteEventService(ProcessedEventRepository processed, RouteRepository routes,
                             RouteNotificationRepository notifications, RouteEngine engine, ScheduleService schedule,
                             JournalService journal) {
        this.processed = processed;
        this.routes = routes;
        this.notifications = notifications;
        this.engine = engine;
        this.schedule = schedule;
        this.journal = journal;
    }

    /** @return false — событие уже было обработано (повтор). */
    @Transactional
    public boolean handle(RouteEvent ev) {
        writeLock.acquire();
        if (duplicate(ev.eventId(), "MIS", ev)) {
            return false;
        }
        Route r = route(ev.routeId());
        if (ev.patientExternalId() != null && !patients.findById(r.getPatientId())
                .map(p -> ev.patientExternalId().equals(p.getExternalId())).orElse(false))
            throw new BadRequestException("PATIENT_MISMATCH", "Маршрут принадлежит другому пациенту");
        String basis = "Событие МИС " + ev.type() + " (eventId " + ev.eventId() + ")";
        switch (ev.type()) {
            case "BOOKED" -> {
                if (ev.slotId() != null) {
                    var slot = schedule.validateSlot(r, ev.slotId());
                    engine.booked(r, slot.dateTime(), slot.location(), slot.online(), slot.doctorName(), basis);
                } else {
                    require(ev.dateTime(), "dateTime");
                    engine.booked(r, ev.dateTime(), ev.location(), Boolean.TRUE.equals(ev.online()), ev.doctorName(), basis);
                }
            }
            case "BOOKING_CANCELLED" -> engine.bookingCancelled(r, basis);
            case "NO_SHOW" -> engine.noShow(r, basis);
            case "VISIT_COMPLETED" -> engine.visitCompleted(r, ev.doctorName(), basis);
            case "TACTIC_SELECTED" -> {
                require(ev.tactic(), "tactic");
                Tactic t;
                try {
                    t = Tactic.valueOf(ev.tactic());
                } catch (IllegalArgumentException e) {
                    throw new BadRequestException("UNKNOWN_TACTIC", "Неизвестная тактика: " + ev.tactic());
                }
                engine.tactic(r, t, ev.subtype(), ev.dueDate(), ev.controlDate(), ev.newSpecialty(), ev.comment(), basis);
            }
            case "HOSPITALIZATION_REFERRED" -> {
                engine.hospitalizationReferred(r, basis);
                r.setHospitalizationClinic(ev.clinic());
            }
            case "HOSPITALIZATION_DATE_SET" -> {
                require(ev.date(), "date");
                java.time.LocalDate date;
                try { date = java.time.LocalDate.parse(ev.date()); }
                catch (java.time.format.DateTimeParseException e) {
                    throw new BadRequestException("INVALID_DATE", "date должна быть в формате YYYY-MM-DD");
                }
                if (date.isBefore(ModelTime.today())) throw new BadRequestException("INVALID_DATE", "Дата госпитализации в прошлом");
                engine.hospitalizationDateSet(r, basis + ", дата " + date);
                r.setHospitalizationDate(date);
                if (ev.clinic() != null) r.setHospitalizationClinic(ev.clinic());
            }
            case "HOSPITALIZATION_FAILED" -> engine.hospitalizationFailed(r, basis + (ev.reason() == null ? "" : ": " + ev.reason()));
            case "HOSPITALIZED" -> engine.hospitalized(r, basis);
            case "SURGERY_DONE" -> engine.surgeryDone(r, basis);
            case "DISCHARGED" -> {
                if (Boolean.TRUE.equals(ev.controlVisitBooked())) {
                    require(ev.controlDateTime(), "controlDateTime");
                    if (!ev.controlDateTime().isAfter(ModelTime.now()))
                        throw new BadRequestException("INVALID_DATE", "Контрольный визит должен быть в будущем");
                }
                engine.discharged(r, Boolean.TRUE.equals(ev.controlVisitBooked()), ev.controlDateTime(), ev.location(), basis);
            }
            case "PROCEDURE_DONE" -> engine.procedureDone(r, basis);
            default -> throw new BadRequestException("UNKNOWN_EVENT", "Неизвестный тип события: " + ev.type());
        }
        mark(ev.eventId(), "MIS", ev.type(), ev);
        return true;
    }

    @Transactional
    public boolean crm(CrmCallback cb) {
        writeLock.acquire();
        if (duplicate(cb.eventId(), "CRM", cb)) {
            return false;
        }
        if (cb.messageId() != null && cb.status() != null) {
            RouteNotification n = notifications.findById(ru.meditron.routing.service.Ids.parse(cb.messageId(), "MESSAGE"))
                    .orElseThrow(() -> new NotFoundException("MESSAGE_NOT_FOUND", "Сообщение " + cb.messageId() + " не найдено"));
            Instant at = cb.at() != null ? cb.at() : ModelTime.now();
            RouteNotification.Delivery status;
            try {
                status = RouteNotification.Delivery.valueOf(cb.status());
            } catch (IllegalArgumentException e) {
                throw new BadRequestException("UNKNOWN_STATUS", "Статусы: SENT, DELIVERED, READ, FAILED");
            }
            // Out-of-order callbacks must not regress READ/DELIVERED to SENT or FAILED.
            if (cb.routeId() != null && !n.getRouteId().toString().equals(cb.routeId()))
                throw new BadRequestException("MESSAGE_ROUTE_MISMATCH", "Сообщение принадлежит другому маршруту");
            boolean progressed = n.getDelivery() != RouteNotification.Delivery.READ
                    && !(n.getDelivery() == RouteNotification.Delivery.DELIVERED
                        && status != RouteNotification.Delivery.READ);
            if (progressed) n.setDelivery(status);
            switch (status) {
                case DELIVERED -> { if (n.getDeliveredAt() == null) n.setDeliveredAt(at); }
                case READ -> {
                    if (n.getReadAt() == null) n.setReadAt(at);
                    if (n.getDeliveredAt() == null) {
                        n.setDeliveredAt(at);
                    }
                }
                case FAILED -> { if (progressed) n.setFailedAt(at); }
                default -> { }
            }
            n.getStatusHistory().add(java.util.Map.of("status", status.name(), "at", at.toString()));
            boolean first = notifications.findByRouteIdOrderBySentAtDesc(n.getRouteId()).stream()
                    .noneMatch(other -> other.getSentAt().isBefore(n.getSentAt()));
            if (first && (status == RouteNotification.Delivery.DELIVERED || status == RouteNotification.Delivery.READ)) {
                routes.findById(n.getRouteId()).ifPresent(r -> {
                    r.getMilestones().putIfAbsent("NOTIFIED", at.toString());
                    routes.save(r);
                });
            }
            journal.entry("CRM", "MESSAGE_STATUS").basis("CRM, eventId " + cb.eventId()).patient(n.getPatientId())
                    .route(n.getRouteId()).detail("messageId", n.getId()).detail("status", status).save();
        } else if (cb.reply() != null) {
            require(cb.routeId(), "routeId");
            Route r = route(cb.routeId());
            journal.entry("CRM", "PATIENT_REPLY").basis("Ответ пациента, eventId " + cb.eventId())
                    .patient(r.getPatientId()).route(r.getId()).detail("reply", cb.reply()).save();
            engine.patientReply(r, cb.reply(), "Ответ пациента: " + cb.reply());
        } else {
            throw new BadRequestException("EMPTY_CALLBACK", "Нужен messageId+status или routeId+reply");
        }
        mark(cb.eventId(), "CRM", cb.status() != null ? cb.status() : cb.reply(), cb);
        return true;
    }

    private boolean duplicate(String id, String source, Object payload) {
        var previous = processed.findById(id);
        if (previous.isEmpty()) return false;
        ProcessedEvent event = previous.get();
        if (!source.equals(event.getSource()) || !fingerprint(payload).equals(event.getPayloadHash()))
            throw new ru.meditron.routing.exception.ConflictException("EVENT_ID_CONFLICT", "eventId уже использован с другим содержимым");
        return true;
    }

    private String fingerprint(Object value) {
        try {
            return java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256")
                    .digest(json.writeValueAsBytes(value)));
        } catch (java.security.NoSuchAlgorithmException | com.fasterxml.jackson.core.JsonProcessingException e) {
            throw new IllegalStateException(e);
        }
    }

    private void mark(String eventId, String source, String type, Object payload) {
        ProcessedEvent p = new ProcessedEvent();
        p.setEventId(eventId);
        p.setSource(source);
        p.setPayloadHash(fingerprint(payload));
        p.setType(type);
        processed.save(p);
    }

    private Route route(String id) {
        try {
            return routes.findById(UUID.fromString(id))
                    .orElseThrow(() -> new NotFoundException("ROUTE_NOT_FOUND", "Маршрут " + id + " не найден"));
        } catch (IllegalArgumentException e) {
            throw new NotFoundException("ROUTE_NOT_FOUND", "Маршрут " + id + " не найден");
        }
    }

    private static void require(Object v, String name) {
        if (v == null) {
            throw new BadRequestException("FIELD_REQUIRED", "Поле " + name + " обязательно для этого события");
        }
    }
}
