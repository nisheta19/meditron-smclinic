package ru.meditron.routing.route.service;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Predicate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.repository.PatientRepository;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.CloseReason;
import ru.meditron.routing.route.domain.Escalation;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.domain.RouteStage;
import ru.meditron.routing.route.repo.EscalationRepository;
import ru.meditron.routing.route.repo.RouteRepository;
import ru.meditron.routing.time.ModelTime;

/** Дашборд-воронка (раздел 17): по данным прототипа, проценты от предыдущего шага, переход к пациентам. */
@Service
@Transactional(readOnly = true)
public class DashboardService {

    /** Шаги воронки 17.1: код вехи → подпись. */
    public static final Map<String, String> STEPS = new LinkedHashMap<>();

    static {
        STEPS.put("CREATED", "Маршрут создан");
        STEPS.put("NOTIFIED", "Получили уведомление");
        STEPS.put("BOOKED", "Записались");
        STEPS.put("VISIT", "Приём состоялся");
        STEPS.put("SURGERY_RECOMMENDED", "Операция рекомендована");
        STEPS.put("REFERRED", "Создано направление");
        STEPS.put("DATE_SET", "Назначена госпитализация");
        STEPS.put("HOSPITALIZED", "Госпитализированы");
        STEPS.put("OPERATED", "Оперированы");
        STEPS.put("CONTROL_VISIT", "Контрольный визит");
    }

    public static final Map<String, String> LOSSES = Map.of(
            "NOT_ENGAGED", "Не вовлечены",
            "PATIENT_REFUSED", "Отказ пациента",
            "OTHER_ORGANIZATION", "Обратились в другую организацию",
            "OVERDUE", "Просрочены на текущем шаге");

    private final RouteRepository routes;
    private final EscalationRepository escalations;
    private final PatientRepository patients;
    private final RouteConfig config;

    public DashboardService(RouteRepository routes, EscalationRepository escalations, PatientRepository patients,
                            RouteConfig config) {
        this.routes = routes;
        this.escalations = escalations;
        this.patients = patients;
        this.config = config;
    }

    public List<Map<String, Object>> funnel(LocalDate from, LocalDate to, String studyType, String routeType) {
        List<Route> rs = filtered(from, to, studyType, routeType);
        List<Map<String, Object>> out = new ArrayList<>();
        Long prev = null;
        for (Map.Entry<String, String> s : STEPS.entrySet()) {
            long n = rs.stream().filter(r -> r.hasMilestone(s.getKey())).count();
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("step", s.getKey());
            m.put("title", s.getValue());
            m.put("count", n);
            m.put("percentOfPrevious", prev == null || prev == 0 ? null : Math.round(n * 100.0 / prev));
            out.add(m);
            prev = n;
        }
        return out;
    }

    public List<Map<String, Object>> losses(LocalDate from, LocalDate to, String studyType, String routeType) {
        List<Route> rs = filtered(from, to, studyType, routeType);
        List<Map<String, Object>> out = new ArrayList<>();
        for (String code : List.of("NOT_ENGAGED", "PATIENT_REFUSED", "OTHER_ORGANIZATION", "OVERDUE")) {
            out.add(Map.of("loss", code, "title", LOSSES.get(code), "count", rs.stream().filter(loss(code)).count()));
        }
        return out;
    }

    public Map<String, Object> escalationMetrics(LocalDate from, LocalDate to) {
        Instant f = start(from), t = end(to);
        List<Escalation> es = escalations.findAll().stream()
                .filter(e -> !e.getStartedAt().isBefore(f) && e.getStartedAt().isBefore(t)).toList();
        long confirmLimit = config.duration("/escalation/confirmTimeout").toMinutes();
        long acceptLimit = RouteConfig.parse(config.at("/escalation/ladder").get(0).path("timeout").asText("10m")).toMinutes();
        long contactLimit = config.duration("/escalation/contactTimeout").toMinutes();
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("total", es.size());
        m.put("avgMinutesToConfirm", avg(es, Escalation::getStartedAt, Escalation::getConfirmedAt));
        m.put("avgMinutesToAccept", avg(es, Escalation::getConfirmedAt, Escalation::getAcceptedAt));
        m.put("avgMinutesToContact", avg(es, Escalation::getAcceptedAt, Escalation::getContactedAt));
        long within = es.stream().filter(e -> ok(e.getStartedAt(), e.getConfirmedAt(), confirmLimit)
                && ok(e.getConfirmedAt(), e.getAcceptedAt(), acceptLimit)
                && ok(e.getAcceptedAt(), e.getContactedAt(), contactLimit)).count();
        long finished = es.stream().filter(e -> e.getContactedAt() != null).count();
        m.put("withinNormsPercent", finished == 0 ? null : Math.round(within * 100.0 / finished));
        Map<String, Long> outcomes = new LinkedHashMap<>();
        config.at("/escalation/outcomes").fieldNames().forEachRemaining(k ->
                outcomes.put(k, es.stream().filter(e -> k.equals(e.getOutcome())).count()));
        m.put("outcomes", outcomes);
        return m;
    }

