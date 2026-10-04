package ru.meditron.routing.dto;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import ru.meditron.routing.domain.ProcessingStatus;
import ru.meditron.routing.domain.StudyType;

public record ProtocolShortDto(
        String id,
        String externalId,
        int version,
        ProcessingStatus status,
        StudyType studyType,
        LocalDate studyDate,
        String conclusion,
        boolean conclusionFound,
        int findingsCount,
        Instant receivedAt,
        List<Map<String, Object>> flags) {
}
