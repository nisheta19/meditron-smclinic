package ru.meditron.routing.route.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import ru.meditron.routing.time.ModelTime;

/** Идемпотентность событий МИС и CRM: повтор того же eventId не меняет состояние (раздел 10). */
@Entity
@Table(name = "route_processed_event")
@Getter
@Setter
@NoArgsConstructor
public class ProcessedEvent {

    @Id
    private String eventId;

    private String payloadHash;

    private String source;

    private String type;

    private Instant processedAt = ModelTime.now();
}
