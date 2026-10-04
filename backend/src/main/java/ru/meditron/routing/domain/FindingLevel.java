package ru.meditron.routing.domain;

/**
 * Уровень срочности находки (поле level в словаре dict-v2).
 * EMERGENCY — экстренно (дежурный врач, без сообщения пациенту от системы);
 * URGENT — срочно (короткий срок 1–3 дня); PLANNED — плановый маршрут.
 */
public enum FindingLevel {
    EMERGENCY(3), URGENT(2), PLANNED(1);

    private final int rank;

    FindingLevel(int rank) {
        this.rank = rank;
    }

    public int rank() {
        return rank;
    }

    public static FindingLevel parse(String value, FindingLevel fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        try {
            return FindingLevel.valueOf(value.trim().toUpperCase());
        } catch (IllegalArgumentException e) {
            return fallback;
        }
    }

    /** Более срочный из двух (null не считается). */
    public static FindingLevel max(FindingLevel a, FindingLevel b) {
        if (a == null) {
            return b;
        }
        if (b == null) {
            return a;
        }
        return a.rank >= b.rank ? a : b;
    }
}
