package ru.meditron.routing.route.web;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import ru.meditron.routing.route.dto.RouteDtos.*;
import ru.meditron.routing.route.service.RouteEventService;
import ru.meditron.routing.route.service.ScheduleService;
import ru.meditron.routing.route.service.TimerRunner;
import ru.meditron.routing.time.ModelTime;

/**
 * Внешние системы: события маршрута от МИС (раздел 10), обратные вызовы CRM (8.2–8.3), заглушка расписания (11).
 * ВНИМАНИЕ: это не /api/integration/events — тот пересылает события протоколов в ML и не трогается.
 */
@RestController
@RequestMapping("/api")
@Tag(name = "Интеграция маршрутов", description = "МИС → события маршрута, CRM → статусы и ответы, расписание")
@org.springframework.boot.autoconfigure.condition.ConditionalOnProperty(name = "routes.enabled", havingValue = "true", matchIfMissing = true)
public class IntegrationRouteController {

    private final RouteEventService events;
    private final ScheduleService schedule;
    private final TimerRunner timers;

    public IntegrationRouteController(RouteEventService events, ScheduleService schedule, TimerRunner timers) {
        this.events = events;
        this.schedule = schedule;
        this.timers = timers;
    }

    @PostMapping("/integration/route-events")
    @Operation(summary = "Событие маршрута от МИС: BOOKED, NO_SHOW, VISIT_COMPLETED, TACTIC_SELECTED, …; повтор eventId — 200 без изменений")
    public ResponseEntity<Map<String, Object>> routeEvent(@Valid @RequestBody RouteEvent ev) {
        boolean applied = events.handle(ev);
        timers.runDue();
        return applied ? ResponseEntity.accepted().body(Map.of("eventId", ev.eventId(), "applied", true))
                : ResponseEntity.ok(Map.of("eventId", ev.eventId(), "applied", false, "duplicate", true));
    }

    @PostMapping("/integration/crm/callbacks")
    @Operation(summary = "CRM: статус доставки (messageId+status) или ответ пациента (routeId+reply)")
    public ResponseEntity<Map<String, Object>> crm(@Valid @RequestBody CrmCallback cb) {
        boolean applied = events.crm(cb);
        timers.runDue();
        return applied ? ResponseEntity.accepted().body(Map.of("eventId", cb.eventId(), "applied", true))
                : ResponseEntity.ok(Map.of("eventId", cb.eventId(), "applied", false, "duplicate", true));
    }

    @GetMapping("/schedule/slots")
    @Operation(summary = "Ближайшие свободные слоты: по специальности или по маршруту (routeId)")
    public List<SlotDto> slots(@RequestParam(required = false) String specialty,
                               @RequestParam(defaultValue = "CONSULTATION") String kind,
                               @RequestParam(required = false) String routeId,
                               @RequestParam(defaultValue = "12") int limit) {
        return routeId != null ? schedule.slotsForRoute(routeId, limit) : schedule.slots(specialty, kind, limit);
    }

    @PostMapping("/schedule/bookings")
    @Operation(summary = "Записаться в слот: создаёт событие BOOKED")
    public ResponseEntity<Map<String, Object>> book(@Valid @RequestBody BookingRequest req) {
        String eventId = "booking-" + UUID.randomUUID();
        events.handle(new RouteEvent(eventId, "BOOKED", ModelTime.now(), null, req.routeId(), req.slotId(), null, null,
                null, null, null, null, null, null, null, null, null, null, null, null, null, null));
        timers.runDue();
        return ResponseEntity.accepted().body(Map.of("eventId", eventId, "applied", true));
    }
}
