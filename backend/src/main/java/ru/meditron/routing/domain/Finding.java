package ru.meditron.routing.domain;

import ru.meditron.routing.time.ModelTime;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** Находка: предложена ML (SUGGESTED) или добавлена врачом (MANUAL). */
@Entity
@Table(name = "finding")
@Getter
@Setter
@NoArgsConstructor
public class Finding {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @ManyToOne(optional = false, fetch = FetchType.LAZY)
    private Patient patient;

    /** null для находок, добавленных врачом вручную. */
    @ManyToOne(fetch = FetchType.LAZY)
    private Protocol protocol;

    @Column(nullable = false)
    private String code;

    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private FindingStatus status;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private FindingSource source;

    @Column(columnDefinition = "text")
    private String evidenceText;

    private Integer evidenceStart;

    private Integer evidenceEnd;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> attributes = new HashMap<>();

    private Double confidence;

    /** Версия ML, извлёкшей находку. */
    private String modelVersion;

    /** Версия словаря, по которой выбраны специалист и срок. */
    private String ruleVersion;

    /** Какое правило словаря сработало, например GALLBLADDER_POLYP.rules[0]. */
    private String matchedRule;

    private String targetSpecialty;

    private Integer targetDays;

    private String routeTemplateCode;

    /** Уровень срочности по словарю: EMERGENCY / URGENT / PLANNED. */
    @Enumerated(EnumType.STRING)
    private FindingLevel level;

    /** = level == EMERGENCY. Колонка осталась из словаря v1 (NOT NULL), поэтому поле не удаляем. */
    private boolean urgent;

    /** Флаги находки: от ML (DISCREPANCY, INCOMPLETE...) и от бэкенда (MINOR, SYSTEM_UNKNOWN...). */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<Map<String, Object>> flags = new ArrayList<>();

    private String reviewedBy;

    private Instant reviewedAt;

    @Column(columnDefinition = "text")
    private String comment;

    @Column(nullable = false)
    private Instant createdAt = ModelTime.now();
}
