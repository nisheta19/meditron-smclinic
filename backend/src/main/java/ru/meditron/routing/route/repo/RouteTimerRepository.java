package ru.meditron.routing.route.repo;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import ru.meditron.routing.route.domain.*;

public interface RouteTimerRepository extends JpaRepository<RouteTimer, UUID> {
    Optional<RouteTimer> findFirstByStatusAndDueAtLessThanEqualOrderByDueAtAscCreatedAtAsc(RouteTimer.Status status, Instant now);
    List<RouteTimer> findByRouteIdAndStatus(UUID routeId, RouteTimer.Status status);
    List<RouteTimer> findByEscalationIdAndStatus(UUID escalationId, RouteTimer.Status status);
    List<RouteTimer> findByPatientId(UUID patientId);
}
