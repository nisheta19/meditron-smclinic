package ru.meditron.routing.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/** Пациент. Создаётся и обновляется только из результатов ML (по externalId из МИС). */
@Entity
@Table(name = "patient")
@Getter
@Setter
@NoArgsConstructor
public class Patient {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    /** ID пациента в МИС. */
    @Column(nullable = false, unique = true)
    private String externalId;

    @Column(nullable = false)
    private String fullName;

    private String lastName;
    private String firstName;
    private String middleName;

    /** Old database rows still have only full_name. */
    public PersonName name() {
        return PersonName.resolve(fullName, lastName, firstName, middleName);
    }

    private LocalDate birthDate;

    @Enumerated(EnumType.STRING)
    private Sex sex;

    @Column(nullable = false)
    private Instant createdAt = Instant.now();
}
