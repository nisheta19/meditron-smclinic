package ru.meditron.routing.service;

import java.text.Collator;
import java.util.Comparator;
import java.util.Locale;
import java.util.function.Function;
import ru.meditron.routing.dto.PatientShortDto;
import ru.meditron.routing.exception.BadRequestException;

/** Сортируем до пагинации; пустые значения всегда последние, ID стабилизирует порядок. */
public final class PatientSort {
    private PatientSort() {}

    public static Comparator<PatientShortDto> comparator(String key, String direction) {
        if (!"asc".equals(direction) && !"desc".equals(direction))
            throw new BadRequestException("INVALID_SORT", "sortDirection: asc или desc");
        boolean desc = "desc".equals(direction);
        Collator ru = Collator.getInstance(Locale.forLanguageTag("ru"));
        ru.setStrength(Collator.SECONDARY);
        Comparator<String> text = ru::compare;
        Comparator<PatientShortDto> result = switch (key) {
            case "patient" -> by(PatientShortDto::fullName, text, desc);
            case "finding" -> by(p -> p.topFindings().isEmpty() ? null : p.topFindings().getFirst().name(), text, desc);
            case "due" -> by(p -> p.topFindings().isEmpty() ? null : p.topFindings().getFirst().targetDays(), Comparator.<Integer>naturalOrder(), desc);
            case "stage" -> by(p -> p.tracking() == null ? null : p.tracking().progressPercent(), Comparator.<Integer>naturalOrder(), desc);
            case "notified" -> by(p -> p.tracking() == null ? null : p.tracking().lastNotifiedAt(), Comparator.<java.time.Instant>naturalOrder(), desc);
            case "receivedAt" -> by(PatientShortDto::receivedAt, Comparator.naturalOrder(), desc);
            case "studyDate" -> by(PatientShortDto::lastStudyDate, Comparator.naturalOrder(), desc);
            case "default" -> Comparator.comparingInt((PatientShortDto p) -> p.maxLevel() == null ? 0 : p.maxLevel().rank()).reversed()
                    .thenComparing(by(PatientShortDto::receivedAt, Comparator.naturalOrder(), true));
            default -> throw new BadRequestException("INVALID_SORT", "sortBy: patient, finding, stage, due, notified, receivedAt, studyDate или default");
        };
        return result.thenComparing(PatientShortDto::id);
    }

    private static <T> Comparator<PatientShortDto> by(Function<PatientShortDto, T> value, Comparator<? super T> order, boolean desc) {
        return Comparator.comparing(value, Comparator.nullsLast(desc ? order.reversed() : order));
    }
}
