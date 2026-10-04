package ru.meditron.routing.dto;

import java.util.Map;
import ru.meditron.routing.domain.FindingStatus;

/** status: только CONFIRMED или REJECTED. */
public record FindingUpdateRequest(
        FindingStatus status,
        String code,
        Map<String, Object> attributes,
        String comment,
        String doctor) {
}
