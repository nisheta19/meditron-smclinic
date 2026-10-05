package ru.meditron.routing.dto;

import java.util.List;

/** Карточка: шапка, «Находки» (по последнему протоколу), маршруты, «История болезни». */
public record PatientCardDto(
        PatientShortDto patient,
        ProtocolShortDto currentProtocol,
        List<FindingDto> currentFindings,
        List<Object> routes,
        History history,
        /** Баннер «Незавершённый клинический маршрут» (ТЗ маршрутов, 15.3); null — нет. */
        String unfinishedRouteBanner,
        List<ru.meditron.routing.route.dto.RouteDtos.RouteDto> clinicalRoutes) {

    public record History(
            List<ProtocolShortDto> protocols,
            List<FindingDto> findings,
            List<Object> routes,
            List<ru.meditron.routing.route.dto.RouteDtos.RouteDto> clinicalRoutes) {
    }
}
