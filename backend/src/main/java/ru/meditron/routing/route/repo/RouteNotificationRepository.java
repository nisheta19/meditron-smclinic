package ru.meditron.routing.route.repo;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import ru.meditron.routing.route.domain.*;

public interface RouteNotificationRepository extends JpaRepository<RouteNotification, UUID> {
    List<RouteNotification> findByRouteIdOrderBySentAtDesc(UUID routeId);
    List<RouteNotification> findByPatientIdOrderBySentAtDesc(UUID patientId);
    List<RouteNotification> findByPatientIdAndSentAtAfter(UUID patientId, Instant after);
    List<RouteNotification> findAllByOrderBySentAtDesc();
}
