package ru.meditron.routing.dto;

import jakarta.validation.constraints.NotBlank;

/** Цитата-доказательство. start/end заполнены, только если у протокола есть полный текст. */
public record EvidenceDto(@NotBlank String text, Integer start, Integer end) {
}
