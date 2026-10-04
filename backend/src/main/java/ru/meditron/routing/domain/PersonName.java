package ru.meditron.routing.domain;

import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/** Explicit MIS parts take precedence. Splitting fullName is only a legacy fallback. */
public record PersonName(String lastName, String firstName, String middleName) {
    public PersonName {
        lastName = clean(lastName);
        firstName = clean(firstName);
        middleName = clean(middleName);
    }

    public static PersonName resolve(String fullName, String lastName, String firstName, String middleName) {
        PersonName explicit = new PersonName(lastName, firstName, middleName);
        if (explicit.lastName() != null || explicit.firstName() != null) return explicit;
        String full = clean(fullName);
        if (full == null) return new PersonName(null, null, null);
        String[] parts = full.split(" ", 3);
        return new PersonName(parts[0], parts.length > 1 ? parts[1] : null, parts.length > 2 ? parts[2] : null);
    }

    public String fullName() { return join(lastName, firstName, middleName); }

    public String shortName() { return join(lastName, initial(firstName), initial(middleName)); }

    private static String initial(String part) {
        return part == null ? null : part.substring(0, part.offsetByCodePoints(0, 1)) + ".";
    }

    private static String join(String... parts) {
        return Stream.of(parts).filter(Objects::nonNull).collect(Collectors.joining(" "));
    }

    private static String clean(String value) {
        if (value == null) return null;
        String normalized = value.replaceAll("(?U)\\s+", " ").trim();
        return normalized.isEmpty() ? null : normalized;
    }
}
