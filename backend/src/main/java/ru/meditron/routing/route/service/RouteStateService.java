package ru.meditron.routing.route.service;

import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import ru.meditron.routing.route.domain.CloseReason;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.domain.RouteStage;
import ru.meditron.routing.route.repo.RouteRepository;
import ru.meditron.routing.time.ModelTime;

/** Смена этапа и закрытие маршрута с записью в историю этапов и журнал (раздел 5). */
@Service
public class RouteStateService {

    /** Этапы, на которых пациент ещё не записан и цепочка напоминаний имеет смысл («нет записи»). */
    public static final Set<RouteStage> WAITING_FOR_BOOKING = EnumSet.of(
            RouteStage.CREATED, RouteStage.NOTIFIED, RouteStage.REBOOKING_REQUIRED, RouteStage.NO_SHOW,
            RouteStage.ADDITIONAL_EXAM, RouteStage.CONTROL_PENDING, RouteStage.OBSERVATION_WAITING_US,
            RouteStage.OBSERVATION_WAITING_VISIT, RouteStage.NOT_ENGAGED);

    private final RouteRepository routes;
    private final JournalService journal;
    private final TimerService timers;
    private final TaskService tasks;

    public RouteStateService(RouteRepository routes, JournalService journal, TimerService timers, TaskService tasks) {
        this.routes = routes;
        this.journal = journal;
        this.timers = timers;
        this.tasks = tasks;
    }

    public void moveTo(Route route, RouteStage stage, String actor, String basis) {
        RouteStage from = route.getStage();
        route.setStage(stage);
        route.setUpdatedAt(ModelTime.now());
        Map<String, Object> h = new LinkedHashMap<>();
        h.put("stage", stage.name());
        h.put("at", ModelTime.now().toString());
        h.put("basis", basis);
        route.getStageHistory().add(h);
        routes.save(route);
        journal.entry(actor, "STAGE_CHANGED").basis(basis).patient(route.getPatientId()).route(route.getId())
                .detail("from", from).detail("to", stage).save();
    }

    /** Закрыть маршрут: цепочка и все таймеры останавливаются, открытые задачи отменяются (5.3, 6.5). */
    public void close(Route route, CloseReason reason, String actor, String basis) {
        if (!route.isOpen()) {
            return;
        }
        timers.cancelRoute(route.getId(), null);
        tasks.cancelForRoute(route.getId(), "Маршрут закрыт: " + reason);
        route.setOpen(false);
        route.setCloseReason(reason);
        route.setClosedAt(ModelTime.now());
        moveTo(route, RouteStage.CLOSED, actor, basis + " (" + reason + ")");
    }

    /** Маршрут завершён: контрольный визит состоялся. */
    public void complete(Route route, String basis) {
        timers.cancelRoute(route.getId(), null);
        tasks.cancelForRoute(route.getId(), "Маршрут завершён");
        route.setOpen(false);
        route.setClosedAt(ModelTime.now());
        moveTo(route, RouteStage.COMPLETED, "MIS", basis);
    }
}
