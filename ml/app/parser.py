"""Read DOCX XML locally and extract explicitly labelled protocol metadata."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from .sections import split_sections

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_XML_BYTES = 32 * 1024 * 1024
MONTHS = dict(zip(
    "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(),
    range(1, 13),
))
LABEL = re.compile(
    r"(?<!\w)(Подпись\s+врача|Ф\.?\s*И\.?\s*О\.?\s+врача|"
    r"Врач|Дата\s+(?:осмотра|при[её]ма|выполнения|исследования|рождения)|"
    r"Возраст(?:\s+пациента|\s+на\s+момент\s+осмотра)?|"
    r"Время(?:\s+выполнения)?|Пациент|ФИО\s+пациента|Пол|"
    r"Номер\s+карты|Организация|Телефон|Адрес)\s*:",
    re.IGNORECASE,
)
NAME = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
PATRONYMIC = re.compile(r"(?:ович|евич|ич|овна|евна|ична)$", re.IGNORECASE)


class DocumentError(ValueError):
    """Invalid or unsupported input document."""


def extract_text(path: str | Path) -> str:
    """Read body, tables and header/footer paragraphs; never access external links.

    Word runs are concatenated without adding spaces inside words. Paragraphs,
    line breaks and table-cell paragraphs retain textual boundaries. Images are
    ignored. Tracked deletions are ignored; current inserted text is included.
    """
    path = Path(path)
    if path.suffix.lower() != ".docx":
        raise DocumentError("Поддерживаются только файлы .docx")
    try:
        with ZipFile(path) as archive:
            if "word/document.xml" not in archive.namelist():
                raise DocumentError("В DOCX отсутствует основной документ")
            parts = ["word/document.xml"] + sorted(
                n for n in archive.namelist()
                if re.fullmatch(r"word/(?:header|footer)\d+\.xml", n)
            )
            if sum(archive.getinfo(n).file_size for n in parts) > MAX_XML_BYTES:
                raise DocumentError("Текстовая часть DOCX превышает 32 МБ")
            blocks = []
            for part in parts:
                xml = archive.read(part)
                markup = xml.replace(b"\x00",b"").upper()
                if b"<!DOCTYPE" in markup or b"<!ENTITY" in markup:
                    raise DocumentError("XML с DTD или сущностями не поддерживается")
                root = ET.fromstring(xml)

                pending=[(root,False)]
                while pending:
                    node,closing=pending.pop()
                    if closing:
                        if node.tag in {W+"p",W+"tc"}: blocks.append("\n")
                        continue
                    if node.tag == W + "del":
                        continue
                    if node.tag == W + "t":
                        blocks.append(node.text or "")
                    elif node.tag in {W + "tab", W + "br", W + "cr"}:
                        blocks.append("\n" if node.tag != W + "tab" else " ")
                    else:
                        pending.append((node,True))
                        pending.extend((child,False) for child in reversed(node))
                blocks.append("\n")
    except DocumentError:
        raise
    except (OSError, BadZipFile, ET.ParseError, RuntimeError, KeyError, NotImplementedError) as exc:
        raise DocumentError("Не удалось прочитать DOCX; проверьте путь и формат файла") from exc
    text = "".join(blocks)
    if not text.strip():
        raise DocumentError("В документе нет доступного текста")
    return text


def _fields(text: str) -> dict[str, list[str]]:
    # Preserve paragraph boundaries until after matching field labels.
    text = text.replace("\xa0", " ").replace("\u202f", " ")
    matches = list(LABEL.finditer(text))
    fields: dict[str, list[str]] = {}
    for i, match in enumerate(matches):
        key = " ".join(match[1].lower().replace("ё", "е").split())
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[match.end():end].strip()
        fields.setdefault(key, []).append(value)
    return fields


def _date(value: str) -> date | None:
    value = " ".join(value.lower().split())
    match = re.match(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)", value)
    if match:
        day, month, year = map(int, match.groups())
    else:
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})(?!\d)", value)
        if match:
            year, month, day = map(int, match.groups())
        else:
            match = re.match(r"(\d{1,2})\s+([а-я]+)\s+(\d{4})(?!\d)", value)
            if not match or match[2] not in MONTHS:
                return None
            day, month, year = int(match[1]), MONTHS[match[2]], int(match[3])
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _unique(values):
    values = set(values)
    return next(iter(values)) if len(values) == 1 else None


def _name(value: str) -> tuple[str | None, str | None]:
    # Take only the first nonempty field line, not recommendations elsewhere.
    line = next((line.strip() for line in value.splitlines() if line.strip()), "")
    prefix = re.match(rf"^({NAME})(?:\s+({NAME}))?(?:\s+({NAME}))?", line)
    if not prefix:
        return None, None
    tokens = [token for token in prefix.groups() if token]
    if len(tokens) >= 2 and PATRONYMIC.search(tokens[1]):
        # Given name + patronymic; a surname is only accepted as a third name
        # if it occupies the remainder of this line.
        surname = tokens[2] if len(tokens) == 3 and prefix.end() == len(line) else None
        return tokens[0], surname
    if len(tokens) == 3 and PATRONYMIC.search(tokens[2]):
        return tokens[1], tokens[0]  # Surname + given name + patronymic.
    # Initials do not establish a full given name.
    if re.fullmatch(rf"{NAME}\s+[А-ЯЁ]\.\s*(?:[А-ЯЁ]\.)?", line):
        return None, tokens[0]
    if re.fullmatch(NAME, line):
        return None, None  # A single word could be a surname or given name.
    return None, None


def parse_text(text: str) -> dict:
    fields = _fields(text)
    names = []
    for key, values in fields.items():
        if key in {"врач", "подпись врача"} or key.endswith(" врача"):
            names.extend(_name(value) for value in values)
    first_name = _unique(first for first, _ in names if first)
    # Do not combine a signature for another doctor with the header name.
    first_names = {first for first, _ in names if first}
    last_name = None if len(first_names) > 1 else _unique(last for _, last in names if last)

    exam_values = [value for key, values in fields.items()
                   if key in {"дата осмотра", "дата приема", "дата выполнения", "дата исследования"}
                   for value in values]
    exam_date = _unique(_date(value) for value in exam_values)
    age_values = [value for key, values in fields.items()
                  if key.startswith("возраст") for value in values]
    if age_values:
        ages = []
        for value in age_values:
            match = re.match(r"(\d{1,3})(?!\d)(?:\s*(?:лет|года?|\n|$))", value)
            ages.append(int(match[1]) if match and int(match[1]) <= 130 else None)
        age = _unique(ages)
    else:
        birth_date = _unique(_date(value) for value in fields.get("дата рождения", []))
        age = None
        if birth_date and exam_date and birth_date <= exam_date:
            computed = exam_date.year - birth_date.year - (
                (exam_date.month, exam_date.day) < (birth_date.month, birth_date.day)
            )
            if 0 <= computed <= 130:
                age = computed
    # Keep paragraph boundaries for extraction; flatten whitespace only in output.
    sections = [
        {
            "name": section["name"],
            "title": " ".join(section["title"].split()) if section["title"] is not None else None,
            "text": " ".join(section["text"].split()),
        }
        for section in split_sections(text)
        if section["title"] is not None or section["text"].strip()
    ]
    return {
        "doctor_first_name": first_name,
        "doctor_last_name": last_name,
        "patient_age": age,
        "examination_date": exam_date.isoformat() if exam_date else None,
        "full_text": " ".join(text.split()),
        "sections": sections,
    }


def parse_docx(path: str | Path) -> dict:
    return parse_text(extract_text(path))
