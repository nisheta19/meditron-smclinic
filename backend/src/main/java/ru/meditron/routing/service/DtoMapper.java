package ru.meditron.routing.service;

import java.time.LocalDate;
import java.time.Period;
import java.util.List;
import org.springframework.stereotype.Component;
import ru.meditron.routing.domain.Finding;
import ru.meditron.routing.domain.Patient;
import ru.meditron.routing.domain.Protocol;
import ru.meditron.routing.dto.EvidenceDto;
import ru.meditron.routing.dto.FindingDto;
import ru.meditron.routing.dto.ProtocolShortDto;

@Component
public class DtoMapper {

    public FindingDto finding(Finding f) {
        EvidenceDto evidence = f.getEvidenceText() == null ? null
                : new EvidenceDto(f.getEvidenceText(), f.getEvidenceStart(), f.getEvidenceEnd());
        return new FindingDto(
                f.getId().toString(),
                f.getPatient().getId().toString(),
                f.getProtocol() == null ? null : f.getProtocol().getId().toString(),
                f.getCode(),
                f.getName(),
                f.getStatus(),
                f.getSource(),
                evidence,
                f.getAttributes(),
                f.getConfidence(),
                f.getModelVersion(),
                f.getRuleVersion(),
                f.getMatchedRule(),
                f.getTargetSpecialty(),
                f.getTargetDays(),
                f.getLevel(),
                f.isUrgent(),
                f.getFlags() == null ? List.of() : f.getFlags(),
                null,
                f.getReviewedBy(),
                f.getReviewedAt(),
                f.getComment());
    }

    public ProtocolShortDto protocolShort(Protocol p, int findingsCount) {
        return new ProtocolShortDto(
                p.getId().toString(),
                p.getExternalId(),
                p.getVersion(),
                p.getStatus(),
                p.getStudyType(),
                p.getStudyDate(),
                p.getConclusion(),
                p.isConclusionFound(),
                findingsCount,
                p.getReceivedAt(),
                p.getFlags() == null ? List.of() : p.getFlags());
    }

    public Integer age(Patient p, LocalDate onDate) {
        if (p.getBirthDate() == null) {
            return null;
        }
        LocalDate date = onDate != null ? onDate : LocalDate.now();
        return Period.between(p.getBirthDate(), date).getYears();
    }
}
