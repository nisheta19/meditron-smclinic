package ru.meditron.routing.repository;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import ru.meditron.routing.domain.Finding;
import ru.meditron.routing.domain.FindingStatus;

public interface FindingRepository extends JpaRepository<Finding, UUID> {

    List<Finding> findByPatientIdOrderByCreatedAtDesc(UUID patientId);

    List<Finding> findByPatientIdAndStatusOrderByCreatedAtDesc(UUID patientId, FindingStatus status);

    List<Finding> findByProtocolId(UUID protocolId);
}
