package ru.meditron.routing.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.meditron.routing.dictionary.DictionaryService;
import ru.meditron.routing.dictionary.RuleEngine;
import ru.meditron.routing.dictionary.RuleContext;
import ru.meditron.routing.domain.*;
import ru.meditron.routing.dto.*;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.exception.NotFoundException;
import ru.meditron.routing.repository.FindingRepository;
import ru.meditron.routing.repository.PatientRepository;
import ru.meditron.routing.repository.ProtocolRepository;

/** Действия врача с находками: подтвердить, отклонить, поправить, добавить, удалить. */
@Service
public class FindingService {

    private final FindingRepository findings;
    private final PatientRepository patients;
    private final ProtocolRepository protocols;
    private final DictionaryService dictionary;
    private final DtoMapper mapper;
    private final RuleEngine rules;
    private final RoutingAdjustments adjustments;
    private final MlResultValidator validator;

    public FindingService(FindingRepository findings, PatientRepository patients, ProtocolRepository protocols,
                          DictionaryService dictionary, DtoMapper mapper, RuleEngine rules,
                          RoutingAdjustments adjustments, MlResultValidator validator) {
        this.findings = findings;
        this.patients = patients;
        this.protocols = protocols;
        this.dictionary = dictionary;
        this.mapper = mapper;
        this.rules = rules;
        this.adjustments = adjustments;
        this.validator = validator;
    }

    @Transactional(readOnly = true)
    public List<FindingDto> list(String patientId, FindingStatus status) {
        UUID pid = patient(patientId).getId();
        List<Finding> fs = status == null
                ? findings.findByPatientIdOrderByCreatedAtDesc(pid)
                : findings.findByPatientIdAndStatusOrderByCreatedAtDesc(pid, status);
        return fs.stream().map(mapper::finding).toList();
    }

    @Transactional
    public FindingDto create(String patientId, FindingCreateRequest req) {
        Patient patient = patient(patientId);
        JsonNode entry = entry(req.code());

        Finding f = new Finding();
        f.setPatient(patient);
        if (req.protocolId() != null) {
            Protocol p = protocols.findById(Ids.parse(req.protocolId(), "PROTOCOL"))
                    .orElseThrow(() -> new NotFoundException("PROTOCOL_NOT_FOUND", "Протокол " + req.protocolId() + " не найден"));
            if (!p.getPatient().getId().equals(patient.getId())) {
                throw new BadRequestException("PROTOCOL_OF_OTHER_PATIENT", "Протокол принадлежит другому пациенту");
            }
            f.setProtocol(p);
            requireCurrentProtocol(f);
        }
        f.setStatus(FindingStatus.CONFIRMED);
        f.setSource(FindingSource.MANUAL);
        f.setAttributes(req.attributes() == null ? new LinkedHashMap<>() : new LinkedHashMap<>(req.attributes()));
        f.setComment(req.comment());
        f.setReviewedBy(req.doctor());
        f.setReviewedAt(Instant.now());
        applyDictionary(f, entry, "MANUAL");
        return mapper.finding(findings.save(f));
    }

    @Transactional
    public List<FindingDto> confirm(String patientId, ConfirmFindingsRequest req) {
        UUID pid = patient(patientId).getId();
        List<FindingDto> result = new ArrayList<>();
        for (String id : req.findingIds()) {
            Finding f = finding(id);
            if (!f.getPatient().getId().equals(pid)) {
                throw new BadRequestException("FINDING_OF_OTHER_PATIENT", "Находка " + id + " принадлежит другому пациенту");
            }
            if (f.getStatus() == FindingStatus.REMOVED) {
                throw new BadRequestException("FINDING_REMOVED", "Находка " + id + " удалена");
            }
            requireCurrentProtocol(f);
            f.setStatus(FindingStatus.CONFIRMED);
            f.setReviewedBy(req.doctor());
            f.setReviewedAt(Instant.now());
            result.add(mapper.finding(f));
        }
        return result;
    }

