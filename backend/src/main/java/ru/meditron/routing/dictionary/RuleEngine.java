package ru.meditron.routing.dictionary;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Iterator;
import java.util.Map;
import org.springframework.stereotype.Component;
import ru.meditron.routing.domain.FindingLevel;

/**
 * Применяет rules из словаря: сверху вниз, срабатывает первое правило, у которого выполнены все условия.
 * Правило может переопределить level, специалиста, срок и шаблон маршрута.
 * result: NO_ROUTE — маршрут не нужен (BELOW_THRESHOLD).
 *
 * Отсутствующие атрибуты:
 *  - булев признак, которого нет, считается false («не упомянут = нет»);
 *  - небулев атрибут (число, категория), которого нет, — условие не выполнено, правило пропускается
 *    и запоминается как «не хватило данных»;
 *  - операторы missing / orMissing видят отсутствие атрибута любого типа.
 * Ни одно правило не сработало, но какое-то пропущено из-за данных: ifMissing=TRIGGER — маршрут по умолчанию.
 *
 * Операторы: eq, ne, gt, gte, lt, lte, in, missing, orMissing.
 * Контекст: patient.age, patient.sex, protocol.studyType.
 */
@Component
public class RuleEngine {

    public RuleDecision evaluate(JsonNode entry, Map<String, Object> attributes, RuleContext context) {
        String code = entry.path("code").asText();
        boolean missingSeen = false;

        JsonNode rules = entry.path("rules");
        for (int i = 0; i < rules.size(); i++) {
            JsonNode rule = rules.get(i);
            ConditionResult cr = matchAll(rule.path("all"), attributes, context);
            if (cr == ConditionResult.NO) {
                continue;
            }
            if (cr == ConditionResult.MISSING) {
                missingSeen = true;
                continue;
            }
            String ruleRef = code + ".rules[" + i + "]";
            if ("NO_ROUTE".equals(rule.path("result").asText())) {
                return RuleDecision.notTriggered("BELOW_THRESHOLD", ruleRef);
            }
            return triggered(entry, rule, ruleRef);
        }

        if (missingSeen && "TRIGGER".equals(entry.path("ifMissing").asText())) {
            return triggered(entry, null, code + ".ifMissing");
        }
        return RuleDecision.notTriggered("BELOW_THRESHOLD", null);
    }

    /** Уровень находки по умолчанию (поле level; для старого словаря — urgent: true -> EMERGENCY). */
    public static FindingLevel defaultLevel(JsonNode entry) {
        if (entry.hasNonNull("level")) {
            return FindingLevel.parse(entry.get("level").asText(), FindingLevel.PLANNED);
        }
        return entry.path("urgent").asBoolean(false) ? FindingLevel.EMERGENCY : FindingLevel.PLANNED;
    }

    /** Самый срочный уровень, который может дать находка (у самой находки или в любом правиле). */
    public static FindingLevel maxLevel(JsonNode entry) {
        FindingLevel max = defaultLevel(entry);
        for (JsonNode rule : entry.path("rules")) {
            if (rule.hasNonNull("level")) {
                max = FindingLevel.max(max, FindingLevel.parse(rule.get("level").asText(), null));
            } else if (rule.path("urgent").asBoolean(false)) {
                max = FindingLevel.max(max, FindingLevel.EMERGENCY);
            }
        }
        return max;
    }

    private RuleDecision triggered(JsonNode entry, JsonNode rule, String ruleRef) {
        return new RuleDecision(
                true,
                text(rule, entry, "targetSpecialty"),
                intValue(rule, entry, "targetDays"),
                text(rule, entry, "routeTemplateCode"),
                level(rule, entry),
                ruleRef,
                null);
    }

    private FindingLevel level(JsonNode rule, JsonNode entry) {
        if (rule != null && rule.hasNonNull("level")) {
            return FindingLevel.parse(rule.get("level").asText(), defaultLevel(entry));
        }
        if (rule != null && rule.path("urgent").asBoolean(false)) {
            return FindingLevel.EMERGENCY;    // совместимость со словарём v1
        }
        return defaultLevel(entry);
    }

