package ru.meditron.routing.time;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Модельные часы для всего бэкенда (ROUTES-REQUIREMENTS, раздел 3).
 * Реальное время + сдвиг; сдвиг меняют только эндпоинты /api/sim/clock.
 * Статический доступ нужен, чтобы им пользовались и сущности (значения по умолчанию полей),
 * и сервисы без протаскивания Clock через все конструкторы.
 */
public final class ModelTime {

    /** Даты (сроки «до 18 октября», рабочие дни) считаются в часовом поясе клиники. */
    public static final ZoneId ZONE = ZoneId.of("Europe/Moscow");

    private static final ThreadLocal<Instant> DISPATCH_TIME = new ThreadLocal<>();

    private static final AtomicLong OFFSET_MS = new AtomicLong();

    private ModelTime() {
    }

    public static Instant now() {
        Instant dispatch = DISPATCH_TIME.get();
        return dispatch != null ? dispatch : Instant.now().plusMillis(OFFSET_MS.get());
    }

    /** Execute overdue handlers at their due time, restoring the request clock even on failure. */
    public static void at(Instant instant, Runnable work) {
        Instant previous = DISPATCH_TIME.get();
        DISPATCH_TIME.set(instant);
        try { work.run(); }
        finally {
            if (previous == null) DISPATCH_TIME.remove(); else DISPATCH_TIME.set(previous);
        }
    }

    public static LocalDate today() {
        return LocalDate.ofInstant(now(), ZONE);
    }

    public static Duration offset() {
        return Duration.ofMillis(OFFSET_MS.get());
    }

    public static void advance(Duration step) {
        if (step.isNegative()) {
            throw new IllegalArgumentException("Модельное время нельзя сдвигать назад");
        }
        OFFSET_MS.addAndGet(step.toMillis());
    }

    public static void reset() {
        OFFSET_MS.set(0);
    }
}
