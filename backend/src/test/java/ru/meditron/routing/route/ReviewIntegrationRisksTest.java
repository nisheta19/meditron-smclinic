package ru.meditron.routing.route;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;
import ru.meditron.routing.domain.Finding;
import ru.meditron.routing.domain.FindingLevel;
import ru.meditron.routing.domain.FindingStatus;
import ru.meditron.routing.repository.FindingRepository;
import ru.meditron.routing.repository.ProtocolRepository;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.*;
import ru.meditron.routing.route.repo.*;
import ru.meditron.routing.route.service.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Regression coverage for defects identified before integration. */
class ReviewIntegrationRisksTest {
    private RouteConfig config() throws Exception {
        return new RouteConfig(new ClassPathResource("routing/route-config.yaml"));
    }

    private JournalService journal() {
        return new JournalService(mock(JournalRepository.class), mock(PlatformTransactionManager.class));
    }

    private Finding finding(FindingLevel level, FindingStatus status) {
        Finding f = new Finding();
        f.setId(UUID.randomUUID());
        f.setLevel(level);
        f.setStatus(status);
        f.setTargetSpecialty("Хирург");
        f.setTargetDays(level == FindingLevel.URGENT ? 3 : 14);
        f.setRouteTemplateCode("SURGICAL_STANDARD");
        return f;
    }

    @Test void rejectingUrgentFindingMustRecalculateRemainingChain() throws Exception {
        UUID patientId = UUID.randomUUID();
        Finding rejected = finding(FindingLevel.URGENT, FindingStatus.REJECTED);
        Finding remaining = finding(FindingLevel.PLANNED, FindingStatus.CONFIRMED);
        FindingRepository findings = mock(FindingRepository.class);
        when(findings.findByPatientIdOrderByCreatedAtDesc(patientId)).thenReturn(List.of(rejected, remaining));
        Route r = new Route();
        r.setId(UUID.randomUUID());
        r.setPatientId(patientId);
        r.setSpecialty("Хирург");
        r.setChainType(ChainType.URGENT);
        r.setStage(RouteStage.NOTIFIED);
        r.setFindingIds(new ArrayList<>(List.of(rejected.getId().toString(), remaining.getId().toString())));
        RouteRepository routes = mock(RouteRepository.class);
        when(routes.findByPatientIdAndOpenTrue(patientId)).thenReturn(List.of(r));
        when(routes.save(any())).thenAnswer(i -> i.getArgument(0));
        RouteEngine engine = new RouteEngine(findings, mock(ProtocolRepository.class), routes,
                mock(AppointmentRepository.class), mock(ChainService.class), mock(NotificationService.class),
                mock(TaskService.class), mock(TimerService.class), mock(RouteStateService.class), journal(), config());
        engine.reconcile(patientId, "Review: reject urgent finding");
        assertEquals(List.of(remaining.getId().toString()), r.getFindingIds());
        assertEquals(ChainType.NEAR, r.getChainType(), "Requirement 4.4: recompute chain from remaining findings");
    }

    @Test void manuallyConfirmedEmergencyMustStartEscalation() throws Exception {
        UUID patientId = UUID.randomUUID();
        Finding emergency = finding(FindingLevel.EMERGENCY, FindingStatus.CONFIRMED);
        ru.meditron.routing.domain.Patient patient = new ru.meditron.routing.domain.Patient();
        patient.setId(patientId);
        emergency.setPatient(patient);
        FindingRepository findings = mock(FindingRepository.class);
        when(findings.findByPatientIdOrderByCreatedAtDesc(patientId)).thenReturn(List.of(emergency));
        EscalationRepository escalations = mock(EscalationRepository.class);
        when(escalations.findByPatientIdOrderByStartedAtDesc(patientId)).thenReturn(List.of());
        EscalationService service = new EscalationService(escalations, findings, mock(RouteRepository.class),
                mock(TimerService.class), mock(TaskService.class), journal(), config(),
                mock(RouteStateService.class), mock(ChainService.class));
        when(escalations.save(any())).thenAnswer(i -> i.getArgument(0));
        service.onFindingsChanged(patientId);
        verify(escalations, atLeastOnce()).save(any(Escalation.class));
    }

    @Test void failedTimerMustNotBeRecordedAsDone() {
        Route r = new Route();
        r.setId(UUID.randomUUID());
        r.setStage(RouteStage.CREATED);
        RouteTimer timer = new RouteTimer();
        timer.setId(UUID.randomUUID());
        timer.setRouteId(r.getId());
        timer.setKind(RouteTimer.Kind.CHAIN_STEP);
        timer.setDueAt(Instant.EPOCH);
        timer.setPayload(Map.of());
        RouteTimerRepository timers = mock(RouteTimerRepository.class);
        when(timers.findFirstByStatusAndDueAtLessThanEqualOrderByDueAtAscCreatedAtAsc(eq(RouteTimer.Status.PENDING), any()))
                .thenReturn(Optional.of(timer), Optional.empty());
        RouteRepository routes = mock(RouteRepository.class);
        when(routes.findById(r.getId())).thenReturn(Optional.of(r));
        ChainService chains = mock(ChainService.class);
        doThrow(new IllegalStateException("Review: notification handler failed")).when(chains).runStep(any(), any());
        PlatformTransactionManager transactions = mock(PlatformTransactionManager.class);
        when(transactions.getTransaction(any())).thenReturn(new SimpleTransactionStatus());
        TimerRunner runner = new TimerRunner(timers, routes, mock(EscalationRepository.class), chains,
                mock(RouteEngine.class), mock(EscalationService.class), mock(NotificationService.class), transactions, mock(RouteWriteLock.class));
        runner.runDue();
        verify(transactions).rollback(any());
        assertNotEquals(RouteTimer.Status.DONE, timer.getStatus(), "Failed handler must remain retryable or record failure");
    }
}
