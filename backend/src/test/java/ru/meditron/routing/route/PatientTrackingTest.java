package ru.meditron.routing.route;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.*;
import ru.meditron.routing.route.repo.*;
import ru.meditron.routing.route.service.PatientTrackingService;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class PatientTrackingTest {
    PatientTrackingService service() throws Exception {
        return new PatientTrackingService(mock(RouteRepository.class), mock(RouteNotificationRepository.class),
                new RouteConfig(new ClassPathResource("routing/route-config.yaml")));
    }
    Route route(String finding, boolean open, String date) {
        var r = new Route(); r.setId(UUID.randomUUID()); r.setPatientId(UUID.randomUUID());
        r.setStage(RouteStage.CREATED); r.setChainType(ChainType.NEAR); r.setTemplateCode("SURGICAL_STANDARD");
        r.setFindingIds(List.of(finding)); r.setOpen(open); r.setCreatedAt(Instant.parse(date));
        r.setMilestones(Map.of("CREATED",date));
        return r;
    }
    @Test void onlyRecordedCheckpointsCountAndRetriesDoNotInflateProgress() throws Exception {
        var s = service(); var r = route("f",true,"2026-10-01T00:00:00Z");
        assertEquals(10,s.progress(r));
        r.setStage(RouteStage.AWAITING_TACTIC);
        r.setMilestones(Map.of("CREATED","x","BOOKED","x","VISIT","x"));
        r.setStageHistory(List.of(Map.of("stage","NOTIFIED"),Map.of("stage","BOOKED"),Map.of("stage","NO_SHOW"),Map.of("stage","BOOKED")));
        assertEquals(40,s.progress(r));
        r.setStage(RouteStage.NOT_ENGAGED);
        assertEquals(40,s.progress(r));
        r.setStage(RouteStage.CLOSED); r.setCloseReason(CloseReason.PATIENT_REFUSED); r.setOpen(false);
        assertEquals(40,s.progress(r));
        r.setCloseReason(CloseReason.SURGERY_NOT_INDICATED);
        assertEquals(100,s.progress(r));
        r.setStage(RouteStage.COMPLETED);
        assertEquals(100,s.progress(r));
    }
    @Test void observationAndProcedureUseTheirOwnWorkflow() throws Exception {
        var s = service(); var r = route("f",true,"2026-10-01T00:00:00Z");
        r.setChainType(ChainType.OBSERVATION);
        assertEquals(17,s.progress(r));
        r.setChainType(ChainType.NEAR); r.setMilestones(Map.of("CREATED","x","CONTROL_ULTRASOUND","x"));
        assertEquals(33,s.progress(r));
        r.setMilestones(Map.of("CREATED","x")); r.setTacticSubtype("PROCEDURE");
        assertEquals(14,s.progress(r));
    }
    @Test void stageBelongsToDisplayedFindingAndPrefersOpenRouteOverOldClosedVersion() throws Exception {
        var s = service(); var r = route("shown",true,"2026-10-01T00:00:00Z");
        var unrelated = route("other",true,"2026-10-04T00:00:00Z");
        var closed = route("shown",false,"2026-10-03T00:00:00Z"); closed.setStage(RouteStage.COMPLETED);
        var latest = Instant.parse("2026-10-03T12:00:00Z");
        var batch = new PatientTrackingService.Batch(Map.of(r.getPatientId(),List.of(unrelated,closed,r)),
                Map.of(r.getPatientId(),new PatientTrackingService.Messages(2,latest)));
        var summary = s.summarize(batch,r.getPatientId(),"shown");
        assertEquals(r.getId().toString(),summary.routeId()); assertEquals(10,summary.progressPercent());
        assertEquals(2,summary.notificationCount()); assertEquals(latest,summary.lastNotifiedAt());
        var emergency = s.summarize(batch,r.getPatientId(),"unrouted-emergency");
        assertNull(emergency.routeId()); assertNull(emergency.progressPercent());
        assertEquals(2,emergency.notificationCount());
        assertEquals(2,batch.activeCount(r.getPatientId()));
    }
    @Test void noRouteDoesNotInventProgressAndNoMessagesMeansZero() throws Exception {
        var x = service().summarize(PatientTrackingService.Batch.empty(),UUID.randomUUID(),null);
        assertNull(x.stage()); assertNull(x.progressPercent()); assertNull(x.lastNotifiedAt()); assertEquals(0,x.notificationCount());
    }
    @Test void bulkReadExcludesFailedDeliveryAndDoesNotIssuePerPatientQueries() throws Exception {
        var routes = mock(RouteRepository.class); var notes = mock(RouteNotificationRepository.class);
        var s = new PatientTrackingService(routes,notes,new RouteConfig(new ClassPathResource("routing/route-config.yaml")));
        var ids = List.of(UUID.randomUUID(),UUID.randomUUID());
        s.load(ids);
        verify(routes).findByPatientIdIn(ids);
        verify(notes).summarizePatients(ids,RouteNotification.Delivery.FAILED);
        verifyNoMoreInteractions(routes,notes);
    }
}
