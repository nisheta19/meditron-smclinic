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
 * Маршрут пациента к одному специалисту (раздел 4 ТЗ). Параллельные маршруты — разные записи.
 * Пациент и протокол хранятся идентификаторами: модуль маршрутов не меняет таблицы старого кода.
 */
@Entity
@Table(name = "route", indexes = {
        @Index(name = "ix_route_patient", columnList = "patientId"),
        @Index(name = "ix_route_open", columnList = "is_open")})
@Getter
@Setter
@NoArgsConstructor
public class Route {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private UUID patientId;

    /** Протокол, по которому маршрут создан или последний раз обновлён. */
    private UUID protocolId;

    @Column(nullable = false)
    private String specialty;

    @org.hibernate.annotations.ColumnDefault("false")
    private boolean specialtyAssignedByDoctor;

    /** Шаблон маршрута из словаря самой срочной находки (SURGICAL_STANDARD, OBSERVATION_FOLLOWUP…). */
    private String templateCode;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ChainType chainType;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private RouteStage stage;

    /** Ради какого визита ждём запись: консультация, повторная, результат, контроль, контрольное УЗИ. */
    @Enumerated(EnumType.STRING)
    private PendingVisit pendingVisit;

    @Enumerated(EnumType.STRING)
    private CloseReason closeReason;

    @Column(name = "is_open")
    private boolean open = true;

    /** «Должен посетить до». */
    private java.time.LocalDate hospitalizationDate;

    private String hospitalizationClinic;

    private Instant dueAt;

    /** Дата контроля для наблюдения / целевая дата контрольного визита. */
    private Instant controlAt;

    /** «Дата посещения» — последний состоявшийся визит. */
    private Instant visitAt;

    /** Тип исследования исходного протокола — для контрольного УЗИ при наблюдении. */
    private String studyType;

    /** Дата исследования, на котором выявлена находка (для баннера). */
    private java.time.LocalDate detectedOn;

    private int noShowCount;

    /** Норматив «дата госпитализации за 3 рабочих дня» нарушен (7.1). */
    private boolean slaOverdue;

    @Enumerated(EnumType.STRING)
    private Tactic tactic;

    private String tacticSubtype;

    private String tacticComment;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<String> findingIds = new ArrayList<>();

    /** История этапов: [{stage, at, basis}]. */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<Map<String, Object>> stageHistory = new ArrayList<>();

    /** Вехи для воронки (раздел 17.1): код вехи → время, ставится один раз. */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, String> milestones = new LinkedHashMap<>();

    private Instant createdAt = ModelTime.now();

    private Instant updatedAt = ModelTime.now();

    private Instant closedAt;

    public void milestone(String code) {
        milestones.putIfAbsent(code, ModelTime.now().toString());
    }

    public boolean hasMilestone(String code) {
        return milestones.containsKey(code);
    }
}
