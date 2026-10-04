"""Explicit dictionary phrase baseline; no clinical routing decisions."""

import re
from .contracts import ContractError, STUDY_TYPES
from .attributes import clause_span, local_attributes


def validate_dictionary(items):
    if not isinstance(items, list) or not items:
        raise ContractError("Словарь должен быть непустым JSON-массивом")
    codes = set()
    for item in items:
        if not isinstance(item, dict):
            raise ContractError("Элемент словаря должен быть объектом")
        for key in ("code", "name"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ContractError(f"Словарь: требуется {key}")
        if item["code"] in codes:
            raise ContractError("Словарь: повторяющийся code")
        codes.add(item["code"])
        synonyms, studies = item.get("synonyms"), item.get("studyTypes")
        if not isinstance(synonyms, list) or any(not isinstance(s, str) or not s.strip() for s in synonyms):
            raise ContractError("Словарь: synonyms должен быть массивом непустых строк")
        if not isinstance(studies, list) or not studies or any(not isinstance(s, str) or s not in STUDY_TYPES for s in studies):
            raise ContractError("Словарь: некорректные studyTypes")
    return items


def analyze(text, study_type, dictionary):
    """Match explicit name/synonyms. Offsets refer to the exact outgoing text.

    Only lexical negation and uncertainty in the immediate clause are supported.
    Attributes not established by the phrase are omitted, never invented.
    """
    items = [item for item in validate_dictionary(dictionary) if study_type in item["studyTypes"]]
    if not items:
        raise ContractError("В словаре нет находок для данного studyType")
    findings, rejected, matches = [], [], []
    for item in items:
        phrases = sorted(set([item["name"], *item["synonyms"]]), key=len, reverse=True)
        pattern = re.compile(r"(?<!\w)(?:" + "|".join(
            r"\s+".join(re.escape(word) for word in phrase.split()) for phrase in phrases
        ) + r")(?!\w)", re.IGNORECASE)
        matches.extend((match, item) for match in pattern.finditer(text))
    matches.sort(key=lambda pair: (pair[0].start(), -pair[0].end()))
    for match, item in matches:
        left, right = clause_span(text, match.start(), match.end())
        before, after = text[left:match.start()], text[match.end():right]
        before = re.split(r"\b(?:но|однако)\b", before, flags=re.IGNORECASE)[-1]
        # Replace neighbouring explicit dictionary phrases with markers to
        # recognize coordinated lists: "без кист и узлов", "кист и узлов нет".
        list_before, list_after = text[left:match.start()], text[match.end():right]
        for other, _ in reversed(matches):
            if left <= other.start() and other.end() <= match.start():
                list_before = list_before[:other.start() - left] + "@" + list_before[other.end() - left:]
            elif match.end() <= other.start() and other.end() <= right:
                a, b = other.start() - match.end(), other.end() - match.end()
                list_after = list_after[:a] + "@" + list_after[b:]
        list_before = re.sub(r"(?:@\s*(?:,|и|или)\s*)+$", "", list_before, flags=re.I)
        list_after = re.sub(r"^\s*(?:(?:,|и|или)\s*@\s*)+", " ", list_after, flags=re.I)
        uncertain = bool(re.search(r"(?:нельзя\s+исключить|не\s+исключается|подозрение\s+на|возможно|вероятно)\s*$", before, re.I)
                         or re.search(r"^\s*(?:не\s+исключается|под\s+вопросом)", after, re.I)
                         or text[match.end():match.end() + 2].strip().startswith("?"))
        reason = None
        if not uncertain:
            if (re.search(r"(?:состояние\s+после|после\s+удаления|удалени[ея]|удал[её]н[аоы]?|после\s+операции\s+по\s+поводу)\s*$", before, re.I)
                    or re.match(r"\s+удал[её]н[аоы]?\b", after, re.I)):
                reason = "POST_SURGERY"
            elif (re.search(r"(?:без\s+(?:признаков\s+)?|нет\s+(?:признаков\s+)?|не\s+выявлено\s+)$", list_before, re.I)
                  or re.match(r"\s*(?:(?:справа|слева)\s*)?[:—-]?\s*(?:не\s+(?:выявлен\w*|определя\w*|обнаружен\w*|лоциру\w*|визуализиру\w*)|отсутств\w*|нет)\b", list_after, re.I)):
                reason = "NEGATION"
        # Stop attributes at neighbouring dictionary entities. Overlapping
        # concepts intentionally get no attributes: association is unclear.
        attr_left, attr_right = left, right
        overlap = False
        for other, _ in matches:
            if other is match:
                continue
            if other.end() <= match.start():
                attr_left = max(attr_left, other.end())
            elif other.start() >= match.end():
                attr_right = min(attr_right, other.start())
            else:
                overlap = True
        attrs, spans = ({"reviewReasons": ["overlapping_concepts"]}, []) if overlap else local_attributes(text, match.start(), match.end(), attr_left, attr_right)
        attrs["uncertain"] = uncertain
        if re.search(r"\b(?:в\s+анамнезе|ранее)\b", before, re.I):
            attrs["temporality"] = "historical"
            attrs.setdefault("reviewReasons", []).append("historical_mention")
        if uncertain or attrs.get("temporality") == "historical":
            spans.append((left, right + 1 if text[right:right + 1] == "?" else right))
        if reason:
            rejected.append({"code": item["code"], "evidence": {"text": text[left:right].strip()}, "reason": reason})
        else:
            quote_start = min([match.start()] + [a for a, b in spans])
            quote_end = max([match.end()] + [b for a, b in spans])
            findings.append({
                "code": item["code"],
                "evidence": {"text": text[quote_start:quote_end], "start": quote_start, "end": quote_end},
                "attributes": attrs,
            })
    return findings, rejected
