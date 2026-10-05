package ru.meditron.routing.route.service;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import ru.meditron.routing.domain.Finding;
import ru.meditron.routing.domain.FindingLevel;
import ru.meditron.routing.route.domain.ChainType;

/** Чистые правила разделов 4.2 и 4.5: группировка, тип цепочки, срок. Без БД — легко тестировать. */
public final class RoutePlanning {

    private RoutePlanning() {
    }

    /** Тип цепочки по находке (4.5). */
    public static ChainType chainOf(Finding f) {
        if (f.getLevel() == FindingLevel.EMERGENCY) {
            return ChainType.EMERGENCY;
        }
        if (f.getLevel() == FindingLevel.URGENT) {
            return ChainType.URGENT;
        }
        if ("OBSERVATION_FOLLOWUP".equals(f.getRouteTemplateCode())) {
            return ChainType.OBSERVATION;
        }
        return ChainType.NEAR;
    }

    /** Порядок срочности: экстренный > срочный > ближний > наблюдение. */
    public static int rank(ChainType t) {
        return switch (t) {
            case EMERGENCY -> 0;
            case URGENT -> 1;
            case NEAR -> 2;
            case OBSERVATION -> 3;
        };
    }

    /** Самая срочная находка группы: по типу цепочки, затем по сроку. */
    public static Finding mostUrgent(List<Finding> group) {
        return group.stream()
                .min(Comparator.<Finding>comparingInt(f -> rank(chainOf(f)))
                        .thenComparing(f -> f.getTargetDays() == null ? Integer.MAX_VALUE : f.getTargetDays()))
                .orElseThrow();
    }

    public static int minDays(List<Finding> group) {
        return group.stream().map(Finding::getTargetDays).filter(d -> d != null).min(Integer::compare).orElse(30);
    }

    /** Один маршрут на специалиста (4.2). Порядок групп стабилен. */
    public static Map<String, List<Finding>> bySpecialty(List<Finding> findings) {
        return findings.stream().collect(Collectors.groupingBy(Finding::getTargetSpecialty, LinkedHashMap::new,
                Collectors.toList()));
    }
}
