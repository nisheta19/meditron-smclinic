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

/** Задача персоналу (раздел 12). Роль — строковая метка, авторизации по ролям нет. */
@Entity
@Table(name = "staff_task", indexes = {
        @Index(name = "ix_task_status", columnList = "status"),
        @Index(name = "ix_task_patient", columnList = "patientId")})
@Getter
@Setter
@NoArgsConstructor
public class StaffTask {

    public enum Status { OPEN, DONE, CANCELLED }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private String type;

    @Column(nullable = false)
    private String role;

    private UUID patientId;

    private UUID routeId;

    private UUID escalationId;

    /** Для MANUAL_REVIEW: находка, по которой задача поставлена (защита от дублей). */
    private UUID findingId;

    @Column(columnDefinition = "text")
    private String text;

    private Instant createdAt = ModelTime.now();

    private Instant dueAt;

    @Enumerated(EnumType.STRING)
    private Status status = Status.OPEN;

    private String doneBy;

    private Instant doneAt;

    @Column(columnDefinition = "text")
    private String comment;
}
