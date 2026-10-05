package ru.meditron.routing.route;

import java.time.DayOfWeek;
import java.time.Instant;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import ru.meditron.routing.domain.Finding;
import ru.meditron.routing.domain.FindingLevel;
import ru.meditron.routing.route.domain.ChainType;
import ru.meditron.routing.route.service.NotificationService;
import ru.meditron.routing.route.service.RoutePlanning;
import ru.meditron.routing.route.service.TextRenderer;
import ru.meditron.routing.route.service.WorkingDays;
import ru.meditron.routing.time.ModelTime;
import static org.junit.jupiter.api.Assertions.*;

/** Чистые правила: тип цепочки, группировка, срок, тексты, рабочие дни. */
class RoutePureRulesTest {

    private static Finding f(String specialty, int days, FindingLevel level, String template) {
        Finding f = new Finding();
        f.setTargetSpecialty(specialty);
        f.setTargetDays(days);
        f.setLevel(level);
        f.setRouteTemplateCode(template);
        return f;
    }

    @Test void chainTypeByFinding() {
        assertEquals(ChainType.EMERGENCY, RoutePlanning.chainOf(f("Дежурный хирург", 0, FindingLevel.EMERGENCY, "URGENT_ESCALATION")));
        assertEquals(ChainType.URGENT, RoutePlanning.chainOf(f("Гинеколог", 3, FindingLevel.URGENT, "CONSULT_OBSERVATION")));
        assertEquals(ChainType.OBSERVATION, RoutePlanning.chainOf(f("Гастроэнтеролог", 180, FindingLevel.PLANNED, "OBSERVATION_FOLLOWUP")));
        assertEquals(ChainType.NEAR, RoutePlanning.chainOf(f("Хирург", 30, FindingLevel.PLANNED, "SURGICAL_STANDARD")));
    }

    @Test void oneRoutePerSpecialtyWithMostUrgentDeadline() {
        List<Finding> fs = List.of(
                f("Оперирующий гинеколог", 14, FindingLevel.PLANNED, "SURGICAL_STANDARD"),
                f("Оперирующий гинеколог", 7, FindingLevel.PLANNED, "SURGICAL_STANDARD"),
                f("Хирург", 30, FindingLevel.PLANNED, "SURGICAL_STANDARD"));
        Map<String, List<Finding>> g = RoutePlanning.bySpecialty(fs);
        assertEquals(2, g.size());
        assertEquals(7, RoutePlanning.minDays(g.get("Оперирующий гинеколог")));
        assertEquals(7, RoutePlanning.mostUrgent(g.get("Оперирующий гинеколог")).getTargetDays());
    }

    @Test void urgentWinsOverObservationInGroup() {
        List<Finding> g = List.of(f("Хирург", 180, FindingLevel.PLANNED, "OBSERVATION_FOLLOWUP"),
                f("Хирург", 3, FindingLevel.URGENT, "CONSULT_OBSERVATION"));
        assertEquals(ChainType.URGENT, RoutePlanning.chainOf(RoutePlanning.mostUrgent(g)));
    }

    @Test void renderOnlineFragmentAndPlaceholders() {
        String t = "Консультация {specGen}. Очно[[ или онлайн]]: {link}";
        Map<String, String> v = Map.of("specGen", "эндокринолога", "link", "L");
        assertEquals("Консультация эндокринолога. Очно или онлайн: L", TextRenderer.render(t, v, true));
        assertEquals("Консультация эндокринолога. Очно: L", TextRenderer.render(t, v, false));
        assertEquals("{unknown}", TextRenderer.render("{unknown}", v, true));
    }

    @Test void termsAndPlurals() {
        assertEquals("7 дней", NotificationService.term(7));
        assertEquals("1 день", NotificationService.term(1));
        assertEquals("3 дня", NotificationService.term(3));
        assertEquals("6 месяцев", NotificationService.term(180));
        assertEquals("1 год", NotificationService.term(365));
        assertEquals("14 дней", NotificationService.term(14));
    }

    @Test void workingDaysSkipWeekend() {
        Instant friday = ZonedDateTime.of(2026, 10, 9, 10, 0, 0, 0, ModelTime.ZONE).toInstant();
        Instant plus3 = WorkingDays.plus(friday, 3);
        ZonedDateTime z = plus3.atZone(ModelTime.ZONE);
        assertEquals(DayOfWeek.WEDNESDAY, z.getDayOfWeek());
        assertEquals(14, z.getDayOfMonth());
    }

    @Test void modelTimeOnlyMovesForward() {
        ModelTime.reset();
        Instant before = ModelTime.now();
        ModelTime.advance(java.time.Duration.ofDays(30));
        assertTrue(ModelTime.now().isAfter(before.plus(java.time.Duration.ofDays(29))));
        assertThrows(IllegalArgumentException.class, () -> ModelTime.advance(java.time.Duration.ofMinutes(-1)));
        ModelTime.reset();
        assertEquals(0, ModelTime.offset().toMinutes());
    }
}
