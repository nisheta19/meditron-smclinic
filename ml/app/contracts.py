"""MIS input validation and backend envelope. No patient metadata is inferred."""

from copy import deepcopy
from datetime import date, datetime, timezone
import re
import json
from uuid import NAMESPACE_URL, uuid5

STUDY_TYPES = {"PELVIS_FEMALE", "ABDOMEN", "BREAST", "THYROID", "PROSTATE", "LOWER_LIMB_VESSELS", "KIDNEY", "SOFT_TISSUE"}
EVENT_TYPES = {"PROTOCOL_SIGNED", "PROTOCOL_CORRECTED", "PROTOCOL_ANNULLED"}
MODEL_VERSION = "dict-v2.1-extractor-8"


class ContractError(ValueError):
    pass


def required_string(obj, field):
    value = obj.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field}: требуется непустая строка")
    return value


def validate_date(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ContractError(f"{field}: требуется YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{field}: несуществующая дата") from exc


def validate_event(event):
    if not isinstance(event, dict):
        raise ContractError("Событие должно быть JSON-объектом")
    try:
        json.dumps(event,allow_nan=False)
    except (ValueError,TypeError) as exc:
        raise ContractError("Событие содержит недопустимое значение JSON") from exc
    required_string(event, "eventId")
    if not isinstance(event.get("eventType"), str) or event["eventType"] not in EVENT_TYPES:
        raise ContractError("eventType: ожидается PROTOCOL_SIGNED, PROTOCOL_CORRECTED или PROTOCOL_ANNULLED")
    for key in ("patient", "protocol"):
        if not isinstance(event.get(key), dict):
            raise ContractError(f"{key}: требуется объект")
        required_string(event[key], "externalId")
    patient, protocol = event["patient"], event["protocol"]
    required_string(patient, "fullName")
    for field in ("lastName", "firstName", "middleName"):
        if patient.get(field) is not None and not isinstance(patient[field], str):
            raise ContractError(f"patient.{field}: требуется строка или null")
    validate_date(patient.get("birthDate"), "patient.birthDate")
    if patient.get("sex") not in ("F", "M"):
        raise ContractError("patient.sex: ожидается F или M")
    if type(protocol.get("version")) is not int or not 1 <= protocol["version"] <= 2**63-1:
        raise ContractError("protocol.version: требуется положительное целое число до 2^63−1")
    if not isinstance(protocol.get("studyType"), str) or protocol["studyType"] not in STUDY_TYPES:
        raise ContractError("protocol.studyType: неизвестный тип исследования")
    validate_date(protocol.get("studyDate"), "protocol.studyDate")
    if event["eventType"] != "PROTOCOL_ANNULLED":
        required_string(event, "fileName")
        required_string(event, "contentBase64")


def envelope(event):
    return {
        "resultId": str(uuid5(NAMESPACE_URL, "meditron-mis-event:" + event["eventId"])),
        "status": "DONE",
        "modelVersion": MODEL_VERSION,
        "processedAt": datetime.now(timezone.utc).isoformat(),
        "patient": deepcopy(event["patient"]),
        "protocol": deepcopy(event["protocol"]),
    }


def failed(result, code, message):
    result.update(status="FAILED", error={"code": code, "message": message})
    return result


def validate_result(result):
    if not isinstance(result, dict):
        raise ContractError("Результат должен быть объектом")
    # Reuse metadata validation without requiring a file for an outgoing result.
    validate_event({"eventId": required_string(result, "resultId"), "eventType": "PROTOCOL_ANNULLED",
                    "patient": result.get("patient"), "protocol": result.get("protocol")})
    required_string(result, "modelVersion")
    try:
        timestamp = datetime.fromisoformat(required_string(result, "processedAt").replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError()
    except ValueError as exc:
        raise ContractError("processedAt: требуется ISO datetime с часовым поясом") from exc
    if result.get("status") not in ("DONE", "FAILED", "ANNULLED"):
        raise ContractError("Некорректный status")
    def validate_flags(value):
        allowed={'DISCREPANCY','INCOMPLETE','NO_CONCLUSION','PREP_VIOLATED','OUTDATED_TERM','INCORRECT_TERM','TEMPLATE_NORM'}
        if not isinstance(value,list) or any(not isinstance(f,dict) or f.get('code') not in allowed or ('note' in f and not isinstance(f['note'],str)) for f in value):
            raise ContractError('flags: требуется массив флагов ML {code, note?}')
        if len({f['code'] for f in value})!=len(value):raise ContractError('Повторяющийся флаг')
    if 'flags' in result:validate_flags(result['flags'])
    if result.get('status')=='DONE' and str(result.get('dictionaryVersion','')).startswith('dict-v2') and 'flags' not in result:
        raise ContractError('DONE v2 требует flags')
    if "text" in result and not isinstance(result["text"], str):
        raise ContractError("text должен быть строкой")
    if result["status"] == "FAILED":
        if not isinstance(result.get("error"), dict):
            raise ContractError("FAILED требует error")
        required_string(result["error"], "code")
        required_string(result["error"], "message")
    if result["status"] == "ANNULLED" and result.get("findings"):
        raise ContractError("ANNULLED не должен содержать находки")
    if result["status"] == "DONE":
        if not isinstance(result.get("conclusion"), str) or type(result.get("conclusionFound")) is not bool:
            raise ContractError("DONE требует conclusion и conclusionFound")
        if not isinstance(result.get("findings"), list):
            raise ContractError("DONE требует массив findings")
    for field in ("findings", "notTriggered"):
        entries = result.get(field, [])
        if not isinstance(entries, list):
            raise ContractError(f"{field}: требуется массив")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("evidence"), dict):
                raise ContractError("Находка требует evidence")
            required_string(entry, "code")
            if 'flags' in entry:validate_flags(entry['flags'])
            evidence = entry["evidence"]
            quote = required_string(evidence, "text")
            if "text" in result:
                if field == "findings":
                    start, end = evidence.get("start"), evidence.get("end")
                    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(result["text"])
                            or result["text"][start:end] != quote):
                        raise ContractError("evidence.start/end не соответствуют text")
                elif quote not in result["text"]:
                    raise ContractError("Цитата notTriggered отсутствует в text")
            if field == "notTriggered" and entry.get("reason") not in ("NEGATION", "NORMAL", "POST_SURGERY"):
                raise ContractError("Некорректная причина notTriggered")
            if "confidence" in entry and (type(entry["confidence"]) not in (int, float)
                    or not 0 <= entry["confidence"] <= 1):
                raise ContractError("confidence должен быть числом 0–1")
            if "attributes" in entry and not isinstance(entry["attributes"], dict):
                raise ContractError("attributes должен быть объектом")
