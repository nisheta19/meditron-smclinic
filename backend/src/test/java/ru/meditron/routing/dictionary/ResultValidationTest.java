package ru.meditron.routing.dictionary;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.*;
import org.springframework.core.io.ClassPathResource;
import ru.meditron.routing.dto.MlResultRequest;
import ru.meditron.routing.service.MlResultValidator;
import ru.meditron.routing.exception.BadRequestException;
import static org.junit.jupiter.api.Assertions.*;

class ResultValidationTest {
    static final ObjectMapper json = new ObjectMapper().findAndRegisterModules();
    static MlResultValidator validator;
    @BeforeAll static void setup() throws Exception {
        var dictionary = new DictionaryService(new ClassPathResource("dictionary/findings-dictionary.yaml"));
        dictionary.load(); validator = new MlResultValidator(dictionary);
    }
    ObjectNode result() throws Exception {
        return (ObjectNode) json.readTree("""
            {"resultId":"validation","status":"DONE","modelVersion":"test","dictionaryVersion":"dict-v2.1",
             "processedAt":"2026-10-04T00:00:00Z",
             "patient":{"externalId":"demo","fullName":"Пациент 001","birthDate":"1990-01-01","sex":"F"},
             "protocol":{"externalId":"protocol","version":1,"studyType":"PELVIS_FEMALE","studyDate":"2026-10-01"},
             "text":"😀 Полип эндометрия","conclusion":"Полип эндометрия","conclusionFound":true,"flags":[],
             "findings":[{"code":"ENDOMETRIAL_POLYP","evidence":{"text":"Полип эндометрия","start":2,"end":18},
                          "attributes":{"sizeMm":8,"uncertain":false},"confidence":0.9,"flags":[]}],"notTriggered":[]}
            """);
    }
    void validate(ObjectNode value) throws Exception { validator.validate(json.treeToValue(value, MlResultRequest.class)); }
    @Test void unicodeOffsetsUseCodePoints() throws Exception {
        validate(result());
    }
    @Test void wrongEvidenceOffsetsRejected() throws Exception {
        var r = result(); ((ObjectNode)r.path("findings").get(0).path("evidence")).put("end", 19);
        assertThrows(BadRequestException.class, () -> validate(r));
    }
    @Test void doneMustHaveFindings() throws Exception {
        var r=result(); r.remove("findings"); assertThrows(BadRequestException.class, () -> validate(r));
    }
    @Test void failedMustHaveError() throws Exception {
        var r=result(); r.put("status","FAILED"); r.putArray("findings"); assertThrows(BadRequestException.class, () -> validate(r));
    }
    @Test void unknownNotTriggeredCodeRejected() throws Exception {
        var r=result(); r.putArray("findings");
        r.putArray("notTriggered").addObject().put("code","UNKNOWN").put("reason","NEGATION")
            .putObject("evidence").put("text","Полип");
        assertThrows(BadRequestException.class, () -> validate(r));
    }
    @Test void backendFlagCannotBeSetByMl() throws Exception {
        var r=result(); r.putArray("findings"); r.putArray("flags").addObject().put("code","MINOR");
        assertThrows(BadRequestException.class, () -> validate(r));
    }
    @Test void wrongDictionaryVersionRejected() throws Exception {
        var r=result(); r.put("dictionaryVersion","old"); assertThrows(BadRequestException.class, () -> validate(r));
    }
    @Test void birthAfterStudyRejected() throws Exception {
        var r=result(); ((ObjectNode)r.get("patient")).put("birthDate","2027-01-01");
        assertThrows(BadRequestException.class, () -> validate(r));
    }
}
