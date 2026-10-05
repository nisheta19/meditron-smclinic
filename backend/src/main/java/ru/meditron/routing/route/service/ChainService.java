package ru.meditron.routing.route.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.ChainType;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.domain.RouteNotification;
import ru.meditron.routing.route.domain.RouteStage;
import ru.meditron.routing.route.domain.RouteTimer;
import ru.meditron.routing.time.ModelTime;

/**
 * Цепочки напоминаний (раздел 6): ближняя, срочная, наблюдение. Шаги и смещения — в route-config.yaml.
 * Запуск цепочки всегда отменяет предыдущую цепочку маршрута.
 */
@Service
public class ChainService {

    public static final String GROUP = "chain";

    private final RouteConfig config;
    private final TimerService timers;
    private final NotificationService notifications;
    private final TaskService tasks;
    private final RouteStateService state;

    public ChainService(RouteConfig config, TimerService timers, NotificationService notifications,
                        TaskService tasks, RouteStateService state) {
        this.config = config;
        this.timers = timers;
        this.notifications = notifications;
        this.tasks = tasks;
        this.state = state;
    }

    /**
     * Запустить цепочку. includeInitial=false — перезапуск после отмены, неявки или просрочки:
     * первое сообщение не повторяется, идут напоминания (6.4).
     */
    public void start(Route route, ChainType type, Instant t0, boolean includeInitial, String basis) {
        stop(route);
        if (type == ChainType.EMERGENCY) {
            return;
        }
        for (JsonNode step : config.chain(type.name())) {
            if (!includeInitial && step.path("initial").asBoolean(false)) {
                continue;
            }
            Map<String, Object> payload = new LinkedHashMap<>();
            step.fields().forEachRemaining(e -> payload.put(e.getKey(), e.getValue().asText()));
            payload.put("basis", basis);
            timers.schedule(RouteTimer.Kind.CHAIN_STEP, GROUP, t0.plus(RouteConfig.parse(step.path("at").asText())),
                    route.getPatientId(), route.getId(), null, payload);
        }
        if (type == ChainType.OBSERVATION && route.getControlAt() != null) {
            for (String before : config.strings("/observation/remindBeforeControl")) {
                Duration d = RouteConfig.parse(before);
                Instant due = route.getControlAt().minus(d);
                if (due.isAfter(ModelTime.now())) {
                    timers.schedule(RouteTimer.Kind.OBSERVATION_REMINDER, GROUP, due, route.getPatientId(),
                            route.getId(), null, Map.of("n", String.valueOf(d.toDays())));
                }
            }
            timers.schedule(RouteTimer.Kind.OBSERVATION_CONTROL_DATE, GROUP, route.getControlAt(),
                    route.getPatientId(), route.getId(), null, Map.of());
        }
    }

    public void stop(Route route) {
        timers.cancelRoute(route.getId(), GROUP);
        tasks.cancelForRoute(route.getId(), "Цепочка напоминаний остановлена", "CALL_PATIENT", "MANAGER_ATTENTION");
    }

    /** Исполнить шаг цепочки (CHAIN_STEP). */
    public void runStep(Route route, Map<String, Object> p) {
        if (!route.isOpen() || !RouteStateService.WAITING_FOR_BOOKING.contains(route.getStage())) {
            return; // пациент записан или маршрут закрыт — шаг не нужен
        }
        String basis = "Таймер цепочки " + route.getChainType() + ", шаг " + p.get("at");
        switch (String.valueOf(p.get("action"))) {
            case "MESSAGE" -> {
                RouteNotification n = notifications.sendAuto(route, String.valueOf(p.get("template")), termValues(route), basis);
                if ("true".equals(String.valueOf(p.get("initial"))) && route.getStage() == RouteStage.CREATED && n != null) {
                    state.moveTo(route, RouteStage.NOTIFIED, "SYSTEM", "Отправлено первое сообщение");
                }
            }
            case "TASK" -> {
                String type = String.valueOf(p.get("task"));
                String text = "CALL_PATIENT".equals(type) ? callScript(route) : "Пациент не записался по маршруту к "
                        + config.specialistCases(route.getSpecialty())[2] + "; требуется внимание руководителя";
                tasks.create(type, String.valueOf(p.get("role")), route.getPatientId(), route.getId(), null, text,
                        p.get("dueIn") == null ? null : RouteConfig.parse(String.valueOf(p.get("dueIn"))), basis);
            }
            case "NOT_ENGAGED" -> state.moveTo(route, RouteStage.NOT_ENGAGED, "SYSTEM",
                    "30 дней без реакции пациента: маршрут не реализован");
            default -> throw new IllegalStateException("Неизвестное действие цепочки: " + p.get("action"));
        }
    }

    /** Напоминание перед контрольным УЗИ при наблюдении (за 14 и за 3 дня). */
    public void runObservationReminder(Route route, Map<String, Object> p) {
        if (!route.isOpen() || route.getStage() != RouteStage.OBSERVATION_WAITING_US) {
            return;
        }
        Map<String, String> extra = termValues(route);
        extra.put("n", String.valueOf(p.get("n")));
        notifications.sendAuto(route, "OBSERVATION_REMINDER", extra, "За " + p.get("n") + " дн. до контрольного УЗИ");
    }

    /** Дата контроля наступила, а УЗИ нет — дальше цепочка ближнего срока от этой даты (6.3). */
    public void runObservationControlDate(Route route) {
        if (route.isOpen() && route.getStage() == RouteStage.OBSERVATION_WAITING_US) {
            start(route, ChainType.NEAR, ModelTime.now(), false, "Дата контроля прошла, контрольного УЗИ нет");
        }
    }

    public String callScript(Route route) {
        return TextRenderer.render(config.text("/callScript", ""), notifications.values(route, termValues(route)),
                ScheduleService.onlineAllowed(route, config));
    }

    private Map<String, String> termValues(Route route) {
        Map<String, String> v = new LinkedHashMap<>();
        if (route.getControlAt() != null && route.getControlAt().isAfter(ModelTime.now())) {
            long seconds = Duration.between(ModelTime.now(), route.getControlAt()).getSeconds();
            v.put("term", NotificationService.term(Math.max(1, (seconds + 86_399) / 86_400)));
        }
        return v;
    }
}
