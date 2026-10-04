package ru.meditron.routing.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import ru.meditron.routing.dto.MlResultRequest;
import ru.meditron.routing.service.MlIngestionService;

@RestController
@RequestMapping("/api/integration")
@Tag(name = "Integration", description = "Вход от ML (не для фронта)")
public class IntegrationController {

    private final MlIngestionService ingestion;

    public IntegrationController(MlIngestionService ingestion) {
        this.ingestion = ingestion;
    }

    @PostMapping("/ml/results")
    @Operation(summary = "Результат ML по одному протоколу. Повтор того же resultId — 202 без изменений")
    public ResponseEntity<Void> mlResult(@Valid @RequestBody MlResultRequest request) {
        ingestion.ingest(request);
        return ResponseEntity.accepted().build();
    }
}
