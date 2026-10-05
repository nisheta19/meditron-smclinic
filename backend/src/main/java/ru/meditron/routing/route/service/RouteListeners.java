package ru.meditron.routing.route.service;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import ru.meditron.routing.event.RoutingEvents;

/**
 * Стык со старым кодом: приём ML и действия координатора с находками публикуют события,
 * модуль маршрутов реагирует синхронно, в той же транзакции.
 */
@Component
@org.springframework.boot.autoconfigure.condition.ConditionalOnProperty(name = "routes.enabled", havingValue = "true", matchIfMissing = true)
public class RouteListeners {

    private final RouteEngine engine;
    private final EscalationService escalations;

    public RouteListeners(RouteEngine engine, EscalationService escalations) {
        this.engine = engine;
        this.escalations = escalations;
    }

    @EventListener
    public void onProtocolAccepted(RoutingEvents.ProtocolAccepted e) {
        escalations.startForProtocol(e.protocolId());
        engine.onProtocolAccepted(e.patientId(), e.protocolId());
        engine.reconcile(e.patientId(), "Поступил протокол");
    }

    @EventListener
    public void onProtocolClosed(RoutingEvents.ProtocolClosed e) {
        String note = e.reason() == RoutingEvents.ProtocolClosed.Reason.ANNULLED ? "Протокол аннулирован" : "Протокол исправлен";
        escalations.onProtocolClosed(e.protocolId(), note);
        engine.reconcile(e.patientId(), note);
    }

    @EventListener
    public void onFindingsChanged(RoutingEvents.FindingsChanged e) {
        escalations.onFindingsChanged(e.patientId());
        engine.reconcile(e.patientId(), "Координатор разобрал находки");
    }
}
