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

/** Экстренная эскалация — лестница (раздел 9). Пациенту система не пишет. */
@Entity
@Table(name = "escalation", indexes = @Index(name = "ix_esc_patient", columnList = "patientId"))
@Getter
@Setter
@NoArgsConstructor
public class Escalation {

    public enum Step { AWAITING_CONFIRMATION, AWAITING_ACCEPT, AWAITING_CONTACT, AWAITING_OUTCOME, CLOSED }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private UUID patientId;

    private UUID protocolId;

    @Column(nullable = false)
    private UUID findingId;

    private String findingName;

    /** Дежурный по профилю из словаря: «Дежурный хирург / флеболог». */
    private String dutySpecialty;

    @Enumerated(EnumType.STRING)
    private Step step = Step.AWAITING_CONFIRMATION;

    /** Индекс текущего уровня лестницы «Принял в работу» (0 — дежурный врач). */
    private int ladderLevel;

    private boolean confirmTimedOut;

    private Instant startedAt = ModelTime.now();

    private Instant confirmedAt;

    private String confirmedBy;

    private Instant acceptedAt;

    private String acceptedBy;

    private String acceptedRole;

    private Instant contactedAt;

    private String contactedBy;

    private Instant closedAt;

    private String outcome;

    @Column(columnDefinition = "text")
    private String outcomeComment;

    /** Причина закрытия без исхода: не подтверждено координатором, протокол аннулирован или исправлен. */
    private String closeNote;

    /** Маршрут, созданный после исхода (госпитализация, скорая, приедет сегодня). */
    private UUID routeId;

    /** Шаги лестницы для карточки: [{step, at, by, role}]. */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<Map<String, Object>> history = new ArrayList<>();
}
