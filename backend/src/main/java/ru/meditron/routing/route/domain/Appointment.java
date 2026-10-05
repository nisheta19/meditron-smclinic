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

/** Запись на приём или контрольное УЗИ (из заглушки расписания или события МИС BOOKED). */
@Entity
@Table(name = "route_appointment", indexes = @Index(name = "ix_appt_route", columnList = "routeId"))
@Getter
@Setter
@NoArgsConstructor
public class Appointment {

    public enum Status { BOOKED, CANCELLED, NO_SHOW, COMPLETED }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private UUID routeId;

    private UUID patientId;

    @Enumerated(EnumType.STRING)
    private PendingVisit purpose;

    private Instant dateTime;

    private String location;

    private boolean online;

    private String doctorName;

    @Enumerated(EnumType.STRING)
    private Status status = Status.BOOKED;

    private Instant createdAt = ModelTime.now();
}
