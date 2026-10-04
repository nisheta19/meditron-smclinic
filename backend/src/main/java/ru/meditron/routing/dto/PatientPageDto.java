package ru.meditron.routing.dto;

import java.util.List;

public record PatientPageDto(List<PatientShortDto> items, int page, int size, long total) {
}
