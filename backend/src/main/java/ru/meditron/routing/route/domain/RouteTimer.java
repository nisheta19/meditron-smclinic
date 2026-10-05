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

/**
 * Отложенное действие по модельному времени: шаг цепочки, отложенное сообщение, таймер эскалации…
 * Обрабатывается при продвижении модельного времени и периодически в реальном времени (раздел 3).
 */
@Entity
@Table(name = "route_timer", indexes = @Index(name = "ix_timer_due", columnList = "status,dueAt"))
@Getter
@Setter
@NoArgsConstructor
public class RouteTimer {

    public enum Status { PENDING, DONE, CANCELLED }

    public enum Kind {
        CHAIN_STEP, DEFERRED_MESSAGE, NO_SHOW_MESSAGE, OBSERVATION_REMINDER, OBSERVATION_CONTROL_DATE,
        VISIT_DEADLINE, HOSPITALIZATION_TASK, HOSPITALIZATION_SLA, AMBULANCE_CALL,
        ESCALATION_CONFIRM, ESCALATION_ACCEPT, ESCALATION_CONTACT
    }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private Instant dueAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Kind kind;

    /** Группа для массовой отмены: chain, hospitalization, escalation… */
    private String groupName;

    private UUID routeId;

    private UUID escalationId;

    private UUID patientId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> payload = new LinkedHashMap<>();

    @Enumerated(EnumType.STRING)
    private Status status = Status.PENDING;

    private Instant createdAt = ModelTime.now();
}
