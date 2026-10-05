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

/** Журнал: кто, что, когда и на каком основании (раздел 13). Записи только добавляются. */
@Entity
@org.hibernate.annotations.Immutable
@Table(name = "route_journal", indexes = {
        @Index(name = "ix_journal_patient", columnList = "patientId"),
        @Index(name = "ix_journal_at", columnList = "happened_at")})
@Getter
@Setter
@NoArgsConstructor
public class JournalEntry {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "happened_at", nullable = false)
    private Instant at = ModelTime.now();

    /** COORDINATOR, DOCTOR, SYSTEM, CRM, MIS или роль из раздела 2. */
    @Column(nullable = false)
    private String actor;

    private String actorName;

    @Column(nullable = false)
    private String action;

    /** Основание: правило словаря, таймер, событие МИС (eventId), решение человека. */
    @Column(columnDefinition = "text")
    private String basis;

    private UUID patientId;

    private UUID routeId;

    private UUID findingId;

    private UUID taskId;

    private UUID escalationId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> details = new LinkedHashMap<>();
}
