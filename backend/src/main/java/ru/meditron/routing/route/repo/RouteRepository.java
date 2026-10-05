package ru.meditron.routing.route.repo;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import ru.meditron.routing.route.domain.*;

public interface RouteRepository extends JpaRepository<Route, UUID> {
    List<Route> findByPatientIdOrderByCreatedAtDesc(UUID patientId);
    List<Route> findByPatientIdAndOpenTrue(UUID patientId);
    List<Route> findByOpenTrue();
    List<Route> findByCreatedAtBetween(Instant from, Instant to);
}
