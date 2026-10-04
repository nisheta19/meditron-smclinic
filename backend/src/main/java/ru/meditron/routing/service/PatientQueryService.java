package ru.meditron.routing.service;

import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.meditron.routing.domain.*;
import ru.meditron.routing.dto.*;
import ru.meditron.routing.exception.NotFoundException;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.repository.FindingRepository;
import ru.meditron.routing.repository.PatientRepository;
import ru.meditron.routing.repository.ProtocolRepository;

/** Чтение для фронта: инбокс, карточка пациента, протокол. */
@Service
@Transactional(readOnly = true)
public class PatientQueryService {

    private final PatientRepository patients;
    private final ProtocolRepository protocols;
    private final FindingRepository findings;
    private final DtoMapper mapper;

    public PatientQueryService(PatientRepository patients, ProtocolRepository protocols,
                               FindingRepository findings, DtoMapper mapper) {
        this.patients = patients;
        this.protocols = protocols;
        this.findings = findings;
        this.mapper = mapper;
    }

    /** Данные одного пациента, из которых собираются и строка инбокса, и карточка. */
    private record Snapshot(Patient patient, List<Protocol> protocols, Protocol current, List<Finding> findings) {
    }

    private Snapshot snapshot(Patient p) {
        List<Protocol> ps = protocols.findByPatientIdOrderByReceivedAtDesc(p.getId());
        Protocol current = ps.stream().filter(x -> !x.isSuperseded()).findFirst().orElse(null);
        List<Finding> fs = findings.findByPatientIdOrderByCreatedAtDesc(p.getId());
        return new Snapshot(p, ps, current, fs);
    }

    private PatientShortDto shortDto(Snapshot s) {
        int pending = (int) s.findings().stream().filter(f -> f.getStatus() == FindingStatus.SUGGESTED).count();
        Protocol c = s.current();
        ReviewState state;
        if (s.protocols().stream().filter(x -> !x.isSuperseded()).anyMatch(x -> x.getStatus() == ProcessingStatus.FAILED
                || x.getStatus() == ProcessingStatus.DONE && (!x.isConclusionFound() || hasFlag(x, "NO_CONCLUSION")))) {
            state = ReviewState.ATTENTION;
        } else if (pending > 0) {
            state = ReviewState.PENDING;
        } else {
            state = ReviewState.OK;
        }
        Patient p = s.patient();
        return new PatientShortDto(
                p.getId().toString(),
                p.getExternalId(),
                p.getFullName(),
                p.name().lastName(),
                p.name().firstName(),
                p.name().middleName(),
                p.name().shortName(),
                p.getBirthDate(),
                mapper.age(p, null),
                p.getSex(),
                null,
                state,
                maxLevel(s),
                c == null ? null : c.getReceivedAt(),
                pending,
                0,
                c == null ? null : c.getStudyDate(),
                c == null ? null : c.getStudyType(),
                active(s).size(),
                active(s).stream().limit(TOP_FINDINGS).map(this::top).toList());
    }

    private static final int TOP_FINDINGS = 2;

    /**
     * Активные находки всех незаменённых протоколов и ручные подтверждённые находки,
     * самые срочные первыми: по уровню, затем по сроку.
     */
    private List<Finding> active(Snapshot s) {
        return s.findings().stream()
                .filter(f -> f.getStatus() == FindingStatus.SUGGESTED || f.getStatus() == FindingStatus.CONFIRMED)
                .filter(f -> f.getProtocol() == null || !f.getProtocol().isSuperseded()
                        && f.getProtocol().getStatus() == ProcessingStatus.DONE)
                .sorted(Comparator.comparing((Finding f) -> f.getLevel() == null ? 0 : f.getLevel().rank(),
                                Comparator.reverseOrder())
                        .thenComparing(Finding::getTargetDays, Comparator.nullsLast(Comparator.naturalOrder())))
                .toList();
    }

    private TopFindingDto top(Finding f) {
        return new TopFindingDto(f.getId().toString(), f.getCode(), f.getName(), f.getStatus(), f.getLevel(),
                f.getTargetSpecialty(), f.getTargetDays());
    }

