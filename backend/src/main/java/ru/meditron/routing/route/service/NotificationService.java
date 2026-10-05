package ru.meditron.routing.route.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.exception.ConflictException;
import ru.meditron.routing.repository.PatientRepository;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.ChainType;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.domain.RouteNotification;
import ru.meditron.routing.route.domain.RouteTimer;
import ru.meditron.routing.route.repo.RouteNotificationRepository;
import ru.meditron.routing.time.ModelTime;

/**
 * Сообщения пациенту через CRM клиники (разделы 6.5–6.7, 8). Мы решаем «что» и «когда»,
 * канал и тихие часы — зона CRM. У каждого сообщения полная и короткая (для SMS) версия.
 */
@Service
public class NotificationService {

    public static final DateTimeFormatter DATE = DateTimeFormatter.ofPattern("d MMMM yyyy", new Locale("ru"));
    public static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm");

    private final RouteNotificationRepository notifications;
    private final RouteConfig config;
    private final TimerService timers;
    private final JournalService journal;
    private final PatientRepository patients;
    private final ru.meditron.routing.route.repo.EscalationRepository escalations;

    public NotificationService(RouteNotificationRepository notifications, RouteConfig config, TimerService timers,
                               JournalService journal, PatientRepository patients, ru.meditron.routing.route.repo.EscalationRepository escalations) {
        this.notifications = notifications;
        this.config = config;
        this.timers = timers;
        this.journal = journal;
        this.patients = patients;
        this.escalations = escalations;
    }

    private boolean hasEmergency(Route route) {
        return escalations.findByPatientIdOrderByStartedAtDesc(route.getPatientId()).stream()
                .anyMatch(e -> e.getStep() != ru.meditron.routing.route.domain.Escalation.Step.CLOSED);
    }

    /**
     * Автоматическое сообщение. Если лимит «одно сообщение в сутки на пациента» исчерпан, сообщение
     * откладывается до момента, когда лимит позволит, и не теряется (6.5).
     */
    public RouteNotification sendAuto(Route route, String templateCode, Map<String, String> extra, String basis) {
        if (route.getChainType() == ChainType.EMERGENCY || hasEmergency(route)) {
            return null; // экстренным пациентам система не пишет
        }
        Instant now = ModelTime.now();
        List<RouteNotification> recent = notifications.findByPatientIdAndSentAtAfter(route.getPatientId(),
                now.minus(Duration.ofDays(1))).stream().filter(n -> !n.getSentAt().isAfter(now)).toList();
        int limit = config.integer("/messages/dailyLimitPerPatient", 1);
        if (recent.size() >= limit) {
            Instant earliest = recent.stream().map(RouteNotification::getSentAt).min(Comparator.naturalOrder()).orElse(now);
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("template", templateCode);
            payload.put("basis", basis);
            payload.put("extra", extra == null ? Map.of() : extra);
            timers.schedule(RouteTimer.Kind.DEFERRED_MESSAGE, "chain", earliest.plus(Duration.ofDays(1)),
                    route.getPatientId(), route.getId(), null, payload);
            journal.entry("SYSTEM", "MESSAGE_DEFERRED").basis("Лимит сообщений в сутки; " + basis)
                    .patient(route.getPatientId()).route(route.getId()).detail("template", templateCode).save();
            return null;
        }
        return create(route, templateCode, extra, false, "SYSTEM", basis);
    }

    /** Ручная отправка координатором: только шаблоны, без подтверждения — предупреждение (6.7). */
    public RouteNotification sendManual(Route route, String templateCode, boolean confirm, String by) {
        validateManual(route, templateCode);
        List<RouteNotification> recent = notifications.findByPatientIdAndSentAtAfter(route.getPatientId(),
                ModelTime.now().minus(Duration.ofDays(1)));
        if (!recent.isEmpty() && !confirm) {
            Instant last = recent.stream().map(RouteNotification::getSentAt).max(Comparator.naturalOrder()).get();
            throw new ConflictException("CONFIRM_REQUIRED", "Пациенту уже отправлено сообщение сегодня в "
                    + TIME.format(last.atZone(ModelTime.ZONE)) + ". Отправить ещё одно?");
        }
        return create(route, templateCode, Map.of(), true, by, "Ручная отправка координатором");
    }

    private void validateManual(Route route, String templateCode) {
        JsonNode t = config.template(templateCode)
                .orElseThrow(() -> new BadRequestException("TEMPLATE_NOT_FOUND", "Шаблон " + templateCode + " не найден"));
        if (!t.path("manual").asBoolean(true)) {
            throw new BadRequestException("TEMPLATE_NOT_MANUAL", "Этот шаблон отправляется только автоматически");
        }
        if (!route.isOpen()) {
            throw new ConflictException("ROUTE_CLOSED", "Маршрут закрыт");
        }
        if (route.getChainType() == ChainType.EMERGENCY || hasEmergency(route)) {
            throw new ConflictException("EMERGENCY_NO_PATIENT_MESSAGES",
                    "Экстренная находка: пациенту сообщения не отправляются, только эскалация персоналу");
        }
    }

    /** Exactly the text used by sendManual, without persistence, timers or CRM events. */
    public ru.meditron.routing.route.dto.RouteDtos.NotificationPreviewDto preview(Route route, String templateCode) {
        validateManual(route, templateCode);
        var n = draft(route, templateCode, Map.of());
        return new ru.meditron.routing.route.dto.RouteDtos.NotificationPreviewDto(
                templateCode, n.getFullText(), n.getShortText());
    }

