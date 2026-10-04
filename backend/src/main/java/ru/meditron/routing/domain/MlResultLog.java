package ru.meditron.routing.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/** Принятые результаты ML — защита от повторной доставки по resultId. */
@Entity
@Table(name = "ml_result_log")
@Getter
@Setter
@NoArgsConstructor
public class MlResultLog {

    @Id
    private String resultId;

    private UUID protocolId;

    @Column(length = 64)
    private String payloadHash;

    @Column(nullable = false)
    private Instant receivedAt = Instant.now();
}
