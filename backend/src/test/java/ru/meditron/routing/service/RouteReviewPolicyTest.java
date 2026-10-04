package ru.meditron.routing.service;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import ru.meditron.routing.domain.*;
import static org.junit.jupiter.api.Assertions.*;

class RouteReviewPolicyTest {
    private Finding finding() {
        Finding f = new Finding();
        f.setStatus(FindingStatus.SUGGESTED);
        f.setTargetSpecialty("Гинеколог");
        f.setTargetDays(7);
        f.setRouteTemplateCode("CONSULT_OBSERVATION");
        return f;
    }
    private Protocol protocol() {
        Protocol p = new Protocol();
        p.setStatus(ProcessingStatus.DONE);
        p.setConclusionFound(true);
        return p;
    }
    @Test void calculatedDirectionDoesNotWaitForRoutineConfirmation() {
        for (FindingLevel level : FindingLevel.values()) {
            Finding f = finding(); f.setLevel(level);
            assertFalse(RouteReviewPolicy.needsReview(protocol(), List.of(f)));
        }
    }
    @Test void incompleteDirectionNeedsReviewEvenWhenConfirmed() {
        Finding f = finding(); f.setStatus(FindingStatus.CONFIRMED);
        f.setTargetDays(null); assertTrue(RouteReviewPolicy.needsReview(f));
        f.setTargetDays(7); f.setTargetSpecialty(" "); assertTrue(RouteReviewPolicy.needsReview(f));
        f.setTargetSpecialty("Координатор"); f.setRouteTemplateCode("MANUAL_REVIEW");
        assertTrue(RouteReviewPolicy.needsReview(f));
    }
    @Test void missingAttributesFallbackIsStillRecognizedAfterRouteMerge() {
        Finding f = finding(); f.setMatchedRule("CODE.ifMissing + backend.mergeRules[gynecology]");
        assertTrue(RouteReviewPolicy.needsReview(f));
        f.setStatus(FindingStatus.CONFIRMED); assertFalse(RouteReviewPolicy.needsReview(f));
    }
    @Test void ambiguousFindingNeedsDecision() {
        Finding f = finding(); f.setAttributes(Map.of("uncertain", true));
        assertTrue(RouteReviewPolicy.needsReview(f));
        f.setStatus(FindingStatus.CONFIRMED); assertFalse(RouteReviewPolicy.needsReview(f));
    }
    @Test void reviewFlagsNeedDecisionButInformationalFlagsDoNot() {
        for (String code : List.of("INCOMPLETE", "DISCREPANCY", "NO_CONCLUSION")) {
            Finding f = finding(); f.setFlags(List.of(Map.of("code", code)));
            assertTrue(RouteReviewPolicy.needsReview(f));
            f.setStatus(FindingStatus.REJECTED); assertFalse(RouteReviewPolicy.needsReview(f));
        }
        Finding f = finding(); f.setFlags(List.of(Map.of("code", "MINOR"), Map.of("code", "MERGED_GYNECOLOGY")));
        assertFalse(RouteReviewPolicy.needsReview(f));
    }
    @Test void missingConclusionWaitsUntilAllFindingsReviewed() {
        Protocol p = protocol(); p.setConclusionFound(false);
        Finding f = finding(); assertTrue(RouteReviewPolicy.needsReview(p, List.of(f)));
        f.setStatus(FindingStatus.CONFIRMED); assertFalse(RouteReviewPolicy.needsReview(p, List.of(f)));
        assertTrue(RouteReviewPolicy.needsReview(p, List.of()));
    }
    @Test void failedNeedsReviewButReplacedAndAnnulledDoNot() {
        Protocol p = protocol(); p.setStatus(ProcessingStatus.FAILED);
        assertTrue(RouteReviewPolicy.needsReview(p, List.of()));
        p.setSuperseded(true); assertFalse(RouteReviewPolicy.needsReview(p, List.of()));
        p.setSuperseded(false); p.setStatus(ProcessingStatus.ANNULLED);
        assertFalse(RouteReviewPolicy.needsReview(p, List.of()));
    }
    @Test void normalStudyDoesNotEnterInbox() {
        assertFalse(RouteReviewPolicy.needsReview(protocol(), List.of()));
    }
    @Test void inactiveFindingsDoNotBlockQueue() {
        Finding f = finding(); f.setRouteTemplateCode("MANUAL_REVIEW");
        for (FindingStatus status : List.of(FindingStatus.REJECTED, FindingStatus.REMOVED)) {
            f.setStatus(status); assertFalse(RouteReviewPolicy.needsReview(protocol(), List.of(f)));
        }
    }
    @Test void absentLegacyAttributesAndFlagsAreSafe() {
        Finding f = finding(); f.setAttributes(null); f.setFlags(List.of(Map.of()));
        assertFalse(RouteReviewPolicy.needsReview(f));
        f.setFlags(null); assertFalse(RouteReviewPolicy.needsReview(f));
    }
}