    @Transactional
    public FindingDto update(String findingId, FindingUpdateRequest req) {
        Finding f = finding(findingId);
        if (f.getStatus() == FindingStatus.REMOVED) {
            throw new BadRequestException("FINDING_REMOVED", "Находка удалена");
        }
        requireCurrentProtocol(f);
        if (req.status() != null) {
            if (req.status() != FindingStatus.CONFIRMED && req.status() != FindingStatus.REJECTED) {
                throw new BadRequestException("INVALID_STATUS", "Допустимы только CONFIRMED и REJECTED");
            }
            f.setStatus(req.status());
            f.setReviewedBy(req.doctor());
            f.setReviewedAt(Instant.now());
        }
        if (req.attributes() != null) {
            f.setAttributes(new LinkedHashMap<>(req.attributes()));
        }
        if (req.code() != null || req.attributes() != null) {
            applyDictionary(f, entry(req.code() == null ? f.getCode() : req.code()), "MANUAL_EDIT");
            f.setReviewedBy(req.doctor());
            f.setReviewedAt(Instant.now());
        }
        if (req.comment() != null) {
            f.setComment(req.comment());
        }
        return mapper.finding(f);
    }

    @Transactional
    public void delete(String findingId, String reason) {
        Finding f = finding(findingId);
        f.setStatus(FindingStatus.REMOVED);
        f.setComment(reason);
        f.setReviewedAt(Instant.now());
    }

    /** Re-evaluate route when a doctor changes code or attributes. */
    private void applyDictionary(Finding f, JsonNode entry, String matchedRule) {
        if (!dictionary.isActive(entry)) throw new BadRequestException("INACTIVE_FINDING_CODE", "Код неактивен");
        validator.attributes(entry, f.getAttributes());
        if (f.getProtocol() != null) {
            boolean applicable = false;
            for (JsonNode kind : entry.path("studyTypes")) {
                if (kind.asText().equals(f.getProtocol().getStudyType().name())) applicable = true;
            }
            if (!applicable) throw new BadRequestException("WRONG_STUDY_TYPE", "Код не относится к типу исследования");
        }
        Integer age = mapper.age(f.getPatient(), f.getProtocol() == null ? null : f.getProtocol().getStudyDate());
        var decision = rules.evaluate(entry, f.getAttributes(), new RuleContext(age, f.getPatient().getSex(),
                f.getProtocol() == null ? null : f.getProtocol().getStudyType()));
        f.setCode(entry.path("code").asText());
        f.setName(entry.path("name").asText());
        f.setTargetSpecialty(decision.targetSpecialty());
        f.setTargetDays(decision.targetDays());
        f.setRouteTemplateCode(decision.routeTemplateCode());
        f.setLevel(decision.level());
        f.setUrgent(f.getLevel() == FindingLevel.EMERGENCY);
        f.setRuleVersion(dictionary.version());
        f.setMatchedRule(matchedRule + ": " + decision.matchedRule());
        if (f.getFlags() != null) f.getFlags().removeIf(flag -> "BACKEND".equals(flag.get("setBy")));
        adjustments.addSystemFlags(f);
        if (decision.triggered()) adjustments.applyMinor(f, age);
    }

    private void requireCurrentProtocol(Finding finding) {
        Protocol p = finding.getProtocol();
        if (p != null && (p.isSuperseded() || p.getStatus() != ProcessingStatus.DONE)) {
            throw new BadRequestException("PROTOCOL_INACTIVE", "Протокол заменён, аннулирован или не обработан");
        }
    }

    private JsonNode entry(String code) {
        return dictionary.find(code).orElseThrow(() ->
                new BadRequestException("UNKNOWN_FINDING_CODE", "Код " + code + " отсутствует в словаре"));
    }

    private Patient patient(String id) {
        return patients.findById(Ids.parse(id, "PATIENT"))
                .orElseThrow(() -> new NotFoundException("PATIENT_NOT_FOUND", "Пациент " + id + " не найден"));
    }

    private Finding finding(String id) {
        return findings.findById(Ids.parse(id, "FINDING"))
                .orElseThrow(() -> new NotFoundException("FINDING_NOT_FOUND", "Находка " + id + " не найдена"));
    }
}
