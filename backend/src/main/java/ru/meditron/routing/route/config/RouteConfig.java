package ru.meditron.routing.route.config;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import java.io.IOException;
import java.io.InputStream;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

/**
 * route-config.yaml — все сроки, тексты, таймеры, лестница эскалации, локации и врачи (раздел 16 ТЗ).
 * Изменения применяются перезапуском сервера (перезагрузка «на лету» по ТЗ не нужна).
 */
@Component
public class RouteConfig {

    private static final Logger log = LoggerFactory.getLogger(RouteConfig.class);

    private final JsonNode root;

    @org.springframework.beans.factory.annotation.Autowired
    public RouteConfig(@Value("${routes.config:classpath:routing/route-config.yaml}") Resource resource) throws IOException {
        try (InputStream in = resource.getInputStream()) {
            this.root = new ObjectMapper(new YAMLFactory()).readTree(in);
        }
        log.info("Настройки маршрутов {} загружены", root.path("version").asText("?"));
    }

    /** Для тестов: конфигурация из готового дерева. */
    public RouteConfig(JsonNode root) {
        this.root = root;
    }

    public JsonNode root() {
        return root;
    }

    public JsonNode at(String jsonPointer) {
        return root.at(jsonPointer);
    }

    public Duration duration(String jsonPointer) {
        return parse(root.at(jsonPointer).asText());
    }

    public int integer(String jsonPointer, int fallback) {
        JsonNode n = root.at(jsonPointer);
        return n.isMissingNode() || n.isNull() ? fallback : n.asInt(fallback);
    }

    public String text(String jsonPointer, String fallback) {
        JsonNode n = root.at(jsonPointer);
        return n.isMissingNode() || n.isNull() ? fallback : n.asText(fallback);
    }

    public List<String> strings(String jsonPointer) {
        List<String> out = new ArrayList<>();
        root.at(jsonPointer).forEach(n -> out.add(n.asText()));
        return out;
    }

    /** Шаги цепочки NEAR / URGENT / OBSERVATION. */
    public JsonNode chain(String chainType) {
        return root.path("chains").path(chainType);
    }

    public Optional<JsonNode> template(String code) {
        JsonNode t = root.path("templates").path(code);
        return t.isMissingNode() ? Optional.empty() : Optional.of(t);
    }

    /** Падежи специалиста: [родительный, творительный, дательный]. */
    public String[] specialistCases(String specialty) {
        JsonNode n = specialty == null ? null : root.path("specialists").get(specialty);
        if (n == null || n.size() < 3) {
            if (specialty != null) {
                log.warn("Нет падежей для специалиста «{}» — используется «профильный специалист»", specialty);
            }
            n = root.path("specialistFallback");
        }
        return new String[] {n.get(0).asText(), n.get(1).asText(), n.get(2).asText()};
    }

    public boolean onlineAllowed(String specialty) {
        return strings("/schedule/onlineAllowed").contains(specialty);
    }

    public boolean hasSlots(String specialty) {
        if (specialty == null || specialty.isBlank()) {
            return false;
        }
        return strings("/schedule/noSlotsPrefixes").stream().noneMatch(specialty::startsWith);
    }

    public String routeType(String templateCode) {
        return text("/routeTypes/" + (templateCode == null ? "NONE" : templateCode), "CONSULTATION");
    }

    public Optional<String> profileForDuty(String dutySpecialty) {
        JsonNode n = root.path("escalation").path("dutyToProfile").get(dutySpecialty == null ? "" : dutySpecialty);
        return n == null ? Optional.empty() : Optional.of(n.asText());
    }

    /** «30m», «24h», «5d» → Duration. */
    public static Duration parse(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Пустая длительность в route-config.yaml");
        }
        String v = value.trim();
        long n = Long.parseLong(v.substring(0, v.length() - 1));
        return switch (v.charAt(v.length() - 1)) {
            case 'm' -> Duration.ofMinutes(n);
            case 'h' -> Duration.ofHours(n);
            case 'd' -> Duration.ofDays(n);
            default -> throw new IllegalArgumentException("Неизвестная единица длительности: " + value);
        };
    }
}
