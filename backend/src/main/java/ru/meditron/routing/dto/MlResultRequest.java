package ru.meditron.routing.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import ru.meditron.routing.domain.ProcessingStatus;
import ru.meditron.routing.domain.Sex;
import ru.meditron.routing.domain.StudyType;

/** Сообщение от ML. Полное описание полей — в документе «Требования к ML-сервису». */
public record MlResultRequest(
        @NotBlank String resultId,
        @NotNull ProcessingStatus status,
        @NotBlank String modelVersion,
        String dictionaryVersion,
        @NotNull OffsetDateTime processedAt,
        @NotNull @Valid PatientPart patient,
        @NotNull @Valid ProtocolPart protocol,
        String text,
        String conclusion,
        Boolean conclusionFound,
        List<@NotNull @Valid MlFlag> flags,
        List<@NotNull @Valid MlFinding> findings,
        List<@NotNull @Valid MlNotTriggered> notTriggered,
        @Valid MlError error) {

    /**
     * Пациент из МИС. ФИО по частям (lastName, firstName, middleName — отчество необязательно);
     * fullName пока обязателен для совместимости с ML, при отсутствии частей бэкенд разбирает его сам.
     */
    public record PatientPart(
            @NotBlank String externalId,
            @NotBlank String fullName,
            String lastName,
            String firstName,
            String middleName,
            @NotNull LocalDate birthDate,
            @NotNull Sex sex) {
    }

    public record ProtocolPart(
            @NotBlank String externalId,
            @Min(1) int version,
            @NotNull StudyType studyType,
            @NotNull LocalDate studyDate) {
    }

    public record MlFinding(
            @NotBlank String code,
            @NotNull @Valid EvidenceDto evidence,
            Map<String, Object> attributes,
            Double confidence,
            List<@NotNull @Valid MlFlag> flags) {
    }

    /** Флаг качества протокола / находки (DISCREPANCY, INCOMPLETE, NO_CONCLUSION...). note — пояснение для врача. */
    public record MlFlag(
            @NotBlank String code,
            String note) {
    }

    public record MlNotTriggered(
            @NotBlank String code,
            @NotNull @Valid EvidenceDto evidence,
            @NotBlank String reason) {
    }

    public record MlError(@NotBlank String code, @NotBlank String message) {
    }
}
