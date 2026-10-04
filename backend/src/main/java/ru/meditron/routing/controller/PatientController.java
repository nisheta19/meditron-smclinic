package ru.meditron.routing.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.time.LocalDate;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import ru.meditron.routing.domain.FindingStatus;
import ru.meditron.routing.domain.FindingLevel;
import ru.meditron.routing.domain.ReviewState;
import ru.meditron.routing.domain.StudyType;
import ru.meditron.routing.dto.*;
import ru.meditron.routing.service.FindingService;
import ru.meditron.routing.service.PatientQueryService;

@RestController
@RequestMapping("/api/patients")
@Tag(name = "Patients", description = "Инбокс, карточка пациента, находки пациента")
public class PatientController {

    private final PatientQueryService query;
    private final FindingService findingService;

    public PatientController(PatientQueryService query, FindingService findingService) {
        this.query = query;
        this.findingService = findingService;
    }

    @GetMapping
    @Operation(summary = "Инбокс: «Новые» = reviewState=PENDING, ATTENTION — протокол не прочитан или без заключения")
    public PatientPageDto list(@RequestParam(required = false) String search,
                               @RequestParam(required = false) ReviewState reviewState,
                               @RequestParam(required = false) StudyType studyType,
                               @RequestParam(required = false) FindingLevel maxLevel,
                               @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateFrom,
                               @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateTo,
                               @RequestParam(defaultValue = "0") int page,
                               @RequestParam(defaultValue = "20") int size) {
        return query.list(search, reviewState, studyType, maxLevel, dateFrom, dateTo, page, size);
    }

    @GetMapping("/{patientId}")
    @Operation(summary = "Карточка пациента: находки по последнему протоколу, маршруты, история")
    public PatientCardDto card(@PathVariable String patientId) {
        return query.card(patientId);
    }

    @GetMapping("/{patientId}/findings")
    public List<FindingDto> findings(@PathVariable String patientId,
                                     @RequestParam(required = false) FindingStatus status) {
        return findingService.list(patientId, status);
    }

    @PostMapping("/{patientId}/findings")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Врач добавляет находку вручную (сразу CONFIRMED, source=MANUAL)")
    public FindingDto addFinding(@PathVariable String patientId, @Valid @RequestBody FindingCreateRequest request) {
        return findingService.create(patientId, request);
    }

    @PostMapping("/{patientId}/findings/confirm")
    @Operation(summary = "«Всё ок» — подтвердить пачку находок")
    public List<FindingDto> confirm(@PathVariable String patientId, @Valid @RequestBody ConfirmFindingsRequest request) {
        return findingService.confirm(patientId, request);
    }
}
