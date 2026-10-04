package ru.meditron.routing.dto;

import ru.meditron.routing.domain.FindingLevel;
import ru.meditron.routing.domain.FindingStatus;

/** Краткая находка для строки списка пациентов: самые срочные активные находки текущего протокола. */
public record TopFindingDto(
        String id,
        String code,
        String name,
        FindingStatus status,
        FindingLevel level,
        String targetSpecialty,
        Integer targetDays) {
}
