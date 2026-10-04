package ru.meditron.routing.dictionary;

import ru.meditron.routing.domain.Sex;
import ru.meditron.routing.domain.StudyType;

/**
 * Данные пациента и протокола, на которые могут ссылаться правила словаря:
 * patient.age, patient.sex (F | M), protocol.studyType.
 */
public record RuleContext(Integer age, Sex sex, StudyType studyType) {

    public static final String PATIENT_AGE = "patient.age";
    public static final String PATIENT_SEX = "patient.sex";
    public static final String PROTOCOL_STUDY_TYPE = "protocol.studyType";

    public boolean isContextAttr(String attr) {
        return attr.startsWith("patient.") || attr.startsWith("protocol.");
    }

    /** Значение атрибута контекста или null, если его нет / атрибут неизвестен. */
    public Object value(String attr) {
        return switch (attr) {
            case PATIENT_AGE -> age;
            case PATIENT_SEX -> sex == null ? null : sex.name();
            case PROTOCOL_STUDY_TYPE -> studyType == null ? null : studyType.name();
            default -> null;
        };
    }
}
