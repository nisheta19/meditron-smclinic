package ru.meditron.routing.service;

import java.util.List;
import java.util.Map;
import java.util.Set;
import ru.meditron.routing.domain.*;

/** Work queue only: never changes medical rules, deadlines or confirmation status. */
public final class RouteReviewPolicy {
    private RouteReviewPolicy() {}
    private static final Set<String> REVIEW_FLAGS = Set.of("NO_CONCLUSION", "INCOMPLETE", "DISCREPANCY");

    public static boolean needsReview(Finding finding) {
        if (finding.getStatus() != FindingStatus.SUGGESTED && finding.getStatus() != FindingStatus.CONFIRMED) return false;
        if (blank(finding.getTargetSpecialty()) || finding.getTargetDays() == null
                || blank(finding.getRouteTemplateCode()) || "MANUAL_REVIEW".equals(finding.getRouteTemplateCode())) return true;
        return finding.getStatus() == FindingStatus.SUGGESTED && (hasReviewFlags(finding.getFlags())
                || finding.getAttributes() != null && Boolean.TRUE.equals(finding.getAttributes().get("uncertain"))
                || finding.getMatchedRule() != null && finding.getMatchedRule().contains(".ifMissing"));
    }

    public static boolean needsReview(Protocol protocol, List<Finding> findings) {
        if (protocol.isSuperseded() || protocol.getStatus() == ProcessingStatus.ANNULLED) return false;
        if (protocol.getStatus() == ProcessingStatus.FAILED) return true;
        boolean unreviewed = findings.isEmpty() || findings.stream().anyMatch(f -> f.getStatus() == FindingStatus.SUGGESTED);
        if (unreviewed && (!protocol.isConclusionFound() || hasReviewFlags(protocol.getFlags()))) return true;
        return findings.stream().anyMatch(RouteReviewPolicy::needsReview);
    }

    private static boolean blank(String value) { return value == null || value.isBlank(); }
    private static boolean hasReviewFlags(List<Map<String, Object>> flags) {
        return flags != null && flags.stream().anyMatch(flag -> flag != null
                && flag.get("code") instanceof String code && REVIEW_FLAGS.contains(code));
    }
}
