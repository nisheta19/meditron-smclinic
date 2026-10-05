package ru.meditron.routing.route.repo;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import ru.meditron.routing.route.domain.*;

public interface EscalationRepository extends JpaRepository<Escalation, UUID> {
    List<Escalation> findByPatientIdOrderByStartedAtDesc(UUID patientId);
    List<Escalation> findByProtocolId(UUID protocolId);
    Optional<Escalation> findFirstByFindingIdAndStepNot(UUID findingId, Escalation.Step step);
    List<Escalation> findAllByOrderByStartedAtDesc();
}
