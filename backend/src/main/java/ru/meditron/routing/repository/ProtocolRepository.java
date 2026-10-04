package ru.meditron.routing.repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import ru.meditron.routing.domain.Protocol;

public interface ProtocolRepository extends JpaRepository<Protocol, UUID> {

    List<Protocol> findByPatientIdOrderByReceivedAtDesc(UUID patientId);

    List<Protocol> findByExternalIdOrderByVersionDesc(String externalId);

    Optional<Protocol> findFirstByExternalIdOrderByVersionDesc(String externalId);
}
