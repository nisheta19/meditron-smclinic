package ru.meditron.routing.route;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.ChainType;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.domain.RouteStage;
import ru.meditron.routing.route.domain.RouteTimer;
import ru.meditron.routing.route.repo.RouteRepository;
import ru.meditron.routing.route.service.*;
import ru.meditron.routing.time.ModelTime;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Заглушка расписания (раздел 11) и планирование цепочек (раздел 6) без БД. */
class ScheduleAndChainTest {
    static RouteConfig config;

    @BeforeAll static void load() throws Exception {
        config = new RouteConfig(new ClassPathResource("routing/route-config.yaml"));
    }

    @Test void slotsRespectOnlineRules() {
        ScheduleService s = new ScheduleService(config, mock(RouteRepository.class));
        assertTrue(s.slots("Хирург", "CONSULTATION", 12).stream().noneMatch(x -> x.online()));
        assertTrue(s.slots("Эндокринолог", "CONSULTATION", 12).stream().anyMatch(x -> x.online()));
        assertTrue(s.slots("Дежурный хирург", "CONSULTATION", 12).isEmpty());
        assertTrue(s.slots("Гастроэнтеролог", "ULTRASOUND", 12).stream().noneMatch(x -> x.online()));
        var slot = s.slots("Онколог / маммолог-онколог", "CONSULTATION", 3).get(0);
        assertEquals(slot.dateTime(), s.decode(slot.id()).dateTime());
        assertEquals(slot.doctorName(), s.decode(slot.id()).doctorName());
        assertNotEquals("Дежурный врач клиники", slot.doctorName());
    }

    private Route route(ChainType type) {
        Route r = new Route();
        r.setId(UUID.randomUUID());
        r.setPatientId(UUID.randomUUID());
        r.setSpecialty("Хирург");
        r.setChainType(type);
        r.setStage(RouteStage.CREATED);
        return r;
    }

    @Test void nearChainSchedulesAllStepsAndRestartSkipsInitial() {
        TimerService timers = mock(TimerService.class);
        ChainService chains = new ChainService(config, timers, mock(NotificationService.class), mock(TaskService.class),
                mock(RouteStateService.class));
        Route r = route(ChainType.NEAR);
        chains.start(r, ChainType.NEAR, ModelTime.now(), true, "test");
        verify(timers, times(6)).schedule(eq(RouteTimer.Kind.CHAIN_STEP), eq("chain"), any(), any(), any(), isNull(), anyMap());
        clearInvocations(timers);
        chains.start(r, ChainType.NEAR, ModelTime.now(), false, "restart");
        verify(timers, times(5)).schedule(eq(RouteTimer.Kind.CHAIN_STEP), eq("chain"), any(), any(), any(), isNull(), anyMap());
        verify(timers, atLeastOnce()).cancelRoute(r.getId(), "chain");
    }

    @Test void observationChainSchedulesRemindersBeforeControl() {
        TimerService timers = mock(TimerService.class);
        ChainService chains = new ChainService(config, timers, mock(NotificationService.class), mock(TaskService.class),
                mock(RouteStateService.class));
        Route r = route(ChainType.OBSERVATION);
        r.setControlAt(ModelTime.now().plus(Duration.ofDays(180)));
        chains.start(r, ChainType.OBSERVATION, ModelTime.now(), true, "test");
        verify(timers, times(2)).schedule(eq(RouteTimer.Kind.OBSERVATION_REMINDER), eq("chain"), any(), any(), any(), isNull(), anyMap());
        verify(timers).schedule(eq(RouteTimer.Kind.OBSERVATION_CONTROL_DATE), eq("chain"), eq(r.getControlAt()), any(), any(), isNull(), anyMap());
    }

    @Test void chainStepSkippedWhenPatientBooked() {
        NotificationService n = mock(NotificationService.class);
        ChainService chains = new ChainService(config, mock(TimerService.class), n, mock(TaskService.class),
                mock(RouteStateService.class));
        Route r = route(ChainType.NEAR);
        r.setStage(RouteStage.BOOKED);
        chains.runStep(r, Map.of("action", "MESSAGE", "template", "REMINDER_24H", "at", "24h"));
        verifyNoInteractions(n);
    }

    @Test void emergencyChainSendsNothing() {
        TimerService timers = mock(TimerService.class);
        ChainService chains = new ChainService(config, timers, mock(NotificationService.class), mock(TaskService.class),
                mock(RouteStateService.class));
        chains.start(route(ChainType.EMERGENCY), ChainType.EMERGENCY, ModelTime.now(), true, "test");
        verify(timers, never()).schedule(any(), any(), any(), any(), any(), any(), anyMap());
    }
}
