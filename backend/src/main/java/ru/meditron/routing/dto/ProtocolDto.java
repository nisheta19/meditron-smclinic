package ru.meditron.routing.dto;

import java.util.List;
import java.util.Map;

public record ProtocolDto(
        ProtocolShortDto protocol,
        String patientId,
        String text,
        String modelVersion,
        ErrorResponse error,
        List<FindingDto> findings,
        List<Map<String, Object>> notTriggered) {
}
