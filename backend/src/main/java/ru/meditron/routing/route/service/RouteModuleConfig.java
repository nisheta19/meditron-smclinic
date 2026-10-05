package ru.meditron.routing.route.service;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

/** Периодически исполняет таймеры в реальном времени (в демо время двигают /api/sim/clock/advance). */
@Configuration
@EnableScheduling
@org.springframework.boot.autoconfigure.condition.ConditionalOnProperty(name = "routes.enabled", havingValue = "true", matchIfMissing = true)
public class RouteModuleConfig {

    private final TimerRunner runner;

    public RouteModuleConfig(TimerRunner runner) {
        this.runner = runner;
    }

    @Scheduled(fixedDelayString = "${routes.tick-ms:15000}", initialDelayString = "${routes.tick-ms:15000}")
    public void tick() {
        runner.runDue();
    }
}
