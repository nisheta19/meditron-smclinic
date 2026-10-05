package ru.meditron.routing.route.service;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import ru.meditron.routing.route.domain.RouteTimer;
import ru.meditron.routing.route.repo.RouteTimerRepository;

/** Планирование и отмена отложенных действий. Исполняет их {@link TimerRunner}. */
@Service
public class TimerService {

    private final RouteTimerRepository timers;

    public TimerService(RouteTimerRepository timers) {
        this.timers = timers;
    }

    public RouteTimer schedule(RouteTimer.Kind kind, String group, Instant dueAt, UUID patientId, UUID routeId,
                               UUID escalationId, Map<String, Object> payload) {
        RouteTimer t = new RouteTimer();
        t.setKind(kind);
        t.setGroupName(group);
        t.setDueAt(dueAt);
        t.setPatientId(patientId);
        t.setRouteId(routeId);
        t.setEscalationId(escalationId);
        if (payload != null) {
            t.getPayload().putAll(payload);
        }
        return timers.save(t);
    }

    /** Отменить ожидающие таймеры маршрута; group == null — все группы. */
    public void cancelRoute(UUID routeId, String group) {
        for (RouteTimer t : timers.findByRouteIdAndStatus(routeId, RouteTimer.Status.PENDING)) {
            if (group == null || group.equals(t.getGroupName())) {
                t.setStatus(RouteTimer.Status.CANCELLED);
            }
        }
    }

    public void cancelEscalation(UUID escalationId, String group) {
        for (RouteTimer t : timers.findByEscalationIdAndStatus(escalationId, RouteTimer.Status.PENDING)) {
            if (group == null || group.equals(t.getGroupName())) {
                t.setStatus(RouteTimer.Status.CANCELLED);
            }
        }
    }
}
