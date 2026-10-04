package ru.meditron.routing.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.util.Arrays;
import java.util.Comparator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.stereotype.Component;
import ru.meditron.routing.dto.MlResultRequest;
import ru.meditron.routing.repository.PatientRepository;
import ru.meditron.routing.service.MlIngestionService;

/**
 * Демо: при пустой базе прогоняет через приём ML готовые результаты из resources/demo/*.json —
 * так же, как если бы их прислал ML. Отключить: DEMO_SEED=false.
 */
@Component
@ConditionalOnProperty(name = "demo.seed", havingValue = "true")
public class DemoDataLoader implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(DemoDataLoader.class);

    private final MlIngestionService ingestion;
    private final PatientRepository patients;
    private final ObjectMapper objectMapper;

    public DemoDataLoader(MlIngestionService ingestion, PatientRepository patients, ObjectMapper objectMapper) {
        this.ingestion = ingestion;
        this.patients = patients;
        this.objectMapper = objectMapper;
    }

    @Override
    public void run(String... args) throws Exception {
        if (patients.count() > 0) {
            return;
        }
        Resource[] files = new PathMatchingResourcePatternResolver().getResources("classpath:demo/*.json");
        Arrays.sort(files, Comparator.comparing(Resource::getFilename));
        for (Resource file : files) {
            try (InputStream in = file.getInputStream()) {
                ingestion.ingest(objectMapper.readValue(in, MlResultRequest.class));
                log.info("Демо-результат загружен: {}", file.getFilename());
            } catch (Exception e) {
                log.warn("Демо-результат {} не загружен: {}", file.getFilename(), e.getMessage());
            }
        }
    }
}
