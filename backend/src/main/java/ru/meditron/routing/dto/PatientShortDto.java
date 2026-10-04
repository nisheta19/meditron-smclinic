package ru.meditron.routing.dto;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import ru.meditron.routing.domain.FindingLevel;
import ru.meditron.routing.domain.ReviewState;
import ru.meditron.routing.domain.Sex;
import ru.meditron.routing.domain.StudyType;

public record PatientShortDto(
        String id,
        String externalId,
        String fullName,
        String lastName,
        String firstName,
        String middleName,
        String shortName,
        LocalDate birthDate,
        Integer age,
        Sex sex,
        String cardNumber,
        ReviewState reviewState,
        boolean needsRouteReview,
        FindingLevel maxLevel,
        Instant receivedAt,
        int pendingFindings,
        int activeRoutes,
        LocalDate lastStudyDate,
        StudyType studyType,
        int activeFindings,
        List<TopFindingDto> topFindings) {
}
