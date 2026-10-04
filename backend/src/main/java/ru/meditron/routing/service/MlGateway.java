package ru.meditron.routing.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import ru.meditron.routing.dto.ErrorResponse;

/** File submission does not hold a DB transaction while waiting for ML. */
@Service
public class MlGateway {
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER).build();
    private final String baseUrl;
    private final ObjectMapper mapper;

    public MlGateway(@Value("${ml.service-url}") String baseUrl, ObjectMapper mapper) {
        URI uri = URI.create(baseUrl);
        if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) || uri.getHost() == null
                || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null) {
            throw new IllegalArgumentException("ML_SERVICE_URL must be an HTTP(S) service URL");
        }
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.mapper = mapper;
    }

    public ResponseEntity<?> submit(JsonNode event) {
        return exchange("POST", "/api/mis/events", event);
    }

    public ResponseEntity<?> status(String eventId, boolean retry) {
        String id = URLEncoder.encode(eventId, StandardCharsets.UTF_8).replace("+", "%20");
        return exchange(retry ? "POST" : "GET", "/api/mis/events/" + id + (retry ? "/retry" : ""), null);
    }

    private ResponseEntity<?> exchange(String method, String path, JsonNode event) {
        try {
            byte[] body = event == null ? new byte[0] : mapper.writeValueAsBytes(event);
            if (body.length > 29 * 1024 * 1024) {
                return ResponseEntity.status(413).body(new ErrorResponse("EVENT_TOO_LARGE", "Событие больше 29 MiB"));
            }
            var request = HttpRequest.newBuilder(URI.create(baseUrl + path)).timeout(Duration.ofSeconds(30))
                    .header("Content-Type", "application/json").header("Accept", "application/json")
                    .method(method, HttpRequest.BodyPublishers.ofByteArray(body)).build();
            var response = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() >= 300 && response.statusCode() < 400) {
                return unavailable();
            }
            JsonNode json = mapper.readTree(response.body());
            if (json == null) return unavailable();
            return ResponseEntity.status(response.statusCode()).contentType(MediaType.APPLICATION_JSON).body(json);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return unavailable();
        } catch (IOException | IllegalArgumentException e) {
            return unavailable();
        }
    }

    private ResponseEntity<ErrorResponse> unavailable() {
        return ResponseEntity.status(502).body(new ErrorResponse("ML_UNAVAILABLE",
                "ML недоступен или вернул некорректный ответ. Повторите тот же eventId и содержимое."));
    }
}
