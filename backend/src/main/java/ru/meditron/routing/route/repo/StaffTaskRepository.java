package ru.meditron.routing.route.repo;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import ru.meditron.routing.route.domain.*;

public interface StaffTaskRepository extends JpaRepository<StaffTask, UUID> {
    List<StaffTask> findByRouteIdAndStatus(UUID routeId, StaffTask.Status status);
    List<StaffTask> findByEscalationIdAndStatus(UUID escalationId, StaffTask.Status status);
    List<StaffTask> findByPatientIdOrderByCreatedAtDesc(UUID patientId);
    List<StaffTask> findAllByOrderByCreatedAtDesc();
    boolean existsByFindingIdAndType(UUID findingId, String type);
}
