package ru.meditron.routing.route.web;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import ru.meditron.routing.route.dto.RouteDtos.*;
import ru.meditron.routing.route.service.NotificationService;
import ru.meditron.routing.route.service.RouteQueryService;

/**
 * Маршруты и уведомления (раздел 15). Адреса совпадают с теми, что уже вызывает фронт.
 * Ручного составления, отмены маршрута и смены этапа нет — запрещено ТЗ.
 */
@RestController
@RequestMapping("/api")
@Tag(name = "Маршруты", description = "Маршрут пациента: создаётся автоматически, этапы меняются событиями МИС")
@org.springframework.boot.autoconfigure.condition.ConditionalOnProperty(name = "routes.enabled", havingValue = "true", matchIfMissing = true)
public class RouteController {
    @org.springframework.beans.factory.annotation.Autowired
    private ru.meditron.routing.route.service.RouteWriteLock writeLock;


    private final RouteQueryService query;
    private final NotificationService notifications;
    private final ru.meditron.routing.dictionary.DictionaryService dictionary;

    public RouteController(RouteQueryService query, NotificationService notifications,
                           ru.meditron.routing.dictionary.DictionaryService dictionary) {
        this.query = query;
        this.notifications = notifications;
        this.dictionary = dictionary;
    }

    @GetMapping("/patients/{patientId}/routes")
    @Operation(summary = "Маршруты пациента: сначала открытые")
    public List<RouteDto> patientRoutes(@PathVariable String patientId) {
        return query.patientRoutes(ru.meditron.routing.service.Ids.parse(patientId, "RESOURCE"));
    }

    @GetMapping("/routes")
    @Operation(summary = "Список маршрутов с фильтрами")
    public List<RouteDto> routes(@RequestParam(required = false) String stage,
                                 @RequestParam(required = false) String specialty,
                                 @RequestParam(required = false) Boolean overdue,
                                 @RequestParam(required = false) Boolean open) {
        return query.list(stage, specialty, overdue, open);
    }

    @GetMapping("/routes/{routeId}")
    @Operation(summary = "Маршрут подробно: этап, срок, дата посещения или просрочка, находки, история этапов")
    public RouteDto route(@PathVariable String routeId) {
        return query.route(routeId);
    }

    @GetMapping("/routes/{routeId}/notifications")
    @Operation(summary = "Уведомления маршрута: отправка, прочтение, запись")
    public List<NotificationDto> routeNotifications(@PathVariable String routeId) {
        return query.routeNotifications(routeId);
    }

    @GetMapping("/patients/{patientId}/notifications")
    @Operation(summary = "Все уведомления пациента")
    public List<NotificationDto> patientNotifications(@PathVariable String patientId) {
        return query.patientNotifications(ru.meditron.routing.service.Ids.parse(patientId, "RESOURCE"));
    }

    @PostMapping("/routes/{routeId}/notifications")
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    @Operation(summary = "Ручная отправка по шаблону. Без confirm при сообщении за сутки — 409 CONFIRM_REQUIRED")
    public NotificationDto send(@PathVariable String routeId, @Valid @RequestBody ManualNotificationRequest req) {
        writeLock.acquire();
        var r = query.find(routeId);
        var n = notifications.sendManual(r, req.templateCode(), req.confirm(), req.doctor());
        return query.notification(n, r);
    }

    @GetMapping("/notification-templates")
    @Operation(summary = "Шаблоны сообщений; manual=true — доступны для ручной отправки")
    public List<TemplateDto> templates() {
        return query.templates();
    }

    @GetMapping("/routes/{routeId}/notification-preview")
    @Transactional(readOnly = true)
    @Operation(summary = "Предпросмотр сообщения по шаблону без отправки и сохранения")
    public NotificationPreviewDto preview(@PathVariable String routeId, @RequestParam String templateCode) {
        return notifications.preview(query.find(routeId), templateCode);
    }

    @GetMapping("/route-templates")
    @Operation(summary = "Шаблоны маршрутов из словаря (только чтение)")
    public Object routeTemplates() {
        return dictionary.document(List.of()).path("routeTemplates");
    }
}
