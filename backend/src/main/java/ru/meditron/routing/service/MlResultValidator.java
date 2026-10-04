package ru.meditron.routing.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;
import ru.meditron.routing.dictionary.DictionaryService;
import ru.meditron.routing.domain.ProcessingStatus;
import ru.meditron.routing.dto.EvidenceDto;
import ru.meditron.routing.dto.MlResultRequest;
import ru.meditron.routing.exception.BadRequestException;

/** Structural validation; clinical thresholds remain exclusively in the dictionary. */
@Component
public class MlResultValidator {
    private final DictionaryService dictionary;
    public MlResultValidator(DictionaryService dictionary) { this.dictionary = dictionary; }

    public void validate(MlResultRequest r) {
        require(!r.patient().birthDate().isAfter(r.protocol().studyDate()), "Дата рождения позже исследования");
        if (r.status() == ProcessingStatus.DONE) {
            require(r.conclusion() != null && r.conclusionFound() != null && r.findings() != null && r.flags() != null,
                    "DONE требует conclusion, conclusionFound, findings, flags");
            require(dictionary.version().equals(r.dictionaryVersion()), "Версия словаря ML не совпадает с бэкендом");
            require(r.error() == null, "DONE не должен содержать error");
        } else {
            require(r.findings() == null || r.findings().isEmpty(), "FAILED/ANNULLED не содержат findings");
            if (r.status() == ProcessingStatus.FAILED) require(r.error() != null, "FAILED требует error");
        }
        flags(r.flags());
        if (r.findings() != null) for (var f : r.findings()) {
            JsonNode entry = code(f.code(), r.protocol().studyType().name());
            evidence(r.text(), f.evidence(), true);
            flags(f.flags());
            require(f.confidence() == null || Double.isFinite(f.confidence()) && f.confidence() >= 0 && f.confidence() <= 1,
                    "confidence должен быть числом 0–1");
            attributes(entry, f.attributes());
        }
        if (r.notTriggered() != null) for (var f : r.notTriggered()) {
            code(f.code(), r.protocol().studyType().name());
            require(Set.of("NEGATION", "NORMAL", "POST_SURGERY").contains(f.reason()), "Неизвестная причина notTriggered");
            evidence(r.text(), f.evidence(), false);
        }
    }

    private JsonNode code(String code, String studyType) {
        JsonNode entry = dictionary.find(code).orElseThrow(() -> new BadRequestException("UNKNOWN_FINDING_CODE", "Неизвестный код " + code));
        boolean allowed = false;
        for (JsonNode kind : entry.path("studyTypes")) if (studyType.equals(kind.asText())) allowed = true;
        require(allowed, "Код " + code + " не относится к studyType " + studyType);
        return entry;
    }

    public void attributes(JsonNode entry, Map<String, Object> attrs) {
        if (attrs == null) return;
        Set<String> allowed = new HashSet<>();
        entry.path("attributes").forEach(n -> allowed.add(n.asText()));
        for (var attr : attrs.entrySet()) {
            require(allowed.contains(attr.getKey()), "Неизвестный атрибут " + attr.getKey());
            require(attr.getValue() != null, "Отсутствующие атрибуты нужно опустить");
            if (attr.getValue() instanceof Number number) {
                require(Double.isFinite(number.doubleValue()) && number.doubleValue() >= 0, "Некорректное числовое значение");
            }
        }
        // Types used in routing are inferred from YAML, so new rules need no Java allowlist.
        for (JsonNode rule : entry.path("rules")) for (JsonNode condition : rule.path("all")) {
            Object value = attrs.get(condition.path("attr").asText());
            if (value == null) continue;
            for (String op : List.of("eq", "ne", "gt", "gte", "lt", "lte")) {
                JsonNode expected = condition.get(op);
                if (expected == null) continue;
                if (expected.isBoolean()) require(value instanceof Boolean, "Ожидается boolean для " + condition.path("attr").asText());
                if (expected.isNumber()) require(value instanceof Number, "Ожидается число для " + condition.path("attr").asText());
            }
        }
    }

    private void flags(List<MlResultRequest.MlFlag> flags) {
        if (flags == null) return;
        Set<String> seen = new HashSet<>();
        for (var flag : flags) {
            require(seen.add(flag.code()), "Повторяющийся флаг");
            require(dictionary.flag(flag.code()).map(n -> "ML".equalsIgnoreCase(n.path("setBy").asText())).orElse(false),
                    "Неизвестный флаг ML: " + flag.code());
        }
    }

    private void evidence(String text, EvidenceDto evidence, boolean coordinatesRequired) {
        Integer start = evidence.start(), end = evidence.end();
        if (text == null) {
            require(start == null && end == null, "Координаты evidence требуют полного text");
            return;
        }
        require(text.contains(evidence.text()), "Цитата evidence отсутствует в text");
        if (coordinatesRequired || start != null || end != null) {
            int length = text.codePointCount(0, text.length());
            require(start != null && end != null && start >= 0 && start < end && end <= length, "Неверные координаты evidence");
            // Python offsets count Unicode code points; Java String indices count UTF-16 units.
            require(text.substring(text.offsetByCodePoints(0, start), text.offsetByCodePoints(0, end)).equals(evidence.text()),
                    "Координаты evidence не совпадают с цитатой");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new BadRequestException("INVALID_ML_RESULT", message);
    }
}
