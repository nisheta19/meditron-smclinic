"""Turn one validated MIS event into one backend result."""

import base64
import binascii
import tempfile
import hashlib
import json
from pathlib import Path

from .contracts import ContractError, envelope, failed, validate_event
from .clinical import analyze_protocol
from .parser import DocumentError, extract_text, parse_text
from .dictionary import normalize_dictionary, uses_v2_contract
from .validation import validate_for_dictionary

MAX_FILE_BYTES = 20 * 1024 * 1024


def process_event(event, dictionary_provider):
    validate_event(event)
    result = envelope(event)
    if event["eventType"] == "PROTOCOL_ANNULLED":
        result["status"] = "ANNULLED"
        return result
    if Path(event["fileName"]).suffix.lower() != ".docx":
        return failed(result, "UNSUPPORTED_FORMAT", "Поддерживаются только DOCX без обработки изображений")
    try:
        if len(event["contentBase64"]) > (MAX_FILE_BYTES + 2) // 3 * 4:
            raise DocumentError("Файл превышает 20 МБ")
        content = base64.b64decode(event["contentBase64"], validate=True)
        if not content or len(content) > MAX_FILE_BYTES:
            raise DocumentError("Пустой или слишком большой файл")
        # Never use a user-supplied fileName as a filesystem destination.
        with tempfile.TemporaryDirectory(prefix="meditron-ml-") as tmp:
            path = Path(tmp) / "protocol.docx"
            path.write_bytes(content)
            raw = extract_text(path)
            parsed = parse_text(raw)
    except (DocumentError, binascii.Error, ValueError) as exc:
        return failed(result, "UNREADABLE_FILE", "Не удалось извлечь текст DOCX")
    result["text"] = parsed["full_text"]
    conclusions = [s["text"] for s in parsed["sections"] if s["name"] == "conclusion"]
    result["conclusion"] = " ".join(s for s in conclusions if s)
    result["conclusionFound"] = bool(result["conclusion"].strip())
    try:
        dictionary = dictionary_provider()
        if not any(event["protocol"]["studyType"] in i["studyTypes"] for i in normalize_dictionary(dictionary)):
            raise ContractError("Отсутствует тип исследования")
    except (ContractError, OSError, ValueError):
        return failed(result, "DICTIONARY_UNAVAILABLE", "Нет корректного словаря для данного типа исследования")
    try:
        findings, rejected = analyze_protocol(parsed, raw, event["protocol"]["studyType"], dictionary, event)
        digest = hashlib.sha256(json.dumps(dictionary, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
        version = dictionary.get("version", "custom") if isinstance(dictionary, dict) else "custom"
        result["modelVersion"] += "+" + str(version) + "-" + digest
        candidate = dict(result,findings=findings,notTriggered=rejected,error=None)
        candidate['dictionaryVersion'] = str(version)
        if uses_v2_contract(dictionary):
            from .clinical_v2 import protocol_flags
            candidate['flags'] = protocol_flags(parsed)
        validate_for_dictionary(candidate,dictionary)
    except Exception:
        # An extraction/validation failure is never reported as a normal protocol.
        # Do not leak the clinical text in an exception message.
        return failed(result, "ANALYSIS_ERROR", "Не удалось получить корректные факты; требуется проверка обработки")
    result.update(candidate)
    return result
