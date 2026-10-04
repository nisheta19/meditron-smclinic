package ru.meditron.routing.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.*;
import ru.meditron.routing.dto.ProtocolDto;
import ru.meditron.routing.service.PatientQueryService;

@RestController
@RequestMapping("/api/protocols")
@Tag(name = "Protocols")
public class ProtocolController {

    private final PatientQueryService query;

    public ProtocolController(PatientQueryService query) {
        this.query = query;
    }

    @GetMapping("/{protocolId}")
    @Operation(summary = "Протокол с находками и списком «почему не сработало»")
    public ProtocolDto protocol(@PathVariable String protocolId) {
        return query.protocol(protocolId);
    }
}
