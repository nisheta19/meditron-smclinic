package ru.meditron.routing.route;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import ru.meditron.routing.time.ModelTime;
import static org.junit.jupiter.api.Assertions.*;

class ModelTimeDispatchTest {
    @AfterEach void reset() { ModelTime.reset(); }

    @Test void overdueCallbacksScheduleFromTheirOwnDueTimeAndRestoreClock() {
        ModelTime.advance(Duration.ofDays(30));
        Instant target = ModelTime.now();
        Instant due = target.minus(Duration.ofDays(29));
        ModelTime.at(due, () -> {
            assertEquals(due, ModelTime.now());
            assertTrue(ModelTime.now().plus(Duration.ofMinutes(10)).isBefore(target));
            Instant nested = due.plusSeconds(10);
            ModelTime.at(nested, () -> assertEquals(nested, ModelTime.now()));
            assertEquals(due, ModelTime.now());
        });
        assertFalse(ModelTime.now().isBefore(target));
    }

    @Test void failedDispatchDoesNotLeakItsClockToNextRequest() {
        Instant target = ModelTime.now();
        assertThrows(IllegalStateException.class, () -> ModelTime.at(Instant.EPOCH, () -> {
            throw new IllegalStateException("Test failure");
        }));
        assertFalse(ModelTime.now().isBefore(target));
    }
}
