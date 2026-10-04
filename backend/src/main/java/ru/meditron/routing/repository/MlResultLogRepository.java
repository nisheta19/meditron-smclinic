package ru.meditron.routing.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.meditron.routing.domain.MlResultLog;

public interface MlResultLogRepository extends JpaRepository<MlResultLog, String> {
}
