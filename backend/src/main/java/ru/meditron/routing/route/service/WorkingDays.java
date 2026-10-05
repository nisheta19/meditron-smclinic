package ru.meditron.routing.route.service;

import java.time.DayOfWeek;
import java.time.Instant;
import java.time.ZonedDateTime;
import ru.meditron.routing.time.ModelTime;

/** Рабочие дни: понедельник–пятница, праздники не учитываются (раздел 3). */
public final class WorkingDays {

    private WorkingDays() {
    }

    public static Instant plus(Instant from, int workingDays) {
        ZonedDateTime t = from.atZone(ModelTime.ZONE);
        int added = 0;
        while (added < workingDays) {
            t = t.plusDays(1);
            if (t.getDayOfWeek() != DayOfWeek.SATURDAY && t.getDayOfWeek() != DayOfWeek.SUNDAY) {
                added++;
            }
        }
        return t.toInstant();
    }
}
