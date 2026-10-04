"""Conservative local attribute extraction with source spans, no thresholds."""
import re
import math

BOUNDARY = re.compile(r"(?<!\d)\.(?!\d)|[;!?\n]|(?<=\d)\.(?!\d)")
NUMBER = r"\d+(?:[.,]\d+)?"
SIZE = re.compile(rf"(?<![\w.,+−–-])({NUMBER}(?:\s*[xх×*]\s*{NUMBER}){{0,2}})\s*(мм|см)(?![\w²³^])", re.I)
CATEGORY = re.compile(r"(?<!\w)(EU\s*[-–]?\s*TI|BI|TI|O)\s*[-–]?\s*RADS\s*[:=-]?\s*([0-6](?:[abcABCабвАБВ])?)(?!\w)", re.I)
ORGAN = re.compile(r"\b(?:желез[аыу]|матк[аиу]|яичник\w*|пузыр[ья]\w*|дол[яию]|лимфоуз\w*)\b", re.I)
OTHER_ENTITY = re.compile(r"\b(?:узел|узлы|кист\w*|образовани\w*|полип\w*|конкремент\w*|миом\w*)\b", re.I)


def clause_span(text, start, end):
    left, right = 0, len(text)
    for b in BOUNDARY.finditer(text):
        if b.end() <= start:
            left = b.end()
        elif b.start() >= end:
            right = b.start()
            break
    # Opposing statements must not inherit each other's negation/side.
    for b in re.finditer(r"\b(?:но|однако)\b", text[left:right], re.I):
        a, z = left + b.start(), left + b.end()
        if z <= start:
            return z, right
        if a >= end:
            return left, a
    return left, right


def categories(text):
    values = []
    for m in CATEGORY.finditer(text):
        scale = re.sub(r"[\s–-]+", "", m[1]).upper()
        scale = "EU-TIRADS" if scale == "EUTI" else scale + "-RADS"
        values.append({"value": scale + " " + m[2].upper(), "start": m.start(), "end": m.end(), "text": m[0]})
    return values


def local_attributes(text, start, end, left, right):
    context = text[left:right]
    attrs, spans, reasons = {}, [], []
    sides = list(re.finditer(r"\b(?:справа|слева|прав\w*|лев\w*|двусторонн\w*|обеих)\b", context, re.I))
    values = {"right" if re.match(r"справа|прав", m[0], re.I) else "left" if re.match(r"слева|лев", m[0], re.I) else "both" for m in sides}
    if len(values) == 1:
        attrs["side"] = values.pop()
        spans.extend((left + m.start(), left + m.end()) for m in sides)
    elif values:
        reasons.append("ambiguous_side")
    # Only sizes AFTER the finding, no intervening organ or other finding.
    candidates = list(SIZE.finditer(text, end, right))
    usable = [m for m in candidates if m.start() - end <= 80
              and not ORGAN.search(text[end:m.start()])
              and not OTHER_ENTITY.search(text[end:m.start()])]
    if len(usable) == 1:
        m = usable[0]
        dimensions = [float(n.replace(",", ".")) for n in re.findall(NUMBER, m[1])]
        size = max(dimensions) * (10 if m[2].lower() == "см" else 1)
        if math.isfinite(size) and size > 0:
            attrs["sizeMm"] = round(size, 6)
            spans.append((m.start(), m.end()))
        else:
            reasons.append("invalid_size")
    elif candidates:
        reasons.append("ambiguous_size")
    cats = categories(context)
    if len(cats) == 1:
        attrs["category"] = cats[0]["value"]
        spans.append((left + cats[0]["start"], left + cats[0]["end"]))
    elif cats:
        reasons.append("ambiguous_category")
    if reasons:
        attrs["reviewReasons"] = reasons
    return attrs, spans
