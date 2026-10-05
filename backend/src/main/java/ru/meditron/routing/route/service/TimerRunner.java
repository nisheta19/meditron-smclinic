package ru.meditron.routing.route.service;

import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import ru.meditron.routing.route.domain.Escalation;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.domain.RouteStage;
import ru.meditron.routing.route.domain.RouteTimer;
import ru.meditron.routing.route.repo.EscalationRepository;
import ru.meditron.routing.route.repo.RouteRepository;
import ru.meditron.routing.route.repo.RouteTimerRepository;
import ru.meditron.routing.time.ModelTime;

/**
 * Исполняет наступившие таймеры по модельному времени — последовательно, в хронологическом порядке,
 * каждый в своей транзакции (раздел 3). Таймер, созданный обработчиком «в прошлом», будет исполнен
 * в этом же проходе.
 */
@Service
public class TimerRunner {

    private static final Logger log = LoggerFactory.getLogger(TimerRunner.class);
    private static final int SAFETY_LIMIT = 10_000;

    private final RouteTimerRepository timers;
    private final RouteRepository routes;
    private final EscalationRepository escalations;
    private final ChainService chains;
    private final RouteEngine engine;
    private final EscalationService escalationService;
    private final NotificationService notifications;
    private final TransactionTemplate tx;
    private final RouteWriteLock writeLock;

    public TimerRunner(RouteTimerRepository timers, RouteRepository routes, EscalationRepository escalations,
                       ChainService chains, RouteEngine engine, EscalationService escalationService,
                       NotificationService notifications, PlatformTransactionManager txManager, RouteWriteLock writeLock) {
        this.timers = timers;
        this.routes = routes;
        this.escalations = escalations;
        this.chains = chains;
        this.engine = engine;
        this.escalationService = escalationService;
        this.notifications = notifications;
        this.tx = new TransactionTemplate(txManager);
        this.writeLock = writeLock;
    }

    /** @return сколько таймеров исполнено */
    public synchronized int runDue() {
        int done = 0;
        while (done < SAFETY_LIMIT) {
            Boolean ran;
            try {
                ran = tx.execute(status -> {
                    writeLock.acquire();
                    Optional<RouteTimer> next = timers.findFirstByStatusAndDueAtLessThanEqualOrderByDueAtAscCreatedAtAsc(
                            RouteTimer.Status.PENDING, ModelTime.now());
                    if (next.isEmpty()) return false;
                    RouteTimer t = next.get();
                    ModelTime.at(t.getDueAt(), () -> dispatch(t));
                    if (t.getStatus() == RouteTimer.Status.PENDING) t.setStatus(RouteTimer.Status.DONE);
                    timers.save(t);
                    return true;
                });
            } catch (RuntimeException e) {
                // The transaction (including outbox/tasks) rolls back; retry on the next tick.
                log.error("Route timer failed; pending timer retained for retry", e);
                break;
            }
            if (!Boolean.TRUE.equals(ran)) {
                break;
            }
            done++;
        }
        return done;
    }

    private void dispatch(RouteTimer t) {
        Map<String, Object> p = t.getPayload();
        if (t.getEscalationId() != null) {
            Escalation e = escalations.findById(t.getEscalationId()).orElse(null);
            if (e == null) {
                return;
            }
            switch (t.getKind()) {
                case ESCALATION_CONFIRM -> escalationService.onConfirmTimeout(e);
                case ESCALATION_ACCEPT -> escalationService.onAcceptTimeout(e, Integer.parseInt(String.valueOf(p.get("level"))));
                case ESCALATION_CONTACT -> escalationService.onContactTimeout(e);
                default -> log.warn("Неожиданный таймер эскалации {}", t.getKind());
            }
            return;
        }
        Route r = t.getRouteId() == null ? null : routes.findById(t.getRouteId()).orElse(null);
        if (r == null || !r.isOpen()) {
            return;
        }
        switch (t.getKind()) {
            case CHAIN_STEP -> chains.runStep(r, p);
            case OBSERVATION_REMINDER -> chains.runObservationReminder(r, p);
            case OBSERVATION_CONTROL_DATE -> chains.runObservationControlDate(r);
            case NO_SHOW_MESSAGE -> engine.onNoShowMessage(r);
            case VISIT_DEADLINE -> engine.onVisitDeadline(r);
            case HOSPITALIZATION_TASK -> engine.onHospitalizationTask(r, p);
            case HOSPITALIZATION_SLA -> engine.onHospitalizationSla(r);
            case AMBULANCE_CALL -> escalationService.onAmbulanceCall(r);
            case DEFERRED_MESSAGE -> {
                if (r.getStage() != RouteStage.CLOSED) {
                    @SuppressWarnings("unchecked")
                    Map<String, String> extra = p.get("extra") instanceof Map<?, ?> m ? (Map<String, String>) m : Map.of();
                    notifications.sendAuto(r, String.valueOf(p.get("template")), extra,
                            "Отложенное сообщение (лимит в сутки): " + p.get("basis"));
                }
            }
            default -> log.warn("Неожиданный таймер маршрута {}", t.getKind());
        }
    }
}
