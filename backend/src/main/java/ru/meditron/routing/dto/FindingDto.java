package ru.meditron.routing.dto;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import ru.meditron.routing.domain.FindingLevel;
import ru.meditron.routing.domain.FindingSource;
import ru.meditron.routing.domain.FindingStatus;

public record FindingDto(
        String id,
        String patientId,
        String protocolId,
        String code,
        String name,
        FindingStatus status,
        FindingSource source,
        EvidenceDto evidence,
        Map<String, Object> attributes,
        Double confidence,
        String modelVersion,
        String ruleVersion,
        String matchedRule,
        String targetSpecialty,
        Integer targetDays,
        FindingLevel level,
        boolean urgent,
        List<Map<String, Object>> flags,
        String routeId,
        String reviewedBy,
        Instant reviewedAt,
        String comment) {
}
