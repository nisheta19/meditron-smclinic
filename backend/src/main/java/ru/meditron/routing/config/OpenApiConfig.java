package ru.meditron.routing.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI meditronOpenApi() {
        return new OpenAPI().info(new Info()
                .title("MEDITRON · СМ-Клиника API")
                .description("Выявление клинически значимых находок и маршрутизация пациента")
                .version("0.0.1"));
    }
}
