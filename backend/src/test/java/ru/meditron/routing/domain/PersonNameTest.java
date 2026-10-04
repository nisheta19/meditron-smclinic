package ru.meditron.routing.domain;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PersonNameTest {
    @Test void partsFromMisWin() {
        var n = PersonName.of("Соколова", "Анна", "Сергеевна", "что угодно");
        assertEquals("Соколова", n.lastName());
        assertEquals("Анна", n.firstName());
        assertEquals("Сергеевна", n.middleName());
        assertEquals("Соколова Анна Сергеевна", n.full());
        assertEquals("Соколова А. С.", n.shortName());
    }
    @Test void middleNameIsOptional() {
        var n = PersonName.of("Smith", "John", null, null);
        assertNull(n.middleName());
        assertEquals("Smith John", n.full());
        assertEquals("Smith J.", n.shortName());
    }
    @Test void doubleSurnameKeptWhenPartsGiven() {
        assertEquals("Петрова-Водкина Е. И.", PersonName.of("Петрова-Водкина", "Елена", "Игоревна", null).shortName());
    }
    @Test void legacyFullNameIsParsed() {
        var n = PersonName.of(null, null, null, "  Иванов   Пётр  Ильич ");
        assertEquals("Иванов", n.lastName());
        assertEquals("Пётр", n.firstName());
        assertEquals("Ильич", n.middleName());
        assertEquals("Иванов П. И.", n.shortName());
    }
    @Test void legacyTwoWordsHasNoMiddleName() {
        var n = PersonName.parse("Пациент 001");
        assertEquals("Пациент", n.lastName());
        assertEquals("001", n.firstName());
        assertNull(n.middleName());
    }
    @Test void blankNameIsEmpty() {
        var n = PersonName.parse("   ");
        assertNull(n.lastName());
        assertEquals("", n.full());
        assertEquals("", n.shortName());
    }
    @Test void extraSpacesInPartsAreCleaned() {
        var n = PersonName.of("  Ким ", " Мин  Хо ", "", null);
        assertEquals("Ким", n.lastName());
        assertEquals("Мин Хо", n.firstName());
        assertNull(n.middleName());
        assertEquals("Ким М.", n.shortName());
    }
}
