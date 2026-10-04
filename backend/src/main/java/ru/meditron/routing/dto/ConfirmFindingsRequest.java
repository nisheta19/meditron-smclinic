package ru.meditron.routing.dto;

import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

public record ConfirmFindingsRequest(@NotEmpty List<@NotBlank String> findingIds, String doctor) {
}
