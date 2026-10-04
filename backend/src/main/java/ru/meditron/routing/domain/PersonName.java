package ru.meditron.routing.domain;

import java.util.Arrays;
import java.util.Locale;

/**
 * ФИО по частям. Отчество необязательно.
 * МИС передаёт части отдельно (lastName / firstName / middleName); если пришла только строка fullName
 * (старый формат), она разбивается: первое слово — фамилия, второе — имя, остальное — отчество.
 */
public record PersonName(String lastName, String firstName, String middleName) {

    public static PersonName of(String lastName, String firstName, String middleName, String fullName) {
        if (!blank(lastName) || !blank(firstName)) {
            return new PersonName(clean(lastName), clean(firstName), clean(middleName));
        }
        return parse(fullName);
    }

    /** Запасной путь для старого формата: «Фамилия Имя Отчество» одной строкой. */
    public static PersonName parse(String fullName) {
        if (blank(fullName)) {
            return new PersonName(null, null, null);
        }
        String[] parts = fullName.trim().split("\\s+");
        String last = parts[0];
        String first = parts.length > 1 ? parts[1] : null;
        String middle = parts.length > 2 ? String.join(" ", Arrays.copyOfRange(parts, 2, parts.length)) : null;
        return new PersonName(last, first, middle);
    }

    /** «Фамилия Имя Отчество» без лишних пробелов. */
    public String full() {
        StringBuilder sb = new StringBuilder();
        for (String p : new String[] {lastName, firstName, middleName}) {
            if (!blank(p)) {
                if (!sb.isEmpty()) {
                    sb.append(' ');
                }
                sb.append(p);
            }
        }
        return sb.toString();
    }

    /** «Фамилия И. О.» — для списков. Без имени возвращается только фамилия. */
    public String shortName() {
        if (blank(lastName)) {
            return full();
        }
        StringBuilder sb = new StringBuilder(lastName);
        if (!blank(firstName)) {
            sb.append(' ').append(initial(firstName)).append('.');
            if (!blank(middleName)) {
                sb.append(' ').append(initial(middleName)).append('.');
            }
        }
        return sb.toString();
    }

    private static String initial(String s) {
        return s.trim().substring(0, s.trim().offsetByCodePoints(0, 1)).toUpperCase(Locale.ROOT);
    }

    private static String clean(String s) {
        return blank(s) ? null : s.trim().replaceAll("\\s+", " ");
    }

    private static boolean blank(String s) {
        return s == null || s.isBlank();
    }
}
