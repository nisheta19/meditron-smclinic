package ru.meditron.routing.route.repo;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import ru.meditron.routing.route.domain.*;

public interface JournalRepository extends JpaRepository<JournalEntry, UUID> {
    List<JournalEntry> findByPatientIdOrderByAtDesc(UUID patientId);
    List<JournalEntry> findAllByOrderByAtDesc();
}
