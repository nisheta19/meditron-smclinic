package ru.meditron.routing.dto;

import jakarta.validation.constraints.NotBlank;
import java.util.Map;

public record FindingCreateRequest(
        @NotBlank String code,
        String protocolId,
        Map<String, Object> attributes,
        String comment,
        String doctor) {
}
