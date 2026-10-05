package ru.meditron.routing.route.web;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.*;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.route.dto.RouteDtos.*;
import ru.meditron.routing.route.service.RouteQueryService;
import ru.meditron.routing.route.service.ScenarioService;
import ru.meditron.routing.route.service.TimerRunner;
import ru.meditron.routing.time.ModelTime;

/** Демо: модельное время, исходящие сообщения заглушки CRM, сценарии для видео (разделы 3, 8.4, 14). */
@RestController
@RequestMapping("/api/sim")
@Tag(name = "Демо", description = "Модельное время, заглушка CRM, сценарии")
@org.springframework.boot.autoconfigure.condition.ConditionalOnExpression("${routes.enabled:true} && ${routes.sim-enabled:false}")
public class SimController {

    private final TimerRunner timers;
    private final RouteQueryService query;
    private final ScenarioService scenarios;

    public SimController(TimerRunner timers, RouteQueryService query, ScenarioService scenarios) {
        this.timers = timers;
        this.query = query;
        this.scenarios = scenarios;
    }

    @GetMapping("/clock")
    public ClockDto clock() {
        return new ClockDto(ModelTime.now(), ModelTime.offset().toMinutes());
    }

    @PostMapping("/clock/advance")
    @Operation(summary = "Продвинуть модельное время (минуты) и сразу исполнить наступившие таймеры")
    public Map<String, Object> advance(@RequestBody AdvanceRequest req) {
        if (req.minutes() <= 0) {
            throw new BadRequestException("INVALID_STEP", "Шаг должен быть положительным");
        }
        ModelTime.advance(Duration.ofMinutes(req.minutes()));
        int done = timers.runDue();
        return Map.of("now", ModelTime.now(), "offsetMinutes", ModelTime.offset().toMinutes(), "timersExecuted", done);
    }

    @PostMapping("/clock/reset")
    public ClockDto reset() {
        ModelTime.reset();
        return clock();
    }

    @GetMapping("/crm/outbox")
    @Operation(summary = "Все сообщения, переданные в заглушку CRM")
    public List<NotificationDto> outbox() {
        return query.outbox();
    }

    @GetMapping("/scenarios")
    public List<Map<String, Object>> scenarios() {
        return scenarios.list();
    }

    @PostMapping("/scenarios/{name}/start")
    @Operation(summary = "Запустить сценарий: сам с паузой stepDelaySeconds или manual=true — по шагу через /next")
    public ScenarioRunDto start(@PathVariable String name, @RequestBody(required = false) ScenarioStartRequest req) {
        return scenarios.start(name, req == null ? null : req.stepDelaySeconds(), req != null && Boolean.TRUE.equals(req.manual()));
    }

    @PostMapping("/scenarios/{runId}/next")
    public ScenarioRunDto next(@PathVariable String runId) {
        return scenarios.next(runId);
    }

    @GetMapping("/scenarios/runs/{runId}")
    public ScenarioRunDto status(@PathVariable String runId) {
        return scenarios.status(runId);
    }
}
