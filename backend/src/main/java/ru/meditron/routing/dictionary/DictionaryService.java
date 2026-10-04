package ru.meditron.routing.dictionary;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

/**
 * Словарь находок из findings-dictionary.yaml — единый источник кодов для ML и бэкенда.
 * Медицинские правила (пороги, специалисты, сроки) живут в словаре, а не в коде.
 */
@Service
public class DictionaryService {

    private static final Logger log = LoggerFactory.getLogger(DictionaryService.class);

    private final Resource resource;
    private final ObjectMapper yaml = new ObjectMapper(new YAMLFactory());

    private String version;
    private JsonNode document;
    private final Map<String, JsonNode> entries = new LinkedHashMap<>();
    private final Map<String, JsonNode> flags = new LinkedHashMap<>();

    public DictionaryService(@Value("${dictionary.location:classpath:dictionary/findings-dictionary.yaml}") Resource resource) {
        this.resource = resource;
    }

    @PostConstruct
    void load() throws IOException {
        try (InputStream in = resource.getInputStream()) {
            JsonNode root = yaml.readTree(in);
            document = root;
            version = root.path("version").asText("unknown");
            entries.clear();
            for (JsonNode f : root.path("findings")) {
                entries.put(f.path("code").asText(), f);
            }
            flags.clear();
            root.path("flags").fields().forEachRemaining(e -> flags.put(e.getKey(), e.getValue()));
        }
        log.info("Словарь находок {} загружен: {} кодов, {} флагов", version, entries.size(), flags.size());
    }

    public String version() {
        return version;
    }

    /** Includes shared ML policy, flags and version, not just individual findings. */
    public JsonNode document(Collection<?> selectedFindings) {
        var copy = (com.fasterxml.jackson.databind.node.ObjectNode) document.deepCopy();
        copy.set("findings", yaml.valueToTree(selectedFindings));
        return copy;
    }

    public Optional<JsonNode> find(String code) {
        return Optional.ofNullable(entries.get(code));
    }

    public Collection<JsonNode> all() {
        return entries.values();
    }

    /** Описание флага из блока flags словаря (name, setBy, when). */
    public Optional<JsonNode> flag(String code) {
        return Optional.ofNullable(flags.get(code));
    }

    public boolean isActive(JsonNode entry) {
        return entry.path("active").asBoolean(false);
    }

    /** Все синонимы плоским списком (в словаре они бывают списком или группами certain/suspected). */
    public List<String> synonyms(JsonNode entry) {
        List<String> result = new ArrayList<>();
        JsonNode s = entry.path("synonyms");
        if (s.isArray()) {
            s.forEach(n -> result.add(n.asText()));
        } else if (s.isObject()) {
            s.fields().forEachRemaining(group -> group.getValue().forEach(n -> result.add(n.asText())));
        }
        return result;
    }
}
