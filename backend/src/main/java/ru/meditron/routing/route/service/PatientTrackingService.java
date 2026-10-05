package ru.meditron.routing.route.service;

import java.time.Instant;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.meditron.routing.dto.PatientTrackingDto;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.*;
import ru.meditron.routing.route.repo.RouteNotificationRepository;
import ru.meditron.routing.route.repo.RouteRepository;

/** Two batch queries, without loading full cards, message bodies, appointments or tasks. */
@Service
@Transactional(readOnly = true)
public class PatientTrackingService {
    private final RouteRepository routes;
    private final RouteNotificationRepository notifications;
    private final RouteConfig config;

    public PatientTrackingService(RouteRepository routes, RouteNotificationRepository notifications, RouteConfig config) {
        this.routes = routes;
        this.notifications = notifications;
        this.config = config;
    }

    public record Messages(long count, Instant latest) {}
    public record Batch(Map<UUID, List<Route>> routes, Map<UUID, Messages> messages) {
        public static Batch empty() { return new Batch(Map.of(), Map.of()); }
        public int activeCount(UUID patientId) {
            return (int) routes.getOrDefault(patientId, List.of()).stream().filter(Route::isOpen).count();
        }
    }

    public Batch load(Collection<UUID> patientIds) {
        if (patientIds.isEmpty()) return Batch.empty();
        var grouped = routes.findByPatientIdIn(patientIds).stream().collect(Collectors.groupingBy(Route::getPatientId));
        Map<UUID, Messages> messages = new HashMap<>();
        for (var s : notifications.summarizePatients(patientIds, RouteNotification.Delivery.FAILED))
            messages.put(s.getPatientId(), new Messages(s.getNotificationCount(), s.getLastNotifiedAt()));
        return new Batch(grouped, messages);
    }

    public PatientTrackingDto summarize(Batch batch, UUID patientId, String findingId) {
        // The stage must describe the finding displayed in this row, never an unrelated route.
        Route route = findingId == null ? null : batch.routes().getOrDefault(patientId, List.of()).stream()
                .filter(r -> r.getFindingIds().contains(findingId))
                .sorted(Comparator.comparing((Route r) -> !r.isOpen())
                        .thenComparing(Route::getCreatedAt, Comparator.reverseOrder()).thenComparing(Route::getId))
                .findFirst().orElse(null);
        Messages messages = batch.messages().getOrDefault(patientId, new Messages(0, null));
        return new PatientTrackingDto(route == null ? null : route.getId().toString(),
                route == null ? null : route.getStage().name(), route == null ? null : RouteQueryService.stageTitle(route),
                route == null ? null : progress(route), messages.latest(), messages.count());
    }

    /** Share of recorded workflow checkpoints, not elapsed time or medical recovery. */
    public Integer progress(Route route) {
        if (route.getStage() == RouteStage.COMPLETED || route.getStage() == RouteStage.CLOSED
                && route.getCloseReason() == CloseReason.SURGERY_NOT_INDICATED) return 100;
        String path = route.getChainType() == ChainType.OBSERVATION || route.getTactic() == Tactic.OBSERVATION
                || route.hasMilestone("CONTROL_ULTRASOUND") ? "observation" :
                "PROCEDURE".equals(route.getTacticSubtype()) ? "procedure" :
                "SURGICAL_STANDARD".equals(route.getTemplateCode()) || route.getTactic() == Tactic.SURGERY_INDICATED
                        || route.hasMilestone("HOSPITALIZED") ? "surgical" : "consultation";
        var checkpoints = config.at("/listProgress/" + path);
        if (!checkpoints.isArray() || checkpoints.isEmpty()) return null;
        var reached = new HashSet<>(route.getMilestones().keySet());
        route.getStageHistory().forEach(h -> { if (h.get("stage") instanceof String s) reached.add(s); });
        reached.add(route.getStage().name());
        int count = 0;
        for (var checkpoint : checkpoints) if (reached.contains(checkpoint.asText())) count++;
        return Math.min(99, Math.round(count * 100f / checkpoints.size()));
    }
}
