package ru.meditron.routing.route.web;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import ru.meditron.routing.route.dto.RouteDtos.*;
import ru.meditron.routing.route.service.DashboardService;
import ru.meditron.routing.route.service.EscalationService;
import ru.meditron.routing.route.service.RouteQueryService;
import ru.meditron.routing.route.service.TaskService;

/** Задачи, эскалации, журнал, дашборд (разделы 9, 12, 13, 17). */
@RestController
@RequestMapping("/api")
@Tag(name = "Координатор", description = "Задачи, экстренная эскалация, журнал, дашборд")
@org.springframework.boot.autoconfigure.condition.ConditionalOnProperty(name = "routes.enabled", havingValue = "true", matchIfMissing = true)
public class StaffController {
    @org.springframework.beans.factory.annotation.Autowired
    private ru.meditron.routing.route.service.RouteWriteLock writeLock;


    private final RouteQueryService query;
    private final TaskService tasks;
    private final EscalationService escalations;
    private final DashboardService dashboard;

    public StaffController(RouteQueryService query, TaskService tasks, EscalationService escalations,
                           DashboardService dashboard) {
        this.query = query;
        this.tasks = tasks;
        this.escalations = escalations;
        this.dashboard = dashboard;
    }

    @GetMapping("/tasks")
    @Operation(summary = "Задачи персонала (фильтры: роль, статус OPEN/DONE/CANCELLED, пациент)")
    public List<TaskDto> tasks(@RequestParam(required = false) String role, @RequestParam(required = false) String status,
                               @RequestParam(required = false) String patientId) {
        return query.tasks(role, status, patientId);
    }

    @PostMapping("/tasks/{taskId}/done")
    @Operation(summary = "Задача выполнена")
    public TaskDto done(@PathVariable String taskId, @RequestBody(required = false) TaskDoneRequest req) {
        return query.task(tasks.done(taskId, req == null ? null : req.doctor(), req == null ? null : req.comment()));
    }

    @GetMapping("/escalations")
    @Operation(summary = "Экстренные эскалации")
    public List<EscalationDto> escalations(@RequestParam(required = false) String patientId,
                                           @RequestParam(required = false) Boolean open) {
        return query.escalations(patientId, open);
    }

    @PostMapping("/escalations/{id}/accept")
    @Transactional
    @Operation(summary = "«Принял в работу»")
    public EscalationDto accept(@PathVariable String id, @RequestBody(required = false) EscalationActionRequest req) {
        writeLock.acquire();
        return query.escalation(escalations.accept(id, req == null ? null : req.role(), req == null ? null : req.doctor()));
    }

    @PostMapping("/escalations/{id}/contacted")
    @Transactional
    @Operation(summary = "«Связался с пациентом»")
    public EscalationDto contacted(@PathVariable String id, @RequestBody(required = false) EscalationActionRequest req) {
        writeLock.acquire();
        return query.escalation(escalations.contacted(id, req == null ? null : req.doctor()));
    }

    @PostMapping("/escalations/{id}/close")
    @Transactional
    @Operation(summary = "Закрыть с исходом: HOSPITALIZED, AMBULANCE, COMING_TODAY, PATIENT_REFUSED, FINDING_NOT_CONFIRMED")
    public EscalationDto close(@PathVariable String id, @RequestBody EscalationActionRequest req) {
        writeLock.acquire();
        return query.escalation(escalations.closeWithOutcome(id, req.outcome(), req.comment(), req.doctor()));
    }

    @GetMapping("/patients/{patientId}/journal")
    @Operation(summary = "Журнал по пациенту")
    public List<JournalDto> patientJournal(@PathVariable String patientId, @RequestParam(required = false) String action,
                                           @RequestParam(defaultValue = "500") int limit) {
        return query.journal(ru.meditron.routing.service.Ids.parse(patientId, "RESOURCE"), action, limit);
    }

    @GetMapping("/journal")
    @Operation(summary = "Общий журнал")
    public List<JournalDto> journal(@RequestParam(required = false) String patientId,
                                    @RequestParam(required = false) String action,
                                    @RequestParam(defaultValue = "500") int limit) {
        return query.journal(patientId == null ? null : ru.meditron.routing.service.Ids.parse(patientId, "RESOURCE"), action, limit);
    }

    @GetMapping("/dashboard/funnel")
    @Operation(summary = "Воронка: проценты от предыдущего шага")
    public List<Map<String, Object>> funnel(@RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) java.time.LocalDate dateFrom,
                                            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) java.time.LocalDate dateTo,
                                            @RequestParam(required = false) String studyType,
                                            @RequestParam(required = false) String routeType) {
        return dashboard.funnel(dateFrom, dateTo, studyType, routeType);
    }

    @GetMapping("/dashboard/losses")
    @Operation(summary = "Где теряем")
    public List<Map<String, Object>> losses(@RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) java.time.LocalDate dateFrom,
                                            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) java.time.LocalDate dateTo,
                                            @RequestParam(required = false) String studyType,
                                            @RequestParam(required = false) String routeType) {
        return dashboard.losses(dateFrom, dateTo, studyType, routeType);
    }

    @GetMapping("/dashboard/escalations")
    @Operation(summary = "Метрики экстренных: время реакции, нормативы, исходы")
    public Map<String, Object> escalationMetrics(@RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) java.time.LocalDate dateFrom,
                                                 @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) java.time.LocalDate dateTo) {
        return dashboard.escalationMetrics(dateFrom, dateTo);
    }

    @GetMapping("/dashboard/patients")
    @Operation(summary = "Переход к пациентам: step — шаг воронки, loss — вид потерь")
    public List<Map<String, Object>> patients(@RequestParam(required = false) String step,
                                              @RequestParam(required = false) String loss,
                                              @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) java.time.LocalDate dateFrom,
                                              @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) java.time.LocalDate dateTo,
                                              @RequestParam(required = false) String studyType,
                                              @RequestParam(required = false) String routeType) {
        return dashboard.patients(step, loss, dateFrom, dateTo, studyType, routeType);
    }
}
