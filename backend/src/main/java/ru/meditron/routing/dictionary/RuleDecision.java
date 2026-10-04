package ru.meditron.routing.dictionary;

import ru.meditron.routing.domain.FindingLevel;

/** Итог применения правил словаря к одной находке. */
public record RuleDecision(
        boolean triggered,
        String targetSpecialty,
        Integer targetDays,
        String routeTemplateCode,
        FindingLevel level,
        String matchedRule,
        String reason) {

    public static RuleDecision notTriggered(String reason, String matchedRule) {
        return new RuleDecision(false, null, null, null, null, matchedRule, reason);
    }

    /** Совместимость с полем urgent: экстренно = urgent. */
    public boolean urgent() {
        return level == FindingLevel.EMERGENCY;
    }
}
