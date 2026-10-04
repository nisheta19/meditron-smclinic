package ru.meditron.routing.dto;

import java.util.List;

/** Карточка: шапка, «Находки» (по последнему протоколу), маршруты, «История болезни». */
public record PatientCardDto(
        PatientShortDto patient,
        ProtocolShortDto currentProtocol,
        List<FindingDto> currentFindings,
        List<Object> routes,
        History history) {

    public record History(
            List<ProtocolShortDto> protocols,
            List<FindingDto> findings,
            List<Object> routes) {
    }
}
