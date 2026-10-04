package ru.meditron.routing.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.core.type.TypeReference;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jdbc.core.JdbcTemplate;
import ru.meditron.routing.dictionary.DictionaryService;
import ru.meditron.routing.dictionary.RuleContext;
import ru.meditron.routing.dictionary.RuleDecision;
import ru.meditron.routing.dictionary.RuleEngine;
import ru.meditron.routing.domain.*;
import ru.meditron.routing.dto.EvidenceDto;
import ru.meditron.routing.dto.MlResultRequest;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.exception.ConflictException;
import ru.meditron.routing.repository.FindingRepository;
import ru.meditron.routing.repository.MlResultLogRepository;
import ru.meditron.routing.repository.PatientRepository;
import ru.meditron.routing.repository.ProtocolRepository;

/**
 * Приём результата ML: пациент и протокол создаются / обновляются по externalId,
 * находки проходят через правила словаря и сохраняются как SUGGESTED (ждут врача).
 */
@Service
public class MlIngestionService {

    private static final Logger log = LoggerFactory.getLogger(MlIngestionService.class);

    private final PatientRepository patients;
    private final ProtocolRepository protocols;
    private final FindingRepository findings;
    private final MlResultLogRepository resultLog;
    private final DictionaryService dictionary;
    private final RuleEngine ruleEngine;
    private final DtoMapper mapper;
    private final RoutingAdjustments adjustments;
    private final JdbcTemplate jdbc;
    private final MlResultValidator validator;
    private final ObjectMapper json;

    public MlIngestionService(PatientRepository patients, ProtocolRepository protocols, FindingRepository findings,
                              MlResultLogRepository resultLog, DictionaryService dictionary, RuleEngine ruleEngine,
                              DtoMapper mapper, RoutingAdjustments adjustments, JdbcTemplate jdbc,
                              MlResultValidator validator, ObjectMapper json) {
        this.patients = patients;
        this.protocols = protocols;
        this.findings = findings;
        this.resultLog = resultLog;
        this.dictionary = dictionary;
        this.ruleEngine = ruleEngine;
        this.mapper = mapper;
        this.adjustments = adjustments;
        this.jdbc = jdbc;
        this.validator = validator;
        this.json = json.copy().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    }

    @Transactional
    public void ingest(MlResultRequest r) {
        // Transaction-scoped PostgreSQL lock also protects concurrent first insert/upsert.
        // Ingestion is intentionally serialized at this hackathon scale across backend instances.
        jdbc.execute("SELECT pg_advisory_xact_lock(761904210)");
        String hash = fingerprint(r);
        MlResultLog previous = resultLog.findById(r.resultId()).orElse(null);
        if (previous != null) {
            if (!hash.equals(previous.getPayloadHash())) {
                throw new ConflictException("RESULT_ID_CONFLICT", "resultId уже использован для другого содержимого");
            }
            log.info("Результат {} уже принят — повтор игнорируется", r.resultId());
            return;
        }

        validator.validate(r);

        Protocol latest = protocols.findFirstByExternalIdOrderByVersionDesc(r.protocol().externalId()).orElse(null);
        if (latest != null && !latest.getPatient().getExternalId().equals(r.patient().externalId())) {
            throw new ConflictException("PROTOCOL_OF_OTHER_PATIENT", "Протокол уже связан с другим пациентом");
        }
        boolean stale = latest != null && (latest.getVersion() > r.protocol().version()
                || latest.getVersion() == r.protocol().version() && r.status() != ProcessingStatus.ANNULLED);
        if (stale) {
            saveReceipt(r, latest, hash);
            return; // A late callback must not overwrite patient metadata or annul a newer version.
        }

        Patient patient = upsertPatient(r.patient());
        Protocol saved = switch (r.status()) {
            case ANNULLED -> annul(r, patient);
            case DONE, FAILED -> acceptVersion(r, patient);
        };

        saveReceipt(r, saved, hash);
    }

    private void saveReceipt(MlResultRequest r, Protocol saved, String hash) {
        MlResultLog entry = new MlResultLog();
        entry.setResultId(r.resultId());
        entry.setProtocolId(saved == null ? null : saved.getId());
        entry.setPayloadHash(hash);
        resultLog.save(entry);
    }

