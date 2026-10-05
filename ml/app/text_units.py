"""Recover logical lines without changing the source or its output offsets.

DOCX paragraphs and hard line breaks may split a sentence. Join continuations
before entity/attribute extraction, retaining anatomy labels and new statements.
"""
import re

FIELD = re.compile(r'^[\w\s()/—–-]{1,75}:', re.U)
CONTINUATION = re.compile(
    r'^(?:не\b|нет\b|без\b|размер\w*\b|диаметр\w*\b|составля\w*\b|'
    r'мм\b|см\b|мл\b|%|на\s*\d|[×хx*—–-]\s*\d)', re.I)
OPEN_END = re.compile(r'(?:[,(/—–-]|\b(?:в|во|на|из|для|от|до|по|с|со|и|или|не|за|без)|по\s+типу)\s*$', re.I)
ANATOMY_HEADING = re.compile(
    r'^(?:(?:ПРАВАЯ|ЛЕВАЯ|ПРАВЫЙ|ЛЕВЫЙ)\s+)?(?:МОЛОЧНАЯ\s+ЖЕЛЕЗА|ДОЛЯ|ПОЧКА|ЯИЧНИК|'
    r'ЛИМФОУЗЛЫ|МАТКА|ШЕЙКА\s+МАТКИ|ЭНДОМЕТРИЙ|ПЕЧЕНЬ|ЖЕЛЧНЫЙ\s+ПУЗЫРЬ)\s*:?$')
OPEN_ADJECTIVE = re.compile(r'\b[А-ЯЁ]+(?:АЯ|ЯЯ|ЫЙ|ИЙ|ОЙ|УЮ|ЮЮ|ОГО|ЕГО|ЫМИ|ИМИ|ЫХ|ИХ|ОЕ|ЕЕ|ЫЕ|ИЕ)\s*$')
OPEN_NOUN = re.compile(r'\b(?:УЗЕЛ|КОНКРЕМЕНТ|КИСТА|ПОЛИП|ГИПЕРПЛАЗИЯ|ОБРАЗОВАНИЕ|ОЧАГ|ТРОМБОЗ)\s*$')
GENITIVE_START = re.compile(r'^(?:[А-ЯЁ]+(?:ОЙ|ОГО|ЕГО|ЫХ|ИХ)|ЭНДОМЕТРИЯ|МИОМЕТРИЯ|ШЕЙКИ|ТЕЛА)\b')


def logical_lines(text):
    lines = []
    for source in text.splitlines():
        line = ' '.join(source.split())
        if not line:
            continue
        previous = lines[-1] if lines else ''
        # A labelled field starts a new unit even if its preceding field has no
        # full stop. Headings/section boundaries are resolved before this call.
        next_field = bool(FIELD.match(line)) and not re.match(
            r'^(?:\w+\s+){0,3}контурами\s*:',line,re.I)
        # A hard wrap may bisect the field name itself: "Шейка\nматки:".
        # This is one anatomical heading, not a new uterus field.
        if re.search(r'\bшейка\s*$',previous,re.I) and re.match(r'^матки\s*:',line,re.I):
            next_field=False
        terminated = previous.endswith(('.', '!', '?', ';', ':'))
        continuing = line[:1].islower() or line[:1].isdigit() or CONTINUATION.match(line)
        # A vessel acronym can start the continuation of a mixed-case diagnosis.
        continuing = continuing or (re.search(r'\b(?:тромбофлебит|тромбоз|стеноз|ствол\w*|вен[аы]|сегмент\w*)\s*$',previous,re.I)
                                    and re.match(r'^(?:БПВ|МПВ|ПДПВ|СФС|СПС|ПБА|ОБА|ГБА|ОБВ|БВ|ГБВ|ПкВ|ЗББВ|ПББВ|МБВ)\b',line,re.I))
        # Categories are frequently wrapped after a side or organ name.
        continuing = continuing or re.match(r'^(?:[BВ]I|[OО]|EU\s*[-–]?\s*TI|ACR\s*TI|TI)\s*[-–]?\s*RADS\b',line,re.I)
        # Uppercase templates carry no sentence-case cue. A terminal adjective
        # needs its following noun; arbitrary uppercase fields must stay apart.
        if previous.isupper() and line.isupper() and not ANATOMY_HEADING.fullmatch(line):
            continuing = continuing or OPEN_ADJECTIVE.search(previous) or (
                OPEN_NOUN.search(previous) and GENITIVE_START.match(line))
            # All-caps exports remove the sentence-case signal entirely. Keep
            # their sentence together until punctuation or an explicit field.
            # A completed negative field remains a separate assertion.
            closed_negative = re.search(r'\b(?:НЕТ|НЕ\s+(?:ВЫЯВЛЕН\w*|ОБНАРУЖЕН\w*|ОПРЕДЕЛЯ\w*|РАСШИРЕН\w*))\s*$', previous)
            if not ANATOMY_HEADING.fullmatch(previous) and not closed_negative:
                continuing = True
        # Parentheses may contain a morphology, unit or differential diagnosis;
        # their hard line break is not a new anatomical field.
        continuing = continuing or line.startswith('(') or previous.count('(') > previous.count(')')
        if previous and not next_field and not terminated and (continuing or OPEN_END.search(previous)):
            lines[-1] += ' ' + line
        else:
            lines.append(line)
    return lines
