package ru.meditron.routing.route.repo;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import ru.meditron.routing.route.domain.*;

public interface RouteNotificationRepository extends JpaRepository<RouteNotification, UUID> {
    interface PatientStats {
        UUID getPatientId();
        long getNotificationCount();
        Instant getLastNotifiedAt();
    }

    @org.springframework.data.jpa.repository.Query("""
            select n.patientId as patientId, count(n) as notificationCount, max(n.sentAt) as lastNotifiedAt
            from RouteNotification n where n.patientId in :patientIds and n.delivery <> :excluded
            group by n.patientId
            """)
    List<PatientStats> summarizePatients(@org.springframework.data.repository.query.Param("patientIds") Collection<UUID> patientIds,
                                        @org.springframework.data.repository.query.Param("excluded") RouteNotification.Delivery excluded);
    List<RouteNotification> findByRouteIdOrderBySentAtDesc(UUID routeId);
    List<RouteNotification> findByPatientIdOrderBySentAtDesc(UUID patientId);
    List<RouteNotification> findByPatientIdAndSentAtAfter(UUID patientId, Instant after);
    List<RouteNotification> findAllByOrderBySentAtDesc();
}
