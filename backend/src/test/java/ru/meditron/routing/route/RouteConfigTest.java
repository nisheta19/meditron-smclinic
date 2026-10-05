package ru.meditron.routing.route;

import java.time.Duration;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import ru.meditron.routing.route.config.RouteConfig;
import static org.junit.jupiter.api.Assertions.*;

/** route-config.yaml соответствует утверждённому ТЗ маршрутов v1.1. */
class RouteConfigTest {
    static RouteConfig config;

    @BeforeAll static void load() throws Exception {
        config = new RouteConfig(new ClassPathResource("routing/route-config.yaml"));
    }

    @Test void durationsParse() {
        assertEquals(Duration.ofMinutes(30), RouteConfig.parse("30m"));
        assertEquals(Duration.ofHours(24), RouteConfig.parse("24h"));
        assertEquals(Duration.ofDays(5), RouteConfig.parse("5d"));
        assertThrows(IllegalArgumentException.class, () -> RouteConfig.parse("5w"));
    }

    @Test void nearChainMatchesCase() {
        var steps = config.chain("NEAR");
        assertEquals(6, steps.size());
        assertEquals("1m", steps.get(0).path("at").asText());
        assertEquals("24h", steps.get(1).path("at").asText());
        assertEquals("72h", steps.get(2).path("at").asText());
        assertEquals("CALL_PATIENT", steps.get(3).path("task").asText());
        assertEquals("5d", steps.get(3).path("at").asText());
        assertEquals("REMINDER_14D", steps.get(4).path("template").asText());
        assertEquals("NOT_ENGAGED", steps.get(5).path("action").asText());
        assertEquals("30d", steps.get(5).path("at").asText());
    }

    @Test void urgentChainFitsDeadline() {
        var steps = config.chain("URGENT");
        assertEquals("12h", steps.get(1).path("at").asText());
        assertEquals("24h", steps.get(2).path("at").asText());
        assertEquals("48h", steps.get(3).path("at").asText());
        assertEquals("MANAGER", steps.get(3).path("role").asText());
    }

    @Test void everyChainTemplateHasFullAndShortText() {
        for (String chain : new String[] {"NEAR", "URGENT", "OBSERVATION"}) {
            for (var step : config.chain(chain)) {
                if (step.has("template")) {
                    var t = config.template(step.path("template").asText()).orElseThrow();
                    assertFalse(t.path("full").asText().isBlank());
                    assertFalse(t.path("short").asText().isBlank());
                }
            }
        }
        for (String code : new String[] {"NO_SHOW", "BOOKING_CONFIRMED", "OBSERVATION_REMINDER", "CONTROL_BOOKED", "CONTROL_RECOMMENDED"}) {
            assertTrue(config.template(code).isPresent(), code);
        }
    }

    @Test void approvedPhraseInFullTextsNamingSpecialist() {
        String phrase = "Консультация нужна, чтобы уточнить результат исследования";
        assertTrue(config.template("INITIAL").orElseThrow().path("full").asText().contains(phrase));
        assertTrue(config.template("REMINDER_24H").orElseThrow().path("full").asText().contains(phrase));
        assertFalse(config.template("INITIAL").orElseThrow().path("short").asText().contains("{specGen}"));
    }

    @Test void specialistsAndOnline() {
        assertArrayEquals(new String[] {"хирурга", "хирургом", "хирургу"}, config.specialistCases("Хирург"));
        assertEquals("профильного специалиста", config.specialistCases("Неизвестный")[0]);
        assertTrue(config.onlineAllowed("Эндокринолог"));
        assertFalse(config.onlineAllowed("Хирург"));
        assertFalse(config.hasSlots("Дежурный хирург"));
        assertFalse(config.hasSlots("Координатор (ручной разбор)"));
        assertTrue(config.hasSlots("Уролог"));
    }

    @Test void escalationLadderAndDutyMapping() {
        assertEquals(Duration.ofMinutes(15), config.duration("/escalation/confirmTimeout"));
        assertEquals(3, config.at("/escalation/ladder").size());
        assertEquals(Duration.ofHours(1), config.duration("/escalation/contactTimeout"));
        assertEquals("Флеболог / хирург", config.profileForDuty("Дежурный хирург / флеболог").orElseThrow());
        assertTrue(config.at("/escalation/outcomes/PATIENT_REFUSED/commentRequired").asBoolean());
    }

    @Test void controlTerms() {
        assertEquals(Duration.ofDays(7), config.duration("/control/afterSurgery/target"));
        assertEquals(Duration.ofDays(2), config.duration("/control/afterSurgery/window"));
        assertEquals(Duration.ofDays(10), config.duration("/control/afterDiagnostic/target"));
        assertEquals(Duration.ofDays(3), config.duration("/control/afterDiagnostic/window"));
        assertEquals(3, config.integer("/hospitalization/dateDeadlineWorkingDays", 0));
    }
}
