package ru.meditron.routing.controller;

import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.*;
import ru.meditron.routing.dictionary.DictionaryService;
import ru.meditron.routing.dictionary.RuleEngine;
import ru.meditron.routing.domain.FindingLevel;

@RestController
@RequestMapping("/api/dictionary")
@Tag(name = "Dictionary", description = "Словарь находок (findings-dictionary.yaml)")
public class DictionaryController {

    private final DictionaryService dictionary;

    public DictionaryController(DictionaryService dictionary) {
        this.dictionary = dictionary;
    }

    @GetMapping("/findings")
    @Operation(summary = "Словарь: краткий вид для фронта; full=true — полные записи для ML (атрибуты, правила извлечения, ловушки)")
    public Object findings(@RequestParam(required = false) String studyType,
                                 @RequestParam(required = false) String q,
                                 @RequestParam(defaultValue = "false") boolean full) {
        List<Object> result = new ArrayList<>();
        for (JsonNode e : dictionary.all()) {
            if (studyType != null && !containsText(e.path("studyTypes"), studyType)) {
                continue;
            }
            List<String> synonyms = dictionary.synonyms(e);
            if (q != null && !q.isBlank()) {
                String needle = q.toLowerCase();
                boolean hit = e.path("name").asText().toLowerCase().contains(needle)
                        || synonyms.stream().anyMatch(s -> s.toLowerCase().contains(needle));
                if (!hit) {
                    continue;
                }
            }
            if (full) {
                result.add(e);
                continue;
            }
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("code", e.path("code").asText());
            m.put("name", e.path("name").asText());
            m.put("active", e.path("active").asBoolean(false));
            FindingLevel level = RuleEngine.defaultLevel(e);
            FindingLevel maxLevel = RuleEngine.maxLevel(e);
            m.put("level", level);
            m.put("maxLevel", maxLevel);
            m.put("urgent", maxLevel == FindingLevel.EMERGENCY);
            m.put("studyTypes", e.path("studyTypes"));
            m.put("targetSpecialty", e.path("targetSpecialty").asText(null));
            m.put("routeTemplateCode", e.path("routeTemplateCode").asText(null));
            m.put("targetDays", e.hasNonNull("targetDays") ? e.get("targetDays").asInt() : null);
            m.put("synonyms", synonyms);
            m.put("dictionaryVersion", dictionary.version());
            result.add(m);
        }
        return full ? dictionary.document(result) : result;
    }

    private boolean containsText(JsonNode array, String value) {
        for (JsonNode n : array) {
            if (n.asText().equalsIgnoreCase(value)) {
                return true;
            }
        }
        return false;
    }
}