    private enum ConditionResult { YES, NO, MISSING }

    private ConditionResult matchAll(JsonNode conditions, Map<String, Object> attrs, RuleContext ctx) {
        if (conditions == null || conditions.isMissingNode() || conditions.isEmpty()) {
            return ConditionResult.YES;
        }
        boolean missing = false;
        for (JsonNode c : conditions) {
            ConditionResult r = matchOne(c, attrs, ctx);
            if (r == ConditionResult.NO) {
                return ConditionResult.NO;     // явное «нет» важнее нехватки данных
            }
            if (r == ConditionResult.MISSING) {
                missing = true;
            }
        }
        return missing ? ConditionResult.MISSING : ConditionResult.YES;
    }

    private ConditionResult matchOne(JsonNode c, Map<String, Object> attrs, RuleContext ctx) {
        String attr = c.path("attr").asText();
        Object value = ctx != null && ctx.isContextAttr(attr) ? ctx.value(attr) : attrs.get(attr);

        if (c.has("missing")) {
            boolean wantMissing = c.get("missing").asBoolean(true);
            return (value == null) == wantMissing ? ConditionResult.YES : ConditionResult.NO;
        }
        if (value == null && c.path("orMissing").asBoolean(false)) {
            return ConditionResult.YES;
        }
        if (value == null && (c.path("eq").isBoolean() || c.path("ne").isBoolean())) {
            // Признак не упомянут в протоколе = признака нет (growth, uncertain, menopause...).
            value = Boolean.FALSE;
        }
        if (value == null) {
            return ConditionResult.MISSING;
        }
        return matches(c, value) ? ConditionResult.YES : ConditionResult.NO;
    }

    private boolean matches(JsonNode condition, Object value) {
        Iterator<Map.Entry<String, JsonNode>> it = condition.fields();
        while (it.hasNext()) {
            Map.Entry<String, JsonNode> e = it.next();
            String op = e.getKey();
            JsonNode expected = e.getValue();
            boolean ok = switch (op) {
                case "attr", "orMissing", "missing" -> true;
                case "eq" -> equalsValue(expected, value);
                case "ne" -> !equalsValue(expected, value);
                case "gte" -> number(value) != null && number(value) >= expected.asDouble();
                case "gt" -> number(value) != null && number(value) > expected.asDouble();
                case "lte" -> number(value) != null && number(value) <= expected.asDouble();
                case "lt" -> number(value) != null && number(value) < expected.asDouble();
                case "in" -> {
                    boolean found = false;
                    for (JsonNode option : expected) {
                        if (option.asText().equalsIgnoreCase(String.valueOf(value))) {
                            found = true;
                        }
                    }
                    yield found;
                }
                default -> false;
            };
            if (!ok) {
                return false;
            }
        }
        return true;
    }

    private boolean equalsValue(JsonNode expected, Object value) {
        if (expected.isBoolean()) {
            return expected.asBoolean() == Boolean.parseBoolean(String.valueOf(value));
        }
        if (expected.isNumber()) {
            Double n = number(value);
            return n != null && Double.compare(n, expected.asDouble()) == 0;
        }
        return expected.asText().equalsIgnoreCase(String.valueOf(value));
    }

    private Double number(Object value) {
        if (value instanceof Number n) {
            return n.doubleValue();
        }
        try {
            return Double.parseDouble(String.valueOf(value).replace(',', '.'));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private String text(JsonNode rule, JsonNode entry, String field) {
        if (rule != null && rule.hasNonNull(field)) {
            return rule.get(field).asText();
        }
        return entry.hasNonNull(field) ? entry.get(field).asText() : null;
    }

    private Integer intValue(JsonNode rule, JsonNode entry, String field) {
        if (rule != null && rule.hasNonNull(field)) {
            return rule.get(field).asInt();
        }
        return entry.hasNonNull(field) ? entry.get(field).asInt() : null;
    }
}
