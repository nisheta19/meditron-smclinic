package ru.meditron.routing.dictionary;

import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import ru.meditron.routing.domain.*;
import static org.junit.jupiter.api.Assertions.*;

class DictionaryRulesTest {
    static DictionaryService dictionary;
    static final RuleEngine rules = new RuleEngine();
    static final RuleContext adult = new RuleContext(40, Sex.F, StudyType.PELVIS_FEMALE);
    @BeforeAll static void load() throws Exception {
        dictionary = new DictionaryService(new ClassPathResource("dictionary/findings-dictionary.yaml"));
        dictionary.load();
    }
    RuleDecision route(String code, Map<String,Object> attrs) {
        return rules.evaluate(dictionary.find(code).orElseThrow(), attrs, adult);
    }
    @Test void fullDictionaryPreservesSharedPolicies() {
        var document = dictionary.document(dictionary.all());
        assertEquals("dict-v2.1", document.path("version").asText());
        assertEquals(48, document.path("findings").size());
        assertTrue(document.path("ml").has("returnPolicy"));
        assertTrue(document.path("flags").has("NO_CONCLUSION"));
    }
    @Test void certainPolypHasSevenDayRoute() {
        var d = route("ENDOMETRIAL_POLYP", Map.of("uncertain", false));
        assertTrue(d.triggered()); assertEquals(7, d.targetDays());
    }
    @Test void suspectedPolypHasFourteenDayRoute() {
        assertEquals(14, route("ENDOMETRIAL_POLYP", Map.of("uncertain", true)).targetDays());
    }
    @Test void missingBooleanFollowsDictionaryPolicy() {
        assertEquals(7, route("ENDOMETRIAL_POLYP", Map.of()).targetDays());
    }
    @Test void smallStableGallbladderPolypHasObservationRoute() {
        assertEquals(180, route("GALLBLADDER_POLYP", Map.of("sizeMm", 3, "growth", false)).targetDays());
    }
    @Test void largeGallbladderPolypTriggersRoute() {
        assertTrue(route("GALLBLADDER_POLYP", Map.of("sizeMm", 12)).triggered());
    }
    @Test void thrombosisIsEmergency() {
        assertEquals(FindingLevel.EMERGENCY, route("DEEP_VEIN_THROMBOSIS", Map.of()).level());
    }
    @Test void breastCategoryTwoIsNotRoute() {
        assertFalse(route("BREAST_LESION", Map.of("birads", 2)).triggered());
    }
    @Test void breastCategoryFiveUsesThreeDaysAndDictionaryLevel() {
        var d=route("BREAST_LESION", Map.of("birads", 5));
        assertEquals(3, d.targetDays());
        assertEquals(FindingLevel.PLANNED, d.level());
    }
    @Test void conditionsAndContextDoNotModifyInput() {
        Map<String,Object> attrs = Map.of("uncertain", true);
        assertEquals(7, rules.evaluate(dictionary.find("ENDOMETRIAL_POLYP").orElseThrow(), attrs,
                new RuleContext(60, Sex.F, StudyType.PELVIS_FEMALE)).targetDays());
        assertEquals(Map.of("uncertain", true), attrs);
    }
}
