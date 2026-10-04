package ru.meditron.routing.domain;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.junit.jupiter.api.Test;
import ru.meditron.routing.dto.MlResultRequest;
import static org.junit.jupiter.api.Assertions.*;

class PersonNameTest {
    @Test void explicitPartsWinOverFullName() {
        var name = PersonName.resolve("Устаревшее ФИО", "Белова", "Наталья", "Олеговна");
        assertEquals("Белова Наталья Олеговна", name.fullName());
        assertEquals("Белова Н. О.", name.shortName());
    }
    @Test void middleNameIsOptional() {
        var name = PersonName.resolve("Incorrect Old Name", "Smith", "John", " ");
        assertNull(name.middleName());
        assertEquals("Smith John", name.fullName());
        assertEquals("Smith J.", name.shortName());
    }
    @Test void compoundNamesStayInTheirOwnFields() {
        var name = PersonName.resolve("Old Name", "де ла Крус", "Анна Мария", " ");
        assertEquals("де ла Крус", name.lastName());
        assertEquals("Анна Мария", name.firstName());
        assertEquals("де ла Крус А.", name.shortName());
        assertEquals("Петрова-Водкина А. И.", new PersonName("Петрова-Водкина", "Анна", "Ивановна").shortName());
    }
    @Test void legacyFullNameUsesAtMostThreeParts() {
        var name = PersonName.resolve("  Иванов\tИван\nИванович оглы  ", null, null, null);
        assertEquals(new PersonName("Иванов", "Иван", "Иванович оглы"), name);
    }
    @Test void legacyTwoWordsHaveNoMiddleName() {
        var name = PersonName.resolve("Пациент 001", null, null, null);
        assertEquals(new PersonName("Пациент", "001", null), name);
        assertEquals("Пациент 001", name.fullName());
    }
    @Test void emptyAndPartialNamesDoNotInventMissingParts() {
        assertEquals("", PersonName.resolve("\u00a0 ", null, null, null).fullName());
        assertEquals("", new PersonName(null, null, null).shortName());
        assertEquals(new PersonName(null, "Мадонна", null), PersonName.resolve("Old Full Name", null, "Мадонна", null));
    }
    @Test void whitespaceInsidePartsIsNormalizedWithoutSplitting() {
        var name = new PersonName("  де\u00a0ла   Крус ", " Анна\tМария ", "\n");
        assertEquals("де ла Крус Анна Мария", name.fullName());
        assertNull(name.middleName());
    }
    @Test void existingDatabaseRowsExposeNamesWithoutMigration() {
        var patient = new Patient();
        patient.setFullName("Иванов Иван Иванович");
        assertEquals(new PersonName("Иванов", "Иван", "Иванович"), patient.name());
        assertNull(patient.getLastName());
    }
    @Test void unicodeInitialIsNotHalfASurrogatePair() {
        assertEquals("Smith 𐐀.", new PersonName("Smith", "𐐀bc", null).shortName());
    }
    @Test void missingNewFieldsDoNotChangeLegacyReceiptFingerprint() throws Exception {
        var json = new ObjectMapper().findAndRegisterModules().disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        var oldPatient = json.readTree("""
                {"externalId":"legacy","fullName":"Пациент 001","birthDate":"1990-01-01","sex":"F"}
                """);
        var patient = json.treeToValue(oldPatient, MlResultRequest.PatientPart.class);
        // Fingerprints serialize the DTO. Optional null keys must not appear after upgrade.
        assertEquals(oldPatient, json.valueToTree(patient));
    }
}