    /** Переход к списку пациентов: step — шаг воронки, loss — вид потерь. */
    public List<Map<String, Object>> patients(String step, String loss, LocalDate from, LocalDate to,
                                              String studyType, String routeType) {
        Predicate<Route> p;
        if (step != null) {
            if (!STEPS.containsKey(step)) {
                throw new BadRequestException("UNKNOWN_STEP", "Неизвестный шаг воронки: " + step);
            }
            p = r -> r.hasMilestone(step);
        } else if (loss != null) {
            if (!LOSSES.containsKey(loss)) {
                throw new BadRequestException("UNKNOWN_LOSS", "Неизвестный вид потерь: " + loss);
            }
            p = loss(loss);
        } else {
            throw new BadRequestException("STEP_REQUIRED", "Укажите step или loss");
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Route r : filtered(from, to, studyType, routeType)) {
            if (!p.test(r)) {
                continue;
            }
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("patientId", r.getPatientId().toString());
            patients.findById(r.getPatientId()).ifPresent(pt -> {
                m.put("fullName", pt.getFullName());
                m.put("shortName", pt.name().shortName());
            });
            m.put("routeId", r.getId().toString());
            m.put("specialty", r.getSpecialty());
            m.put("stage", r.getStage().name());
            m.put("dueAt", r.getDueAt());
            out.add(m);
        }
        return out;
    }

    private Predicate<Route> loss(String code) {
        return switch (code) {
            case "NOT_ENGAGED" -> r -> r.getStage() == RouteStage.NOT_ENGAGED;
            case "PATIENT_REFUSED" -> r -> r.getCloseReason() == CloseReason.PATIENT_REFUSED;
            case "OTHER_ORGANIZATION" -> r -> r.getCloseReason() == CloseReason.OTHER_ORGANIZATION;
            case "OVERDUE" -> r -> r.isOpen() && (RouteQueryService.overdueDays(r) != null || r.isSlaOverdue());
            default -> r -> false;
        };
    }

    private List<Route> filtered(LocalDate from, LocalDate to, String studyType, String routeType) {
        Instant f = start(from), t = end(to);
        return routes.findByCreatedAtBetween(f, t).stream()
                .filter(r -> studyType == null || studyType.equals(r.getStudyType()))
                .filter(r -> routeType == null || routeType.equals(config.routeType(r.getTemplateCode())))
                .toList();
    }

    private static Instant start(LocalDate d) {
        return d == null ? Instant.EPOCH : d.atStartOfDay(ModelTime.ZONE).toInstant();
    }

    private static Instant end(LocalDate d) {
        return d == null ? ModelTime.now().plus(Duration.ofDays(1)) : d.plusDays(1).atStartOfDay(ModelTime.ZONE).toInstant();
    }

    private static boolean ok(Instant a, Instant b, long limitMinutes) {
        return a == null || b == null || Duration.between(a, b).toMinutes() <= limitMinutes;
    }

    private static Long avg(List<Escalation> es, java.util.function.Function<Escalation, Instant> a,
                            java.util.function.Function<Escalation, Instant> b) {
        List<Long> mins = es.stream().filter(e -> a.apply(e) != null && b.apply(e) != null)
                .map(e -> Duration.between(a.apply(e), b.apply(e)).toMinutes()).filter(Objects::nonNull).toList();
        return mins.isEmpty() ? null : Math.round(mins.stream().mapToLong(Long::longValue).average().orElse(0));
    }
}
