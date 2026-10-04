"""Split protocol text at explicit section headings, without discarding text."""

import re

# Longer alternatives come first so that a heading is not partially consumed.
# New templates can extend this list without changing metadata extraction.
HEADINGS = {
    "description": r"Описание(?:[^\S\r\n]+(?:исследования|УЗИ))?|Результаты[^\S\r\n]+исследования",
    "conclusion": r"(?:УЗ[ -]?)?Заключение(?:[^\S\r\n]+(?:исследования|врача|УЗИ))?",
    "recommendations": r"Рекомендации(?:[^\S\r\n]+врача)?|Рекомендовано|Рекомендована|Рек-но",
    "diagnosis": r"Диагноз",
    "complaints": r"Жалобы(?:[^\S\r\n]+со[^\S\r\n]+слов[^\S\r\n]+пациента)?",
    "history": r"(?:(?:Клинический|Данные)[^\S\r\n]+)?Анамнез(?:а|[^\S\r\n]+(?:заболевания|жизни))?",
    "ordered_services": r"Назначенные[^\S\r\n]+услуги",
    "laboratory_tests": r"Лабораторная[^\S\r\n]+диагностика",
    "prescriptions": r"Назначения",
    "additional": r"Дополнительно",
    "note": r"Примечание",
    "signature": r"Подпись[^\S\r\n]+врача",
}
SPACE = r"[^\S\r\n]"
PATTERN = re.compile(
    r"(?<!\w)(?:" + "|".join(
        # A colon permits inline headings. Without a colon, require a whole
        # heading line: 'Данное заключение не является диагнозом' is prose.
        rf"(?P<{name}>(?:{pattern})){SPACE}*:"
        for name, pattern in HEADINGS.items()
    ) + r")|^" + SPACE + r"*(?:" + "|".join(
        rf"(?P<line_{name}>(?:{pattern}))" for name, pattern in HEADINGS.items()
    ) + r")" + SPACE + r"*\r?$",
    re.IGNORECASE | re.MULTILINE,
)


def split_sections(text: str) -> list[dict]:
    """Return ordered sections; heading + body spans partition the entire text.

    The source headings are authoritative, even when a template places the
    whole examination under 'Заключение'. Repeated sections remain separate.
    Unrecognized headings stay in the body instead of triggering guesses.
    """
    matches = list(PATTERN.finditer(text))
    if not matches:
        return [{"name": "unsectioned", "title": None, "text": text}] if text else []
    sections = []
    if matches[0].start():
        sections.append({"name": "unsectioned", "title": None,
                         "text": text[:matches[0].start()]})
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append({
            "name": match.lastgroup.removeprefix("line_"),
            "title": match[0],
            "text": text[match.end():end],
        })
    return sections
