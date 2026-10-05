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

/** Сообщение пациенту, переданное в CRM клиники (раздел 8). Канал выбирает CRM, не мы. */
@Entity
@Table(name = "route_notification", indexes = {
        @Index(name = "ix_rn_patient", columnList = "patientId"),
        @Index(name = "ix_rn_route", columnList = "routeId")})
@Getter
@Setter
@NoArgsConstructor
public class RouteNotification {

    public enum Delivery { SENT, DELIVERED, READ, FAILED }

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private UUID routeId;

    @Column(nullable = false)
    private UUID patientId;

    @Column(nullable = false)
    private String templateCode;

    @Column(columnDefinition = "text")
    private String fullText;

    @Column(columnDefinition = "text")
    private String shortText;

    private String preferredChannel;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, String> links = new LinkedHashMap<>();

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<String> buttons = new ArrayList<>();

    private boolean manual;

    private String sentBy;

    private Instant sentAt = ModelTime.now();

    @Enumerated(EnumType.STRING)
    private Delivery delivery = Delivery.SENT;

    private Instant deliveredAt;

    private Instant readAt;

    private Instant failedAt;

    /** История статусов от CRM: [{status, at}]. */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<Map<String, Object>> statusHistory = new ArrayList<>();
}
