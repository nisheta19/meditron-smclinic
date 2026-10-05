package ru.meditron.routing.dto;

import java.time.Instant;

/** List projection: route of the displayed finding and successful patient notifications. */
public record PatientTrackingDto(String routeId, String stage, String stageTitle, Integer progressPercent,
                                 Instant lastNotifiedAt, long notificationCount) {
}
