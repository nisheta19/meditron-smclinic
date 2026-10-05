package ru.meditron.routing.route.dto;

import jakarta.validation.constraints.NotBlank;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/** DTO модуля маршрутов (раздел 15 ТЗ). */
public final class RouteDtos {

    private RouteDtos() {
    }

    public record RouteDto(
            String id, String patientId, String protocolId, String specialty, String routeType, String chainType,
            String stage, String stageTitle, String pendingVisit, boolean open, String closeReason,
            Instant dueAt, Instant controlAt, Instant visitAt, Integer overdueDays, boolean slaOverdue,
            int noShowCount, String tactic, String tacticSubtype, String tacticComment,
            List<FindingRef> findings, List<Map<String, Object>> stageHistory, List<TaskDto> openTasks,
            AppointmentDto appointment, Instant createdAt, Instant closedAt,
            java.time.LocalDate hospitalizationDate, String hospitalizationClinic) {
    }

    public record FindingRef(String id, String code, String name, String status) {
    }

    public record AppointmentDto(String id, String purpose, Instant dateTime, String location, boolean online,
                                 String doctorName, String status) {
    }

    public record NotificationDto(
            String id, String routeId, String specialty, String templateCode, String templateTitle,
            String fullText, String shortText, Map<String, String> links, List<String> buttons, boolean manual,
            String sentBy, Instant sentAt, String delivery, Instant deliveredAt, Instant readAt, Instant failedAt,
            boolean bookedAfter, String patientId, String patientExternalId, String preferredChannel) {
    }

    public record TemplateDto(String code, String title, boolean manual) {
    }

    public record NotificationPreviewDto(String templateCode, String fullText, String shortText) {
    }

    public record ManualNotificationRequest(@NotBlank String templateCode, boolean confirm, String doctor) {
    }

    public record TaskDto(String id, String type, String role, String patientId, String routeId, String escalationId,
                          String text, Instant createdAt, Instant dueAt, boolean overdue, String status,
                          String doneBy, Instant doneAt, String comment) {
    }

    public record TaskDoneRequest(String doctor, String comment) {
    }

    public record EscalationDto(String id, String patientId, String protocolId, String findingId, String findingName,
                                String dutySpecialty, String step, String currentRole, Instant deadline,
                                boolean confirmTimedOut, Instant startedAt, Instant confirmedAt, Instant acceptedAt,
                                String acceptedBy, Instant contactedAt, Instant closedAt, String outcome,
                                String outcomeComment, String closeNote, String routeId,
                                List<Map<String, Object>> history) {
    }

    public record EscalationActionRequest(String role, String doctor, String outcome, String comment) {
    }

    public record JournalDto(String id, Instant at, String actor, String actorName, String action, String basis,
                             String patientId, String routeId, String findingId, String taskId, String escalationId,
                             Map<String, Object> details) {
    }

    public record SlotDto(String id, String specialty, String kind, Instant dateTime, String location, boolean online,
                          String doctorName) {
    }

    public record BookingRequest(@NotBlank String routeId, @NotBlank String slotId) {
    }

    /** Событие маршрута от МИС (раздел 10). */
    public record RouteEvent(
            @NotBlank String eventId, @NotBlank String type, Instant occurredAt, String patientExternalId,
            @NotBlank String routeId, String slotId, Instant dateTime, String location, Boolean online,
            String doctorName, String tactic, String subtype, Instant dueDate, Instant controlDate,
            String newSpecialty, String comment, String clinic, String date, String reason, String serviceCode,
            Boolean controlVisitBooked, Instant controlDateTime) {
    }

    /** Статус доставки или ответ пациента от CRM (разделы 8.2–8.3). */
    public record CrmCallback(@NotBlank String eventId, String messageId, String status, Instant at,
                              String routeId, String reply) {
    }

    public record ClockDto(Instant now, long offsetMinutes) {
    }

    public record AdvanceRequest(long minutes) {
    }

    public record ScenarioStartRequest(Integer stepDelaySeconds, Boolean manual) {
    }

    public record ScenarioRunDto(String runId, String scenario, String title, int step, int totalSteps,
                                 String lastStep, boolean finished, String error, List<String> log) {
    }
}
