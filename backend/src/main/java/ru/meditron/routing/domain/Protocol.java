package ru.meditron.routing.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** Протокол исследования. Одна версия протокола МИС = одна запись (дубли версий отсекает MlIngestionService). */
@Entity
@Table(name = "protocol", uniqueConstraints = @UniqueConstraint(name = "uk_protocol_external_version", columnNames = {"externalId", "version"}))
@Getter
@Setter
@NoArgsConstructor
public class Protocol {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @ManyToOne(optional = false, fetch = FetchType.LAZY)
    private Patient patient;

    /** ID протокола в МИС. */
    @Column(nullable = false)
    private String externalId;

    @Column(nullable = false)
    private int version;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ProcessingStatus status;

    @Enumerated(EnumType.STRING)
    private StudyType studyType;

    private LocalDate studyDate;

    @Column(columnDefinition = "text")
    private String conclusion;

    private boolean conclusionFound;

    /** Полный текст, если ML его прислал. */
    @Column(columnDefinition = "text")
    private String text;

    private String modelVersion;

    /** Версия словаря, с которой работал ML. */
    private String dictionaryVersion;

    private String errorCode;

    @Column(columnDefinition = "text")
    private String errorMessage;

    /** Почему кандидаты не стали находками: от ML (NEGATION, NORMAL, POST_SURGERY) и от бэкенда (BELOW_THRESHOLD, OUT_OF_SCOPE). */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<Map<String, Object>> notTriggered = new ArrayList<>();

    /** Флаги уровня протокола от ML (NO_CONCLUSION, PREP_VIOLATED, DISCREPANCY...). */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<Map<String, Object>> flags = new ArrayList<>();

    /** true — есть более новая версия этого протокола. */
    private boolean superseded;

    @Column(nullable = false)
    private Instant receivedAt = Instant.now();
}
