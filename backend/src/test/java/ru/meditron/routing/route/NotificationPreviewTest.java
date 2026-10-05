package ru.meditron.routing.route;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import ru.meditron.routing.repository.PatientRepository;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.*;
import ru.meditron.routing.route.repo.*;
import ru.meditron.routing.route.service.*;
import ru.meditron.routing.exception.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class NotificationPreviewTest {
    @Test void previewMatchesSentTextAndHasNoSideEffects() throws Exception {
        var repo = mock(RouteNotificationRepository.class);
        var timers = mock(TimerService.class);
        var journal = mock(JournalService.class, RETURNS_DEEP_STUBS);
        var service = new NotificationService(repo, new RouteConfig(new ClassPathResource("routing/route-config.yaml")),
                timers, journal, mock(PatientRepository.class), mock(EscalationRepository.class));
        var route = route();
        var preview = service.preview(route, "INITIAL");
        assertTrue(preview.fullText().contains("хирурга"));
        assertFalse(preview.fullText().contains("{spec"));
        assertEquals(RouteStage.CREATED, route.getStage());
        verifyNoInteractions(repo, timers, journal);
        when(repo.save(any())).thenAnswer(i -> i.getArgument(0));
        var sent = service.sendManual(route, "INITIAL", true, "Тестовый врач");
        assertEquals(preview.fullText(), sent.getFullText());
        assertEquals(preview.shortText(), sent.getShortText());
        verify(repo, times(1)).save(any());
    }

    @Test void previewRespectsClosedEmergencyAndAutomaticOnlyRestrictions() throws Exception {
        var repo = mock(RouteNotificationRepository.class);
        var service = new NotificationService(repo, new RouteConfig(new ClassPathResource("routing/route-config.yaml")),
                mock(TimerService.class), mock(JournalService.class), mock(PatientRepository.class), mock(EscalationRepository.class));
        var route = route();
        route.setOpen(false);
        assertThrows(ConflictException.class, () -> service.preview(route, "INITIAL"));
        route.setOpen(true); route.setChainType(ChainType.EMERGENCY);
        assertThrows(ConflictException.class, () -> service.preview(route, "INITIAL"));
        route.setChainType(ChainType.NEAR);
        assertThrows(BadRequestException.class, () -> service.preview(route, "BOOKING_CONFIRMED"));
        assertThrows(BadRequestException.class, () -> service.preview(route, "missing"));
        verifyNoInteractions(repo);
    }

    private Route route() {
        var r = new Route(); r.setId(UUID.randomUUID()); r.setPatientId(UUID.randomUUID());
        r.setSpecialty("Хирург"); r.setOpen(true); r.setStage(RouteStage.CREATED); r.setChainType(ChainType.NEAR);
        return r;
    }
}