    private String fingerprint(MlResultRequest r) {
        try {
            Map<String, Object> value = json.convertValue(r, new TypeReference<Map<String, Object>>() {});
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(json.writeValueAsBytes(value)));
        } catch (Exception e) {
            throw new IllegalStateException("Cannot fingerprint validated result", e);
        }
    }

    private Patient upsertPatient(MlResultRequest.PatientPart p) {
        Patient patient = patients.findByExternalId(p.externalId()).orElseGet(Patient::new);
        PersonName name = PersonName.resolve(p.fullName(), p.lastName(), p.firstName(), p.middleName());
        patient.setExternalId(p.externalId());
        patient.setLastName(name.lastName());
        patient.setFirstName(name.firstName());
        patient.setMiddleName(name.middleName());
        patient.setFullName(name.fullName());
        patient.setBirthDate(p.birthDate());
        patient.setSex(p.sex());
        return patients.save(patient);
    }

    /** Аннулирование: все версии протокола закрываются, их находки снимаются. */
    private Protocol annul(MlResultRequest r, Patient patient) {
        List<Protocol> versions = protocols.findByExternalIdOrderByVersionDesc(r.protocol().externalId());
        if (versions.isEmpty()) {
            Protocol p = newProtocol(r, patient);
            p.setStatus(ProcessingStatus.ANNULLED);
            return protocols.save(p);
        }
        for (Protocol p : versions) {
            p.setStatus(ProcessingStatus.ANNULLED);
            p.setSuperseded(p.getVersion() != r.protocol().version());
            removeActiveFindings(p, "PROTOCOL_ANNULLED");
        }
        if (r.protocol().version() > versions.get(0).getVersion()) {
            Protocol tombstone = newProtocol(r, patient);
            tombstone.setStatus(ProcessingStatus.ANNULLED);
            return protocols.save(tombstone);
        }
        return versions.get(0);
    }

    /** Новый протокол или новая версия исправленного. Старые и повторные версии не создают дублей. */
    private Protocol acceptVersion(MlResultRequest r, Patient patient) {
        Protocol latest = protocols.findFirstByExternalIdOrderByVersionDesc(r.protocol().externalId()).orElse(null);
        if (latest != null && latest.getVersion() >= r.protocol().version()) {
            log.info("Протокол {} v{} уже есть (v{}) — результат не применяется",
                    r.protocol().externalId(), r.protocol().version(), latest.getVersion());
            return latest;
        }
        if (latest != null) {
            latest.setSuperseded(true);
            removeActiveFindings(latest, "PROTOCOL_CORRECTED: заменён версией " + r.protocol().version());
        }

        Protocol p = newProtocol(r, patient);
        p.setStatus(r.status());
        p.setText(r.text());
        p.setConclusion(r.conclusion());
        p.setConclusionFound(Boolean.TRUE.equals(r.conclusionFound()));
        p.setDictionaryVersion(r.dictionaryVersion());
        p.setFlags(flags(r.flags(), "ML"));
        if (r.status() == ProcessingStatus.DONE && !p.isConclusionFound()
                && p.getFlags().stream().noneMatch(f -> "NO_CONCLUSION".equals(f.get("code")))) {
            Map<String, Object> noConclusion = flag("NO_CONCLUSION", "Раздел «Заключение» не найден", "BACKEND");
            p.getFlags().add(noConclusion);
        }
        if (r.status() == ProcessingStatus.FAILED && r.error() != null) {
            p.setErrorCode(r.error().code());
            p.setErrorMessage(r.error().message());
        }
        p = protocols.save(p);

        if (r.status() == ProcessingStatus.DONE) {
            applyFindings(r, patient, p);
        }
        return p;
    }

    private void applyFindings(MlResultRequest r, Patient patient, Protocol protocol) {
        List<Map<String, Object>> notTriggered = new ArrayList<>();
        if (r.notTriggered() != null) {
            for (MlResultRequest.MlNotTriggered nt : r.notTriggered()) {
                notTriggered.add(notTriggeredEntry(nt.code(), nt.evidence(), nt.reason(), "ML", null));
            }
        }
        List<Finding> created = new ArrayList<>();
        if (r.findings() != null) {
            Integer age = mapper.age(patient, r.protocol().studyDate());
            RuleContext context = new RuleContext(age, patient.getSex(), r.protocol().studyType());
            for (MlResultRequest.MlFinding mf : r.findings()) {
                JsonNode entry = dictionary.find(mf.code()).orElseThrow();
                Map<String, Object> attrs = mf.attributes() == null ? new LinkedHashMap<>() : new LinkedHashMap<>(mf.attributes());

                if (!dictionary.isActive(entry)) {
                    notTriggered.add(notTriggeredEntry(mf.code(), mf.evidence(), "OUT_OF_SCOPE", "BACKEND", null));
                    continue;
                }
                RuleDecision d = ruleEngine.evaluate(entry, attrs, context);
                if (!d.triggered()) {
                    Map<String, Object> nt = notTriggeredEntry(mf.code(), mf.evidence(), d.reason(), "BACKEND", d.matchedRule());
                    nt.put("attributes", attrs);
                    notTriggered.add(nt);
                    continue;
                }

                Finding f = new Finding();
                f.setPatient(patient);
                f.setProtocol(protocol);
                f.setCode(mf.code());
                f.setName(entry.path("name").asText());
                f.setStatus(FindingStatus.SUGGESTED);
                f.setSource(FindingSource.ML);
                f.setEvidenceText(mf.evidence().text());
                f.setEvidenceStart(mf.evidence().start());
                f.setEvidenceEnd(mf.evidence().end());
                f.setAttributes(attrs);
                f.setConfidence(mf.confidence());
                f.setModelVersion(r.modelVersion());
                f.setRuleVersion(dictionary.version());
                f.setMatchedRule(d.matchedRule());
                f.setTargetSpecialty(d.targetSpecialty());
                f.setTargetDays(d.targetDays());
                f.setRouteTemplateCode(d.routeTemplateCode());
                f.setLevel(d.level());
                f.setUrgent(d.urgent());
                f.setFlags(flags(mf.flags(), "ML"));
                adjustments.addSystemFlags(f);
                adjustments.applyMinor(f, age);
                created.add(f);
            }
        }
        adjustments.mergeGynecology(created);
        findings.saveAll(created);
        protocol.setNotTriggered(notTriggered);
    }

    /** Флаги от ML в хранимый вид; неизвестный словарю код сохраняется, но с предупреждением в лог. */
    private List<Map<String, Object>> flags(List<MlResultRequest.MlFlag> source, String setBy) {
        List<Map<String, Object>> result = new ArrayList<>();
        if (source == null) {
            return result;
        }
        for (MlResultRequest.MlFlag mf : source) {
            if (mf == null || mf.code() == null) {
                continue;
            }
            if (dictionary.flag(mf.code()).isEmpty()) {
                log.warn("Флаг {} отсутствует в словаре {} — сохранён как есть", mf.code(), dictionary.version());
            }
            result.add(flag(mf.code(), mf.note(), setBy));
        }
        return result;
    }

    private Map<String, Object> flag(String code, String note, String setBy) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("code", code);
        dictionary.flag(code).ifPresent(d -> m.put("name", d.path("name").asText()));
        if (note != null) {
            m.put("note", note);
        }
        m.put("setBy", setBy);
        return m;
    }

    private Map<String, Object> notTriggeredEntry(String code, EvidenceDto ev, String reason, String source, String rule) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("code", code);
        dictionary.find(code).ifPresent(e -> m.put("name", e.path("name").asText()));
        Map<String, Object> evidence = new LinkedHashMap<>();
        evidence.put("text", ev.text());
        evidence.put("start", ev.start());
        evidence.put("end", ev.end());
        m.put("evidence", evidence);
        m.put("reason", reason);
        m.put("source", source);
        if (rule != null) {
            m.put("matchedRule", rule);
        }
        return m;
    }

    private void removeActiveFindings(Protocol p, String reason) {
        for (Finding f : findings.findByProtocolId(p.getId())) {
            if (f.getStatus() == FindingStatus.SUGGESTED || f.getStatus() == FindingStatus.CONFIRMED) {
                f.setStatus(FindingStatus.REMOVED);
                f.setComment(reason);
                f.setReviewedAt(Instant.now());
                f.setReviewedBy("SYSTEM");
            }
        }
    }

    private Protocol newProtocol(MlResultRequest r, Patient patient) {
        Protocol p = new Protocol();
        p.setPatient(patient);
        p.setExternalId(r.protocol().externalId());
        p.setVersion(r.protocol().version());
        p.setStudyType(r.protocol().studyType());
        p.setStudyDate(r.protocol().studyDate());
        p.setModelVersion(r.modelVersion());
        return p;
    }
}
