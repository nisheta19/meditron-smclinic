package ru.meditron.routing.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.io.IOException;
import java.util.Base64;
import java.util.Locale;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.service.MlGateway;

@RestController
@RequestMapping("/api/integration")
@Tag(name = "MIS", description = "Бэкенд отправляет протоколы в ML и получает результат асинхронно")
public class MisController {
    private final MlGateway gateway;
    public MisController(MlGateway gateway) { this.gateway = gateway; }

    @PostMapping(value = "/protocols", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "Передать DOCX в ML: metadata (application/json) и file (DOCX)")
    public ResponseEntity<?> upload(@RequestPart("metadata") JsonNode metadata,
                                    @RequestPart(value = "file", required = false) MultipartFile file) throws IOException {
        if (!metadata.isObject()) throw new BadRequestException("INVALID_METADATA", "metadata должен быть JSON-объектом");
        ObjectNode event = metadata.deepCopy();
        event.remove("contentBase64");
        event.remove("fileName");
        if (file != null) {
            String name = file.getOriginalFilename();
            if (name == null || !name.toLowerCase(Locale.ROOT).endsWith(".docx") || file.isEmpty()) {
                throw new BadRequestException("INVALID_FILE", "Нужен непустой файл DOCX");
            }
            event.put("fileName", name.replace('\\', '/').substring(name.replace('\\', '/').lastIndexOf('/') + 1));
            event.put("contentBase64", Base64.getEncoder().encodeToString(file.getBytes()));
        }
        return gateway.submit(event);
    }

    @PostMapping(value = "/events", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Передать JSON МИС в ML, включая аннулирование без файла")
    public ResponseEntity<?> event(@RequestBody JsonNode event) { return gateway.submit(event); }

    @GetMapping("/events/status")
    @Operation(summary = "Статус обработки и доставки callback; успех доставки — delivery=delivered")
    public ResponseEntity<?> status(@RequestParam String eventId) { return gateway.status(eventId, false); }

    @PostMapping("/events/retry")
    @Operation(summary = "Повторить доставку результата после устранения ошибки бэкенда")
    public ResponseEntity<?> retry(@RequestParam String eventId) { return gateway.status(eventId, true); }
}