    public PatientPageDto list(String search, ReviewState reviewState, StudyType studyType, FindingLevel maxLevel,
                               LocalDate dateFrom, LocalDate dateTo, int page, int size) {
        if (page < 0 || size < 1 || size > 200 || (dateFrom != null && dateTo != null && dateFrom.isAfter(dateTo))) {
            throw new BadRequestException("INVALID_FILTER", "page >= 0; size от 1 до 200; dateFrom <= dateTo");
        }
        List<PatientShortDto> all = new ArrayList<>();
        for (Patient p : patients.findAll()) {
            Snapshot s = snapshot(p);
            if (search != null && !search.isBlank()) {
                String q = search.toLowerCase();
                if (!p.getFullName().toLowerCase().contains(q) && !p.getExternalId().toLowerCase().contains(q)) {
                    continue;
                }
            }
            if (studyType != null && s.protocols().stream().noneMatch(x -> x.getStudyType() == studyType)) {
                continue;
            }
            LocalDate last = s.current() == null ? null : s.current().getStudyDate();
            if (dateFrom != null && (last == null || last.isBefore(dateFrom))) {
                continue;
            }
            if (dateTo != null && (last == null || last.isAfter(dateTo))) {
                continue;
            }
            PatientShortDto dto = shortDto(s);
            if (reviewState != null && dto.reviewState() != reviewState) {
                continue;
            }
            if (maxLevel != null && dto.maxLevel() != maxLevel) {
                continue;
            }
            all.add(dto);
        }
        // Экстренные — вверху инбокса, затем срочные; внутри уровня — новые сверху.
        all.sort(Comparator.comparing((PatientShortDto d) -> d.maxLevel() == null ? 0 : d.maxLevel().rank(),
                        Comparator.reverseOrder())
                .thenComparing(PatientShortDto::receivedAt,
                        Comparator.nullsLast(Comparator.<Instant>reverseOrder())));
        int from = (int) Math.min((long) page * size, all.size());
        int to = Math.min(from + size, all.size());
        return new PatientPageDto(all.subList(from, to), page, size, all.size());
    }

    public PatientCardDto card(String patientId) {
        Patient p = patients.findById(Ids.parse(patientId, "PATIENT"))
                .orElseThrow(() -> new NotFoundException("PATIENT_NOT_FOUND", "Пациент " + patientId + " не найден"));
        Snapshot s = snapshot(p);
        UUID currentId = s.current() == null ? null : s.current().getId();

        List<FindingDto> current = s.findings().stream()
                .filter(f -> f.getStatus() != FindingStatus.REMOVED)
                .filter(f -> f.getProtocol() == null || f.getProtocol().getId().equals(currentId))
                .map(mapper::finding)
                .toList();
        List<FindingDto> pastFindings = s.findings().stream()
                .filter(f -> f.getStatus() == FindingStatus.CONFIRMED || f.getStatus() == FindingStatus.SUGGESTED)
                .filter(f -> f.getProtocol() != null && !f.getProtocol().getId().equals(currentId))
                .map(mapper::finding)
                .toList();
        List<ProtocolShortDto> pastProtocols = s.protocols().stream()
                .filter(x -> !x.getId().equals(currentId))
                .map(x -> mapper.protocolShort(x, countFindings(s, x)))
                .toList();

        return new PatientCardDto(
                shortDto(s),
                s.current() == null ? null : mapper.protocolShort(s.current(), countFindings(s, s.current())),
                current,
                List.of(),
                new PatientCardDto.History(pastProtocols, pastFindings, List.of()));
    }

    public ProtocolDto protocol(String protocolId) {
        Protocol p = protocols.findById(Ids.parse(protocolId, "PROTOCOL"))
                .orElseThrow(() -> new NotFoundException("PROTOCOL_NOT_FOUND", "Протокол " + protocolId + " не найден"));
        List<Finding> fs = findings.findByProtocolId(p.getId());
        ErrorResponse error = p.getErrorCode() == null ? null : new ErrorResponse(p.getErrorCode(), p.getErrorMessage());
        List<Map<String, Object>> nt = p.getNotTriggered() == null ? List.of() : p.getNotTriggered();
        return new ProtocolDto(
                mapper.protocolShort(p, fs.size()),
                p.getPatient().getId().toString(),
                p.getText(),
                p.getModelVersion(),
                error,
                fs.stream().map(mapper::finding).toList(),
                nt);
    }

    /** Самый срочный уровень среди активных находок текущего протокола (предложенных и подтверждённых). */
    private FindingLevel maxLevel(Snapshot s) {
        FindingLevel max = null;
        for (Finding f : active(s)) {
            max = FindingLevel.max(max, f.getLevel());
        }
        return max;
    }

    private boolean hasFlag(Protocol p, String code) {
        return p.getFlags() != null && p.getFlags().stream().anyMatch(f -> code.equals(f.get("code")));
    }

    private int countFindings(Snapshot s, Protocol p) {
        return (int) s.findings().stream()
                .filter(f -> f.getProtocol() != null && f.getProtocol().getId().equals(p.getId()))
                .filter(f -> f.getStatus() != FindingStatus.REMOVED)
                .count();
    }
}
