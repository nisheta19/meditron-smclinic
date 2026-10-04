package ru.meditron.routing.service;

import java.util.List;
import org.junit.jupiter.api.Test;
import ru.meditron.routing.dto.PatientShortDto;
import ru.meditron.routing.dto.TopFindingDto;
import ru.meditron.routing.exception.BadRequestException;
import static org.junit.jupiter.api.Assertions.*;

class PatientSortTest {
    PatientShortDto patient(String id, String name, String finding, Integer days) {
        return new PatientShortDto(id, id, name, name, null, null, name, null, null, null, null, null,
                false, null, null, 0, 0, null, null, finding == null ? 0 : 1,
                finding == null ? List.of() : List.of(new TopFindingDto(id, "TEST", finding, null, null, null, days)));
    }

    @Test void russianNamesAndStableTies() {
        var a = patient("1", "Андреева Анна", "Полип", 7);
        var b = patient("2", "Яковлева Анна", "Киста", 3);
        var c = patient("3", "Андреева Анна", "Полип", 7);
        assertEquals(List.of(a, c, b), List.of(c, b, a).stream().sorted(PatientSort.comparator("patient", "asc")).toList());
        assertEquals(List.of(b, a, c), List.of(c, a, b).stream().sorted(PatientSort.comparator("patient", "desc")).toList());
    }

    @Test void missingValuesStayLastInEitherDirection() {
        var zero = patient("1", "А", "Полип", 0);
        var large = patient("2", "Б", "Киста", 30);
        var empty = patient("3", "В", null, null);
        assertEquals(List.of(zero, large, empty), List.of(empty, large, zero).stream().sorted(PatientSort.comparator("due", "asc")).toList());
        assertEquals(List.of(large, zero, empty), List.of(empty, zero, large).stream().sorted(PatientSort.comparator("due", "desc")).toList());
        assertEquals(List.of(large, zero, empty), List.of(empty, zero, large).stream().sorted(PatientSort.comparator("finding", "asc")).toList());
    }

    @Test void rejectsUnknownAndUnavailableSorts() {
        for (String key : List.of("stage", "notified", "oops"))
            assertThrows(BadRequestException.class, () -> PatientSort.comparator(key, "asc"));
        assertThrows(BadRequestException.class, () -> PatientSort.comparator("patient", "oops"));
    }
}