    private RouteNotification create(Route route, String templateCode, Map<String, String> extra, boolean manual,
                                     String by, String basis) {
        RouteNotification n = draft(route, templateCode, extra);
        n.setManual(manual);
        n.setSentBy(by);
        n.setSentAt(ModelTime.now());
        n.getStatusHistory().add(Map.of("status", "SENT", "at", n.getSentAt().toString()));
        RouteNotification saved = notifications.save(n);
        if (route.getStage() == ru.meditron.routing.route.domain.RouteStage.CREATED && "INITIAL".equals(templateCode)) {
            route.setStage(ru.meditron.routing.route.domain.RouteStage.NOTIFIED);
            route.setUpdatedAt(ModelTime.now());
            route.getStageHistory().add(Map.of("stage", "NOTIFIED", "at", ModelTime.now().toString(), "basis", "Первое сообщение передано в CRM"));
            journal.entry("SYSTEM", "ROUTE_STAGE_CHANGED").basis("Первое сообщение передано в CRM")
                    .patient(route.getPatientId()).route(route.getId()).detail("stage", "NOTIFIED").save();
        }
        journal.entry(manual ? "COORDINATOR" : "SYSTEM", "MESSAGE_SENT").by(by).basis(basis)
                .patient(route.getPatientId()).route(route.getId())
                .detail("template", templateCode).detail("messageId", saved.getId()).detail("manual", manual).save();
        return saved;
    }

    private RouteNotification draft(Route route, String templateCode, Map<String, String> extra) {
        JsonNode t = config.template(templateCode)
                .orElseThrow(() -> new IllegalStateException("Нет шаблона " + templateCode + " в route-config.yaml"));
        Map<String, String> values = values(route, extra);
        boolean online = ScheduleService.onlineAllowed(route, config);
        RouteNotification n = new RouteNotification();
        n.setRouteId(route.getId());
        n.setPatientId(route.getPatientId());
        n.setTemplateCode(templateCode);
        n.setFullText(TextRenderer.render(t.path("full").asText(), values, online));
        n.setShortText(TextRenderer.render(t.path("short").asText(), values, online));
        if (java.util.regex.Pattern.compile("\\{[A-Za-z]+}").matcher(n.getFullText() + n.getShortText()).find())
            throw new BadRequestException("TEMPLATE_CONTEXT_REQUIRED", "Для шаблона не хватает данных текущего этапа маршрута");
        n.setPreferredChannel(config.text("/messages/preferredChannel", "PERSONAL_ACCOUNT"));
        n.getLinks().put("booking", values.get("link"));
        if (online) {
            n.getLinks().put("online", values.get("onlineLink"));
        }
        List<String> buttons = new ArrayList<>();
        t.path("buttons").forEach(b -> buttons.add(b.asText()));
        n.setButtons(buttons);
        return n;
    }

    /** Значения подстановок для шаблонов. */
    public Map<String, String> values(Route route, Map<String, String> extra) {
        String[] cases = config.specialistCases(route.getSpecialty());
        Map<String, String> v = new LinkedHashMap<>();
        v.put("specGen", cases[0]);
        v.put("specIns", cases[1]);
        v.put("specDat", cases[2]);
        v.put("link", config.text("/messages/bookingLink", "").replace("{routeId}", route.getId().toString()));
        v.put("onlineLink", config.text("/messages/onlineLink", "").replace("{routeId}", route.getId().toString()));
        patients.findById(route.getPatientId()).ifPresent(p -> {
            String name = ((p.getFirstName() == null ? "" : p.getFirstName()) + " "
                    + (p.getMiddleName() == null ? "" : p.getMiddleName())).trim();
            v.put("name", name.isEmpty() ? p.getFullName() : name);
        });
        if (route.getControlAt() != null) {
            long days = Math.max(0, (long) Math.ceil(Duration.between(ModelTime.now(), route.getControlAt()).toSeconds() / 86400.0));
            v.put("term", term(days));
            v.put("n", String.valueOf(days));
        }
        if (extra != null) {
            v.putAll(extra);
        }
        return v;
    }

    /** Подстановки даты, времени и места записи. */
    public static Map<String, String> appointmentValues(Instant dateTime, String place) {
        LocalDateTime local = LocalDateTime.ofInstant(dateTime, ModelTime.ZONE);
        Map<String, String> v = new LinkedHashMap<>();
        v.put("date", DATE.format(local));
        v.put("time", TIME.format(local));
        v.put("place", place == null ? "" : place);
        return v;
    }

    /** «7 дней», «6 месяцев» — для {term}. */
    public static String term(long days) {
        if (days >= 360 && days % 365 == 0) {
            return plural(days / 365, "год", "года", "лет");
        }
        if (days >= 28 && days % 30 == 0) {
            return plural(days / 30, "месяц", "месяца", "месяцев");
        }
        return plural(days, "день", "дня", "дней");
    }

    static String plural(long n, String one, String few, String many) {
        long m10 = n % 10, m100 = n % 100;
        String w = m10 == 1 && m100 != 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
        return n + " " + w;
    }

    /** Есть ли у пациента сообщения за последние сутки (для предупреждения в интерфейсе). */
    public boolean sentWithinDay(UUID patientId) {
        return !notifications.findByPatientIdAndSentAtAfter(patientId, ModelTime.now().minus(Duration.ofDays(1))).isEmpty();
    }
}
