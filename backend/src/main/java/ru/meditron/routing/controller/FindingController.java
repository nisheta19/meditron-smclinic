package ru.meditron.routing.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import ru.meditron.routing.dto.FindingDto;
import ru.meditron.routing.dto.FindingUpdateRequest;
import ru.meditron.routing.service.FindingService;

@RestController
@RequestMapping("/api/findings")
@Tag(name = "Findings")
public class FindingController {

    private final FindingService findingService;

    public FindingController(FindingService findingService) {
        this.findingService = findingService;
    }

    @PatchMapping("/{findingId}")
    @Operation(summary = "Подтвердить / отклонить / поправить находку")
    public FindingDto update(@PathVariable String findingId, @RequestBody FindingUpdateRequest request) {
        return findingService.update(findingId, request);
    }

    @DeleteMapping("/{findingId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Operation(summary = "Удалить находку (мягко — статус REMOVED, остаётся в истории)")
    public void delete(@PathVariable String findingId, @RequestParam(required = false) String reason) {
        findingService.delete(findingId, reason);
    }
}
