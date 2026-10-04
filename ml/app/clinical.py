"""Fact extraction for the supplied dict-v1-ml. No backend routing rules run here."""
from dataclasses import dataclass
import re
from .attributes import BOUNDARY
from .dictionary import normalize_dictionary, uses_v2_contract
from .findings import analyze as literal_analyze
from .sections import split_sections
from .extensions import extract_declared
from .text_units import logical_lines

NUM = r"\d+(?:[.,]\d+)?"
MEASURE = re.compile(rf"(?<![\d−-])({NUM}(?:\s*(?:[xх×*–-]|\bна\b)\s*{NUM}){{0,2}})\s*(мм|см)(?![\w³²^])", re.I)
CATEGORY = re.compile(r"(?<!\w)(EU\s*[-–]?\s*[TТ]I\s*[-–]?\s*RADS|[TТ]I\s*[-–]?\s*RADS|[BВ]I\s*[-–]?\s*RADS|BIRADS|BR|[OО]\s*[-–]?\s*RADS)\s*[-:=]?\s*([0-6]|IV|III|II|VI|V|I)([abcабв])?(?!\w)", re.I)
NEG = re.compile(r"\b(?:не\s+(?:выяв\w*|определ\w*|в[уы]?изуализ\w*|лоцир\w*|обнаруж\w*|получ\w*)|без\s+признак\w*|отсутств\w*|нет)\b", re.I)
UNCERTAIN = re.compile(r"\?|нельзя\s+исключить|не\s+исключается|вероятн\w*|возможно|предположительн\w*|под\s+(?:вопросом|подозрением)|подозр\w*\s+на", re.I)
SURGERY = re.compile(r"после\s+(?:удаления|операции|резекции|холецистэктомии)|состояние\s+после|\bудал[её]н[аоы]?\b|\bудалени[ея]\b|миомэктомия|кистэктомия", re.I)
EXCLUDED_SECTIONS = {"history", "recommendations", "prescriptions", "signature", "ordered_services", "laboratory_tests"}


@dataclass
class Block:
    text: str
    start: int
    end: int
    section: str
    side: str | None = None
    organ: str | None = None


def side_of(text):
    if re.search(r"с\s+обеих\s+сторон|обеих|билатерально", text, re.I):
        return "both"
    if re.search(r"\bдвусторонн",text,re.I): return "both"
    left = bool(re.search(r"\b(?:слева|левосторонн\w*|лев(?:ая|ой|ую|ое|ого|ом|ый|ые|ых)|s(?!\s*[-=]?\s*\d))\b", text, re.I))
    right = bool(re.search(r"\b(?:справа|правосторонн\w*|прав(?:ая|ой|ую|ое|ого|ом|ый|ые|ых)|d(?!\s*[-=]?\s*\d))\b", text, re.I))
    return "both" if left and right else "left" if left else "right" if right else None


def clause_boundaries(line):
    """Keep clinical abbreviations and measurement lists inside their clause."""
    boundaries=[]
    for m in BOUNDARY.finditer(line):
        if m[0]=='.' and re.search(r'(?:\b(?:мол(?:очн)?|разм|диам|остаточ|до)|куб|см)$',line[:m.start()],re.I):continue
        if m[0]==';' and re.match(r'\s*\d',line[m.end():]):continue
        boundaries.append(m)
    boundaries.extend(re.finditer(r'\b(?:но|однако)\b|,\s*(?=рядом\s+с\s+яичником)|,\s*(?=(?:узел|киста|полип)\s+\d)',line,re.I))
    # Coordinated diagnoses keep separate anatomy and uncertainty scopes even
    # when Word places the entire conclusion in one paragraph.
    boundaries.extend(re.finditer(
        r',\s*(?=(?:(?:\w+(?:ой|ого|ых|ые|ая)|форм[аы])\s+){0,4}'
        r'(?:эндометриоз\w*|эндометри[йя]\b|кист[аы]\b|полип\w*|миом\w*|аденомиоз\w*))', line, re.I))
    return sorted((m for m in boundaries if not (m[0].startswith(',') and
        re.fullmatch(r'\s*(?:вероятн\w*|возможно|предположительн\w*)\s*',line[:m.start()],re.I))),key=lambda m:m.start())


def blocks(raw, full_text):
    result, cursor = [], 0
    for section in split_sections(raw):
        inherited, organ = None, None
        for raw_line in logical_lines(section["text"]):
            line = " ".join(raw_line.split())
            if not line:
                continue
            start = full_text.find(line, cursor)
            if start < 0:
                raise ValueError("Cannot align source paragraphs")
            cursor = start + len(line)
            # Preserve decimal points; split opposite claims as well.
            boundaries = clause_boundaries(line)
            last = 0
            pieces = []
            for boundary in sorted(boundaries, key=lambda m: m.start()):
                if boundary.start() < last: continue
                end = boundary.end() if boundary[0] == "?" else boundary.start()
                if line[last:end].strip():
                    a = last + len(line[last:end]) - len(line[last:end].lstrip())
                    z = end - len(line[last:end]) + len(line[last:end].rstrip())
                    piece = line[a:z]
                    pieces.append((piece,a,z))
                last = boundary.end()
            if line[last:].strip():
                a = last + len(line[last:]) - len(line[last:].lstrip())
                z = len(line.rstrip())
                piece = line[a:z]
                pieces.append((piece,a,z))
            for piece,a,z in pieces:
                # Resolve anatomy on each clause, never from a later opposite side.
                previous_organ = organ
                if re.search(r"лимфоуз|лимфатическ\w*\s+уз",piece,re.I): organ="lymph"
                elif re.search(r"желчн\w*\s+пузыр",piece,re.I): organ="gallbladder"
                elif re.search(r"яичник",piece,re.I): organ="ovary"
                elif re.search(r"эндометри|м\s*[-–—]\s*эхо",piece,re.I): organ="endometrium"
                elif re.search(r"поч(?:к[аиуе]|ек|ках|ке)\b",piece,re.I): organ="kidney"
                elif re.search(r"шейк\w*\s+матки|цервикальн\w*\s+канал|эндоцервикс",piece,re.I): organ="cervix"
                elif re.search(r"матк[аи]\b|миометри",piece,re.I): organ="uterus"
                elif re.search(r"переше[еий]к",piece,re.I): organ="isthmus"
                elif re.search(r"щитовидн\w*\s+желез",piece,re.I): organ="study_organ"
                elif re.search(r"предстательн\w*\s+желез",piece,re.I): organ="study_organ"
                elif re.search(r"поджелудочн|селез[её]нк|\bпечень\b|мочев\w*\s+пузыр",piece,re.I): organ="other"
                elif re.search(r"мол(?:очн\w*)?\.?\s*желез|дол[яиюе]\b|предстательн\w*\s+желез",piece,re.I): organ="study_organ"
                if organ != previous_organ: inherited=None
                explicit_side=side_of(piece)
                if explicit_side: inherited=explicit_side
                result.append(Block(piece,start+a,start+z,section["name"],explicit_side or inherited,organ))
    # Word tables often put the label and its value in separate cells/paragraphs.
    merged, i = [], 0
    labels = re.compile(r"^(?:м\s*[-–]\s*эхо|эндометрий|свободная\s+жидкость[^:]*|конкременты|образования|остаточная\s+моча)\s*:?$",re.I)
    while i < len(result):
        b=result[i]
        if labels.match(b.text) and i+1<len(result) and result[i+1].section==b.section:
            nxt=result[i+1]
            if re.match(r"^(?:\d|не\b|нет\b|отсутств|небольш|умеренн|определ|выяв)",nxt.text,re.I):
                merged.append(Block(full_text[b.start:nxt.end],b.start,nxt.end,b.section,b.side,b.organ));i+=2;continue
        merged.append(b);i+=1
    # Line wrapping and adjacent Word cells must not sever a lesion from its size.
    joined=[]
    for b in merged:
        prev=joined[-1] if joined else None
        if prev and prev.section==b.section and prev.organ==b.organ and prev.side==b.side:
            unmeasured=re.search(r'образовани\w*|узел\b|полост\w*',prev.text,re.I) and not dimensions(prev.text)
            continuation=re.match(r'^(?:ровными|неровными|контурами|размер\w*|диаметр\w*|\d)',b.text,re.I)
            if unmeasured and continuation:
                joined[-1]=Block(full_text[prev.start:b.end],prev.start,b.end,b.section,b.side,b.organ)
                continue
        joined.append(b)
    return joined


def phrase_pattern(phrase):
    words = []
    stems = {"полип": "полип", "киста": "кист", "узел": "уз(?:ел|л)", "миома": "миом", "гиперплазия": "гиперплази", "беременность": "беременност", "жидкость": "жидкост", "тромбоз": "тромбоз", "перекрут": "перекрут", "яичник": "яичник", "конкремент": "конкремент", "камень": "кам(?:ень|н)", "грыжа": "грыж", "образование": "образовани"}
    for word in phrase.split():
        low = word.lower()
        root = next((v for k, v in stems.items() if low == k), None)
        if root:
            words.append(root + r"\w*")
        elif re.fullmatch(r"[а-яё]+ие",low):
            words.append(re.escape(low[:-1]) + r"(?:е|я|ю|ем|и)")
        elif re.fullmatch(r"[а-яё]+(?:ый|ий|ой|ая|ое|ые)", low):
            words.append(re.escape(low[:-2]) + r"(?:ый|ий|ой|ого|его|ому|ему|ым|им|ом|ем|ая|яя|ую|юю|ое|ее|ые|ие|ых|их|ыми|ими)")
        else:
            words.append(re.escape(word).replace("ё", "[её]"))
    return r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)"


def expand_lesion_blocks(source,full,study):
    result=[]
    for b in source:
        cuts=[]
        if len(list(CATEGORY.finditer(b.text)))>1:
            cuts.extend(m.start() for m in re.finditer(r',\s*(?=(?:справа|слева)\b)',b.text,re.I))
        lobes=list(re.finditer(r'\bв\s+(?:правой|левой)\s+доле\b',b.text,re.I))
        if len(lobes)>1:cuts.extend(m.start() for m in lobes[1:])
        # Explicit FIGO/type pairs are individual entities even in one sentence.
        if len(re.findall(r'\([0-8]\s*тип',b.text,re.I))>1:
            cuts.extend(m.start() for m in re.finditer(r',\s*(?=(?:в\s+области\s+[^,]+?\s+)?(?:интрамураль|субсерозн|субмукозн|интерстици))',b.text,re.I))
        starts=[0]+sorted(set(cuts));ends=sorted(set(cuts))+[len(b.text)]
        for a,z in zip(starts,ends):
            part=b.text[a:z].strip(' ,')
            if not part:continue
            offset=b.text.find(part,a)
            result.append(Block(part,b.start+offset,b.start+offset+len(part),b.section,side_of(part) or b.side,b.organ))
    return result


def find_categories(block, study=None):
    matches = list(CATEGORY.finditer(block.text))
    found = []
    for i, m in enumerate(matches):
        token = re.sub(r"[\s–-]", "", m[1]).upper().translate(str.maketrans("ТВО","TBO"))
        scale = "tirads" if "TI" in token else "orads" if token.startswith("O") else "birads"
        value = m[2].upper()
        value = int(value) if value.isdigit() else {"I":1,"II":2,"III":3,"IV":4,"V":5,"VI":6}[value]
        a = 0 if i == 0 else m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(block.text)
        part = block.text[a:end].strip()
        offset = block.text.find(part, a)
        attrs = {scale: value}
        if scale == "tirads": attrs["tiradsSystem"] = "EU" if token.startswith("EU") else "UNKNOWN"
        if scale == "birads" and m[3]: attrs["biradsSub"] = m[3].lower().translate(str.maketrans("абв", "abc"))
        found.append((scale, attrs, Block(part, block.start+offset, block.start+offset+len(part), block.section, side_of(part) or block.side, block.organ)))
    if not found:
        scale_match=re.search(r"(?<!\w)(EU\s*[-–]?\s*TIRADS|TI\s*[-–]?\s*RADS|BI\s*[-–]?\s*RADS|O\s*[-–]?\s*RADS)\b",block.text,re.I)
        if scale_match:
            token=re.sub(r"[\s–-]","",scale_match[0]).upper()
            scale="tirads" if "TI" in token else "orads" if token.startswith("O") else "birads"
            for m in re.finditer(r"(справа|слева)\s*[:—-]?\s*([0-6])",block.text[scale_match.end():],re.I):
                attrs={scale:int(m[2])}
                if scale=="tirads": attrs["tiradsSystem"]="EU" if token.startswith("EU") else "UNKNOWN"
                found.append((scale,attrs,Block(block.text,block.start,block.end,block.section,"right" if m[1].lower()=="справа" else "left",block.organ)))
        elif study == "BREAST":
            m=re.search(r"\bкатегори\w*\s*[:—-]?\s*([0-6])([abcабв])?(?!\w)",block.text,re.I)
            if m:
                attrs={"birads":int(m[1])}
                if m[2]: attrs["biradsSub"]=m[2].lower().translate(str.maketrans("абв","abc"))
                found.append(("birads",attrs,block))
    return found


def dimensions(text):
    values = []
    for m in MEASURE.finditer(text):
        norm=list(re.finditer(r"\(\s*(?:N\b|норма\b)",text[:m.start()],re.I))
        if norm and norm[-1].start()>text.rfind(")",0,m.start()): continue
        value = max(float(n.replace(",", ".")) for n in re.findall(NUM, m[1])) * (10 if m[2].lower() == "см" else 1)
        if 0 < value < float("inf"):
            values.append((round(value, 6), m.start(), m.end()))
    return values


def lesion_count(text,infer=True):
    """Explicit counts or enumerated measurements; an axis is not a lesion."""
    number=re.search(r'\b(\d+)\s*(?:узл\w*|кист\w*|образовани\w*|полип\w*|конкремент\w*)',text,re.I)
    if number:return int(number[1])
    words={r'од(?:ин|но|на)':1,r'дв(?:а|е|умя|ух)':2,r'тр(?:и|ех|ёх)':3,r'четыр(?:е|ех|ёх)':4,r'пят(?:ь|и)':5,r'шест(?:ь|и)':6}
    for word,n in words.items():
        if re.search(rf'\b(?:{word})\b',text,re.I):return n
    if re.search(r'\bединичн(?:ое|ый|ая)\b',text,re.I):return 1
    if not infer:return None
    sizes=dimensions(text)
    if len(sizes)>1 and not re.search(r'по\s+ТАУЗИ|по\s+ТВУЗИ|\bот\s+\d[^;]*\bдо\s+\d',text,re.I):return len(sizes)
    # Shared unit: "15 и 25 мм" is a list, "15 х 25 мм" is one lesion.
    if re.search(rf'{NUM}\s+и\s+{NUM}\s*мм',text):return 2
    return None


def measured(text, label):
    m = re.search("(?:" + label + r")", text, re.I)
    tail=text[m.end():m.end()+45] if m else ""
    sizes = dimensions(tail)
    if sizes and re.search(r"\b(?:полип\w*|кист\w*|образовани\w*|узел|холедох)\b",tail[:sizes[0][1]],re.I):
        return None
    return sizes[0][0] if sizes else None


def explicit_bool(text, positive, negative=None):
    if negative and re.search(negative, text, re.I): return False
    if re.search(positive, text, re.I): return True
    return None


def attributes(code, block, match_end=0):
    text = block.text
    attrs = {"uncertain": bool(UNCERTAIN.search(text))}
    if block.side: attrs["side"] = block.side
    # A finding's size must follow its mention; exclude competing organ metrics.
    tail = text[match_end:]
    competing=re.search(r"\b(?:матка|яичник|железа|холедох|лоханка|лимфоузлы|доля)\b",tail,re.I)
    if competing: tail=tail[:competing.start()]
    sizes = dimensions(tail)
    if sizes and not re.search(r"(?:толщин\w*\s+стенк|об[ъь][её]м|размер\w*\s+(?:матки|яичника|железы)|холедох|лоханк)", tail[:sizes[-1][1]], re.I):
        attrs["sizeMm"] = max(s[0] for s in sizes)
    count=lesion_count(text,infer=False) or lesion_count(tail)
    if count: attrs['count']=count
    growth = explicit_bool(text, r"с\s+динамикой\s+роста|увеличение\s+(?:размеров|по\s+сравнению)|в\s+динамике\s+увеличение", r"без\s+(?:отрицательной\s+)?динамики|без\s+признаков\s+роста|стабильн")
    if growth is not None: attrs["growth"] = growth
    if re.search(r"рецидив|повторн\w*\s+полип", text, re.I): attrs["recurrent"] = True
    if code == "UTERINE_FIBROID":
        figo = re.search(r"(?:по\s+)?FIGO\s*[:=-]?\s*([0-8])|тип\s*([0-8])\s*по\s*FIGO|\(\s*([0-8])\s*тип", text, re.I)
        if figo: attrs["figo"] = int(next(v for v in figo.groups() if v))
        else:
            for pattern, value in ((r"субмукозн\w*\s+узел\s+на\s+ножке",0),(r"интрамурально[ -]субмукозн",2),(r"субмукозн|подслизист",1),(r"интрамуральн",4),(r"субсерозн",6)):
                if re.search(pattern, text, re.I): attrs["figo"] = value; break
        attrs["deformsCavity"] = explicit_bool(text, r"деформ\w*\s+полост", r"не\s+деформ\w*\s+полост|полость[^.;]{0,20}не\s+деформ")
        attrs["prolapsing"] = explicit_bool(text, r"рождающ|узел\s+в\s+цервикальном\s+канале")
    if code == "ENDOMETRIAL_HYPERPLASIA":
        attrs["thicknessMm"] = measured(text, r"м\s*[-–—]\s*эхо|эндометри\w*")
    if code == "OVARIAN_LESION":
        for key, pos, neg in (("functional",r"фолликулярн\w*\s+кист|кист\w*\s+ж[её]лтого\s+тела|геморрагическ\w*\s+кист",None),
                              ("solid",r"солидн",r"без\s+солидн"),("papillary",r"папиллярн\w*\s+разрастан|пристеночн\w*\s+включен",r"без\s+папиллярн"),
                              ("septated",r"перегород|многокамерн",r"без\s+перегород")):
            attrs[key] = explicit_bool(text,pos,neg)
    if code in {"GALLBLADDER_POLYP", "OVARIAN_LESION"}:
        attrs["vascularized"] = explicit_bool(text,r"кровоток\s+в\s+образовании|васкуляризован",r"аваскулярн|кровоток[^.;]{0,20}не\s+(?:определ|выяв)")
    if code == "GALLBLADDER_POLYP":
        attrs["sessile"] = explicit_bool(text,r"широк\w*\s+основан",r"на\s+ножке")
    if code in {"GALLSTONES", "KIDNEY_STONES"}:
        attrs["location"] = ("choledoch" if re.search(r"холедох|общ\w*\s+желчн\w*\s+проток", text,re.I) else "gallbladder") if code == "GALLSTONES" else ("ureter" if re.search(r"мочеточник",text,re.I) else "bladder" if re.search(r"мочев\w*\s+пузыр",text,re.I) else "kidney")
        attrs["mobile"] = explicit_bool(text,r"смещаем|подвижн|перемещающ",r"неподвижн|не\s+смещаем")
        if re.search(r"микролит",text,re.I): attrs["uncertain"] = True
        attrs["obstruction"] = explicit_bool(text,r"признаки\s+обструкции|уретерогидронефроз|расширение\s+ЧЛС|ЧЛС\s+расширена",r"без\s+обструкции|ЧЛС\s+не\s+расширена")
    if code == "ACUTE_CHOLECYSTITIS":
        attrs["wallThicknessMm"] = measured(text,r"стенк\w*")
        attrs["pericholecysticFluid"] = explicit_bool(text,r"перипузырн\w*\s+жидкость|паравезикальн\w*\s+инфильтрат")
    if code in {"FREE_FLUID","OVARIAN_LESION","OVARIAN_APOPLEXY","BPH_URINARY_RETENTION"}:
        volume = re.search(rf"({NUM})\s*мл\b",text[match_end:] if code=="FREE_FLUID" else text,re.I)
        if volume:
            key="freeFluidMl" if code=="OVARIAN_APOPLEXY" else "residualUrineMl" if code=="BPH_URINARY_RETENTION" and re.search(r"остаточн\w*\s+моч",text,re.I) else "volumeMl"
            attrs[key] = float(volume[1].replace(",","."))
    if code == "FREE_FLUID":
        for pat, value in ((r"небольш", "небольшое"),(r"умеренн","умеренное"),(r"значительн","значительное"),(r"больш","большое")):
            if re.search(pat,text,re.I): attrs["amount"] = value; break
        for pat, value in ((r"со\s+сгустками|сгустк","со сгустками"),(r"со\s+взвесью","со взвесью"),(r"анэхоген","анэхогенная")):
            if re.search(pat,text,re.I): attrs["echogenic"] = value; break
        for pat, value in ((r"дуглас|позадиматоч|мал\w*\s+таз","малый таз"),(r"брюшн\w*\s+полост","брюшная полость"),(r"межпетель","межпетельно"),(r"подпеч[её]ноч","подпечёночно"),(r"поддиафрагм","поддиафрагмально")):
            if re.search(pat,text,re.I): attrs["location"] = value; break
    if code == "BREAST_LESION":
        attrs["inflammation"] = explicit_bool(text,r"мастит|признаки\s+воспаления",r"без\s+признаков\s+воспаления")
    if code == "ECTOPIC_PREGNANCY":
        for pattern,value in ((r"трубн|маточн\w*\s+труб","tubal"),(r"шеечн|шейк\w*\s+матки","cervical"),(r"беременность\s+в\s+рубце","scar")):
            if re.search(pattern,text,re.I): attrs["location"]=value;break
    if code == "THYROID_NODULE":
        features = [label for pattern,label in ((r"микрокальцин\w*","микрокальцинаты"),(r"выраженно\s+гипоэхоген\w*","выраженно гипоэхогенный"),(r"неровн\w*\s+контур\w*|неч[её]тк\w*\s+контур\w*","неровный / нечёткий контур"),(r"вертикальн\w*\s+ориентац\w*|выше,?\s+чем\s+шире","вертикальная ориентация"),(r"экстратиреоидн\w*\s+распростран\w*","экстратиреоидное распространение")) if any(not negates(text,m.start(),m.end()) for m in re.finditer(pattern,text,re.I))]
        # Explicit absence of suspicious signs is not a positive feature.
        if re.search(r"без\s+(?:признаков\s+)?[^.;]{0,100}(?:микрокальцин|вертикальн)",text,re.I):
            features=[f for f in features if f not in {"микрокальцинаты","вертикальная ориентация"}]
        if features: attrs["suspiciousFeatures"] = features
    if code == "DEEP_VEIN_THROMBOSIS":
        attrs["floating"] = explicit_bool(text,r"флотирующ",r"нефлотирующ|без\s+флотации")
        attrs["occlusive"] = explicit_bool(text,r"\bокклюзивн",r"неокклюзивн")
        vein = re.search(r"\b(?:ОБВ|ПБВ|БПВ|МПВ|подколенн\w*|суральн\w*)\b",text,re.I)
        if vein: attrs["vein"] = vein[0]
        if re.search(r"посттромботическ",text,re.I): attrs["uncertain"] = True
    if code == "ARTERIAL_STENOSIS":
        percentages=[max(float(n.replace(',','.')) for n in re.findall(NUM,m[1])) for m in re.finditer(rf'({NUM}(?:\s*[-–]\s*{NUM})?)\s*%',text)]
        if percentages:attrs['stenosisPct']=max(percentages)
        attrs['occlusion']=explicit_bool(text,r'\bокклюзи\w*',r'без\s+окклюзи\w*|окклюзи\w*\s+не\s+выяв')
    if code == "HERNIA":
        attrs.pop("sizeMm",None)
        attrs["sizeMm"] = measured(text,r"грыжев\w*\s+ворот\w*|дефект\w*\s+апоневроз\w*")
        attrs["reducible"] = explicit_bool(text,r"\bвправим",r"невправим")
        attrs["incarcerated"] = explicit_bool(text,r"ущемл[её]н|признаки\s+ущемления|жидкость\s+в\s+грыжевом\s+мешке|нарушение\s+кровотока\s+в\s+содержимом",r"без\s+признаков\s+ущемления|неущемл")
    if code == "HYDRONEPHROSIS":
        grade = re.search(r"(?:степень\s*([1-4])|([1-4])\s*(?:ст\b|степен))",text,re.I)
        if grade: attrs["grade"] = int(grade[1] or grade[2])
        attrs["pelvisMm"] = measured(text,r"лоханк\w*")
        attrs["ureterDilated"] = explicit_bool(text,r"расширен\w*\s+мочеточник|мочеточник\s+расширен",r"мочеточник\s+не\s+расширен")
    return {k:v for k,v in attrs.items() if v is not None}


EXTRA = {
    "ENDOMETRIAL_POLYP": r"полип\w*\s+эндометри\w*|эндометри\w*\s*\(\s*полип\w*\s*\)|(?:очагов\w*\s+образовани\w*|локальн\w*\s+утолщени\w*|фокальн\w*\s+разрастани\w*)\s+эндометри\w*",
    "ENDOMETRIAL_HYPERPLASIA": r"гиперплази\w*\s+эндометри\w*",
    "UTERINE_FIBROID": r"\bмиом(?:а|ы|у|ой|е)?\b|миоматозн\w*\s+уз\w*|лейомиом\w*|фибромиом\w*|субмукозн\w*\s+уз\w*|подслизист\w*\s+уз\w*",
    "OVARIAN_LESION": r"(?:кист|образовани)\w*(?:\s+\w+){0,3}\s+яичник\w*|эндометриом\w*|параовариальн\w*\s+кист\w*|фолликулярн\w*\s+кист\w*|кист\w*\s+ж[её]лтого\s+тела|геморрагическ\w*\s+кист\w*",
    "BREAST_LESION": r"фиброаденом\w*|\bкист[аы]\b|об[ъь][её]мн\w*\s+образовани\w*|очагов\w*\s+образовани\w*",
    "THYROID_NODULE": r"\bуз(?:ел|лы|лов|ла|лом)\b|узлов\w*\s+образовани\w*",
    "DEEP_VEIN_THROMBOSIS": r"\bтромбоз\w*|\bтромботическ\w*\s+масс\w*|посттромботическ\w*\s+изменени\w*",
    "HYDRONEPHROSIS": r"ЧЛС\s+(?:не\s+)?расширен\w*",
    "VENOUS_INSUFFICIENCY": r"варикозн\w*\s+(?:трансформац|деформац|расширен)\w*|несостоятельност\w*\s+(?:ствола|клапан\w*|БПВ|МПВ)|хроническ\w*\s+заболевани\w*\s+вен",
    "ARTERIAL_STENOSIS": r"\bстеноз\w*|\bстенозирующ\w*|\bокклюзи\w*|атеросклеротическ\w*\s+бляш\w*|\bАСБ\b",
    "BPH_URINARY_RETENTION": r"гиперплази\w*(?:\s+[^.;,]+)?\s+предстательн\w*\s+желез\w*|гиперплази\w*\s*,[^.;]*предстательн\w*\s+желез\w*",
}


def negates(text, start, end):
    # Lexical profiles may match a Russian stem. Scope starts after the whole
    # word, otherwise its ending looks like unrelated text before the cue.
    while end < len(text) and (text[end].isalnum() or text[end]=='_'):end += 1
    before,after=text[:start],text[end:]
    cue=NEG.search(after)
    location_only = cue and re.fullmatch(r"[\s:—–,-]*(?:(?:достоверно|в|на|за|и|с|со|обеих|обоих|обоим|област\w*|проекци\w*|прав\w*|лев\w*|мал\w*|таз\w*|маткой|брюшн\w*|пахов\w*|полост\w*|дол[еяхию]\w*|яичник\w*|молочн\w*|предстательн\w*|желез\w*|почк\w*|почек|желчн\w*|пузыр\w*|просвет\w*|после|микци\w*|мочеиспускани\w*|позадиматочн\w*|пространств\w*|забрюшинн\w*|момент|исследования)\b[\s:—–,-]*)*",after[:cue.start()],re.I)
    claim_negated=cue and re.search(r"(?:данных\s+за|признаков)\s*$",before,re.I)
    return bool(location_only or claim_negated or re.search(r"(?:без\s+(?:признаков\s+)?|нет\s+(?:признаков\s+)?)$",before,re.I)
                or re.match(r"\s*[:—–,-]?\s*(?:(?:справа|слева)\s*)?(?:не\s+(?:выяв\w*|определ\w*|визуализ\w*|лоцир\w*|обнаруж\w*|получ\w*|расширен\w*)|нет\b|отсутств\w*)",after,re.I))


def candidates_for(item, source_blocks, study):
    code = item["code"]
    phrases = [item["name"], *item["synonyms"]]
    pattern = "|".join(phrase_pattern(p) for p in sorted(phrases,key=len,reverse=True))
    if code in EXTRA: pattern += "|" + EXTRA[code]
    regex = re.compile(pattern, re.I)
    suspected = [re.compile(phrase_pattern(p),re.I) for p in item.get("suspectedSynonyms", [])]
    found = []
    for block in source_blocks:
        if block.section in EXCLUDED_SECTIONS:
            continue
        text = block.text
        if re.search(r"гистологическ\w*\s+заключени|морфологи|\bв\s+анамнезе\b",text,re.I):
            continue
        match = regex.search(text)
        if not match:
            if code == "GALLSTONES" and (block.organ == "gallbladder" or block.section == "conclusion"):
                match = re.search(r"\bконкремент\w*|\bЖКБ\b",text,re.I)
            elif code == "GALLBLADDER_POLYP" and block.organ == "gallbladder":
                match = re.search(r"\bполип\w*",text,re.I)
            elif code == "KIDNEY_STONES" and (block.organ == "kidney" or study == "KIDNEY"):
                match = re.search(r"\bконкремент\w*|\bкам(?:ень|ни|ней)\b",text,re.I)
            elif code == "OVARIAN_LESION" and block.organ == "ovary":
                match = re.search(r"\bкист[аы]\b|(?:жидкостн|кистозн|солидн)\w*\s+образовани\w*",text,re.I)
        if code in {"BREAST_LESION","THYROID_NODULE"} and block.organ == "lymph":
            continue
        if code == "THYROID_NODULE" and re.search(r"лимфатическ\w*\s+уз",text,re.I):
            continue
        if code == "GALLSTONES" and (block.organ == "kidney" or re.search(r"конкремент\w*\s+(?:почек|почки|мочеточника|мочевого)",text,re.I)):
            continue
        if code == "KIDNEY_STONES" and re.search(r"желчн\w*\s+пузыр",text,re.I):
            continue
        if code == "FREE_FLUID" and re.search(r"жидкость\s+в\s+грыжевом\s+мешке",text,re.I):
            continue
        if code == "HYDRONEPHROSIS" and re.search(r"ампулярн|внепочечн",text,re.I):
            continue
        if code == "ACUTE_CHOLECYSTITIS" and re.search(r"хроническ\w*\s+холецистит|вне\s+обострения",text,re.I):
            continue
        if code in {"GALLSTONES","GALLBLADDER_POLYP"} and re.search(r"холецистэктом|желчн\w*\s+пузырь\s+удал",text,re.I):
            found.append(dict(code=code,block=block,attrs={},reason="POST_SURGERY"))
            continue
        if not match: continue
        if code == 'ARTERIAL_STENOSIS':
            sides=list(re.finditer(r'\b(справа|слева)\b',text,re.I))
            if len(sides)>1:
                scoped=[]
                for j,side_match in enumerate(sides):
                    end=sides[j+1].start() if j+1<len(sides) else len(text)
                    part=text[side_match.start():end].strip(' ,')
                    if '%' not in part:continue
                    side='right' if side_match[1].lower()=='справа' else 'left'
                    local=Block(part,block.start+side_match.start(),block.start+end,block.section,side,block.organ)
                    attrs=attributes(code,local)
                    # Keep the explicit stenosis mention in the evidence range.
                    evidence=Block(text[:end],block.start,block.start+end,block.section,side,block.organ)
                    scoped.append(dict(code=code,block=evidence,attrs=attrs,reason='NEGATION' if NEG.search(part) else None))
                if scoped:
                    found.extend(scoped)
                    continue
        if code in {"BREAST_LESION","THYROID_NODULE"} and re.fullmatch(r"(?:BI[ -]?RADS|BIRADS|BR|(?:EU[ -]?)?TI[ -]?RADS)",match[0],re.I):
            # A scale name with no number is not evidence of a lesion.
            continue
        anchor=re.search(r"\b(?:образовани\w*|уз(?:ел|лы|лов)\b|полип\w*|кист[аы]\b|конкремент\w*)",text,re.I)
        attrs = attributes(code,block,min(match.end(),anchor.end()) if anchor else match.end())
        # Separate coordinated diagnoses before assigning question/hedging cues.
        left=0;right=len(text)
        for comma in re.finditer(r",\s*(?=(?:полип\w*|миом\w*|кист\w*|образовани\w*|узел|свободн\w*\s+жидкост\w*|также)\b)",text,re.I):
            if comma.end()<=match.start():
                if UNCERTAIN.search(text[left:comma.start()]) and not regex.search(text[left:comma.start()]):continue
                left=comma.end()
            elif comma.start()>=match.end():right=comma.start();break
        attrs['uncertain']=bool(UNCERTAIN.search(text[left:right]))
        attrs["uncertain"] |= any(p.search(text) for p in suspected)
        if code == "ENDOMETRIAL_POLYP" and re.search(r"очагов|локальн|фокальн",match[0],re.I): attrs["uncertain"] = True
        reason = "POST_SURGERY" if SURGERY.search(text) else "NEGATION" if negates(text,match.start(),match.end()) else None
        if code == "HYDRONEPHROSIS" and re.search(r"ЧЛС\s+не\s+расширен",text,re.I): reason = "NEGATION"
        if code == "VENOUS_INSUFFICIENCY" and re.search(r"рефлюкс[^,.;]{0,100}не\s+рег[ие]ст(?:р|ир)",text,re.I): reason = "NEGATION"
        # negates() is anchored to the finding. An unrelated negative attribute
        # must never cancel a real negation of the finding earlier in the clause.
        if code == "OVARIAN_TORSION" and re.search(r"отсутствие\s+кровотока|снижение\s+кровотока",match[0],re.I):
            reason = None
        if code == "ECTOPIC_PREGNANCY" and re.search(r"плодное\s+яйцо.*не\s+визуализируется",text,re.I):
            hcg = [b for b in source_blocks if re.search(r"положительн\w*\s+(?:ХГЧ|тест\s+на\s+беременность)|ХГЧ\s*[:—-]?\s*положительн",b.text,re.I)]
            if not hcg: continue
            attrs.update(hcgPositive=True,uncertain=True)
            reason = None
        if attrs["uncertain"] and re.search(r"не\s+исключается|нельзя\s+исключить",text,re.I) and not NEG.search(text): reason = None
        found.append(dict(code=code,block=block,attrs=attrs,reason=reason))
    return found


def descriptive_attributes(code, rows, source):
    """Enrich an already explicit finding with same-organ descriptive evidence."""
    if not any(not r["reason"] for r in rows) and not (code in {'BREAST_LESION','THYROID_NODULE'} and any(CATEGORY.search(b.text) and b.section not in EXCLUDED_SECTIONS for b in source)): return rows
    extra=[]
    node_list=False
    for b in source:
        if b.section in EXCLUDED_SECTIONS: continue
        marker=None
        if code=='THYROID_NODULE':
            if re.search(r'узлов\w*\s+образовани|узел',b.text,re.I):node_list=True
            elif not re.match(r'\s*в\s+(?:правой|левой)\s+доле\s*:',b.text,re.I):node_list=False
        if any(r["block"].start==b.start for r in rows): continue
        if code=="UTERINE_FIBROID" and b.organ=="uterus" and re.search(r"интрамураль|интерстици|субсерозн|субмукозн|FIGO|[0-8]\s*тип",b.text,re.I):
            marker=re.search(r"образовани\w*|уз(?:ел|лы|лов|ла)\b",b.text,re.I)
        elif code=="ENDOMETRIAL_POLYP" and b.organ=="endometrium":
            marker=re.search(r"образовани\w*|гиперэхогенн\w*\s+участок",b.text,re.I)
        elif code=="ENDOMETRIAL_HYPERPLASIA" and b.organ=="endometrium":
            marker=re.search(r"эндометри\w*|м\s*[-–—]\s*эхо",b.text,re.I)
        elif code=="CERVICAL_POLYP" and b.organ=="cervix":
            marker=re.search(r"гиперэхогенн\w*\s+образовани\w*",b.text,re.I)
        elif code=="OVARIAN_LESION" and b.organ=="ovary":
            marker=re.search(r"(?:анэхогенн\w*|жидкостн\w*|аваскулярн\w*)\s+(?:\w+\s+){0,2}(?:включени\w*|образовани\w*|структур\w*)|полост[ьюи]+",b.text,re.I)
        elif code=="GALLBLADDER_POLYP" and b.organ=="gallbladder" and re.search(r"без\s+акустическ\w*\s+тени|неподвижн|пристеночн",b.text,re.I):
            marker=re.search(r"образован(?:и\w*|яи)",b.text,re.I)
        elif code=="GALLSTONES" and b.organ=="gallbladder" and re.search(r"акустическ\w*\s+тен",b.text,re.I) and not re.search(r"без\s+акустическ",b.text,re.I):
            marker=re.search(r"образовани\w*|включени\w*",b.text,re.I)
        elif code=="THYROID_NODULE" and b.organ in {"study_organ","isthmus"}:
            marker=re.search(r"образовани\w*",b.text,re.I)
            if node_list and dimensions(b.text):marker=marker or re.search(r'\bдоле\s*:',b.text,re.I)
        elif code=="BREAST_LESION" and b.organ=="study_organ":
            marker=re.search(r"неоднородн\w*\s+структур\w*\s+участок|участок\s+неоднородн\w*\s+структур\w*|анэхогенн\w*\s+(?:\w+\s+){0,2}(?:образовани\w*|структур\w*)",b.text,re.I)
        if marker and not negates(b.text,marker.start(),marker.end()) and not SURGERY.search(b.text):
            attrs=attributes(code,b,marker.end())
            if code=="UTERINE_FIBROID" and "figo" not in attrs:
                m=re.search(r"([0-8])\s*тип",b.text,re.I)
                if m: attrs["figo"]=int(m[1])
            extra.append(dict(code=code,block=b,attrs=attrs,reason=None))
    return rows+extra


def scoped_measurements(code,rows):
    """Split bilateral descriptions with separately stated sizes/counts."""
    output=[]
    for r in rows:
        b=r['block'];sides=list(re.finditer(r'\b(справа|слева)\b',b.text,re.I))
        if r['reason'] or len(sides)<2 or not dimensions(b.text):output.append(r);continue
        scoped=[]
        for i,m in enumerate(sides):
            end=sides[i+1].start() if i+1<len(sides) else len(b.text)
            part=b.text[m.start():end].strip(' ,')
            local=Block(part,b.start+m.start(),b.start+m.start()+len(part),b.section,'right' if m[1].lower()=='справа' else 'left',b.organ)
            attrs=attributes(code,local)
            if 'sizeMm' in attrs:scoped.append(dict(code=code,block=b,attrs=attrs,reason=None))
        output.extend(scoped or [r])
    return output


def analyze_protocol(parsed, raw, study, dictionary, context=None):
    if uses_v2_contract(dictionary):
        from .clinical_v2 import analyze
        return analyze(parsed, raw, study, dictionary, context)
    return analyze_legacy(parsed, raw, study, dictionary)


def analyze_legacy(parsed, raw, study, dictionary):
    v2 = uses_v2_contract(dictionary)
    items = [i for i in normalize_dictionary(dictionary) if study in i["studyTypes"]]
    if not items:
        from .contracts import ContractError
        raise ContractError("В словаре нет находок для данного studyType")
    full = parsed["full_text"]
    source = blocks(raw,full)
    source = expand_lesion_blocks(source, full, study)
    # Keep custom codes, but retain section semantics and global quote offsets.
    if all("attributes" not in i for i in items):
        found,rejected=[],[]
        for b in source:
            if b.section in EXCLUDED_SECTIONS: continue
            positives,negatives=literal_analyze(b.text,study,items)
            for f in positives:
                f["evidence"]["start"]+=b.start
                f["evidence"]["end"]+=b.start
            found.extend(positives);rejected.extend(negatives)
        return found,rejected
    found, rejected = [], []
    all_candidates = {i["code"]: candidates_for({**i,'code':i.get('extractionProfile',i['code'])},source,study) for i in items}
    def category_source(b):
        if b.section not in EXCLUDED_SECTIONS:return True
        if b.section!='recommendations':return False
        # Some templates append standalone result categories after recommendations.
        # Accept only a standalone category statement, never conditional advice.
        remainder=CATEGORY.sub('',b.text)
        remainder=re.sub(r"\b(?:справа|слева|категория|правая|левая|доля|молочная|железа)\b",'',remainder,flags=re.I)
        return bool(CATEGORY.search(b.text)) and not remainder.strip(' ,:.-—()')
    category_rows = [row for b in source if category_source(b) for row in find_categories(b,study)]
    for item in items:
        output_code=item['code']
        code = item.get('extractionProfile',output_code)
        rows = scoped_measurements(code,descriptive_attributes(code,all_candidates[output_code],source))
        scale = {"BREAST_LESION":"birads","THYROID_NODULE":"tirads","OVARIAN_LESION":"orads"}.get(code)
        cats = [(attrs,b) for s,attrs,b in category_rows if s == scale]
        # BI-RADS 1–2 explicitly remain facts. O-RADS without a lesion is not
        # an ovarian mass; category 1 alone does not turn a normal follicle into one.
        if code in {"BREAST_LESION","THYROID_NODULE"}:
            rows = [r for r in rows if not CATEGORY.search(r["block"].text)
                    or "sizeMm" in r["attrs"] or (code=="THYROID_NODULE" and re.search(EXTRA[code],r["block"].text,re.I))]
            for attrs,b in cats:
                same=[r for r in rows if not r["reason"] and r["block"].start==b.start and r["block"].end==b.end
                      and r["attrs"].get("side")==b.side]
                if same:
                    for r in same:r["attrs"].update(attrs)
                else: rows.append(dict(code=code,block=b,attrs={**attrs,"uncertain":False,**({"side":b.side} if b.side else {})},reason=None))
        if code == "ENDOMETRIAL_HYPERPLASIA":
            menopause = [b for b in source if re.search(r"\b(?:пост)?менопауз",b.text,re.I) and not re.search(r"нет\s+менопауз|менопауза\s*:\s*нет",b.text,re.I)]
            if menopause and not v2 and not any(not r["reason"] for r in rows):
                for b in source:
                    value = measured(b.text,r"эндометри\w*|м\s*[-–]\s*эхо")
                    if value is not None and not re.search(r"не\s+(?:определ|визуализ)",b.text,re.I):
                        rows.append(dict(code=code,block=b,attrs={"thicknessMm":value,"menopause":True,"fromMeasurement":True,"uncertain":True},reason=None))
        conclusions = [r for r in rows if r["block"].section == "conclusion"]
        positives = []
        for r in rows:
            if "side" not in item.get("attributes",["side"]): r["attrs"].pop("side",None)
            if r["reason"]:
                rejected.append({"code":output_code,"evidence":{"text":r["block"].text},"reason":r["reason"]})
                continue
            # Explicit conclusion negation overrides a descriptive candidate on
            # the same side; normal breast categories remain independently valid.
            if not v2 and r["block"].section != "conclusion" and any(c["reason"] and (not c["block"].side or not r["block"].side or c["block"].side==r["block"].side) for c in conclusions):
                continue
            positives.append(r)
        groups = {}
        known_sides = {r["attrs"].get("side") for r in positives} - {None,"both"}
        if not known_sides and any(r['attrs'].get('side')=='both' for r in positives):known_sides={'both'}
        for r in positives:
            side = r["attrs"].get("side")
            # A summary without side enriches side-specific findings; it is not
            # an extra third lesion. Do not transfer its conflicting categories.
            specific=bool(set(r['attrs'])-{'uncertain','side'})
            summary=r['block'].section=='conclusion' and 'sizeMm' not in r['attrs']
            if code=='ARTERIAL_STENOSIS' and side=='both' and known_sides & {'left','right'}:
                if any(v['attrs'].get('stenosisPct')==r['attrs'].get('stenosisPct') and v['attrs'].get('side') in known_sides for v in positives):continue
            targets = sorted(known_sides) if side in {None,"both"} and known_sides and (not specific or summary) else [side]
            for target in targets: groups.setdefault(target,[]).append(r)
        coherent_groups=[]
        for side,group in groups.items():
            anchors=[r for r in group if "sizeMm" in r["attrs"]]
            # Different named lesion kinds (e.g. cyst / fibroadenoma) are not a
            # single maximum-size finding even when they share one side.
            def kind(r):
                text=r['block'].text
                if re.search(r'фиброаденом',text,re.I):return 'fibroadenoma'
                if re.search(r'\bкист[аы]\b',text,re.I):return 'cyst'
                return None
            kinds={kind(r) for r in anchors}-{None}
            if code=='BREAST_LESION' and len(kinds)>1:
                for value in sorted(kinds):
                    coherent_groups.append((side,[r for r in group if kind(r)==value or (kind(r) is None and 'sizeMm' not in r['attrs'])]))
                continue
            key=scale or ('figo' if code=='UTERINE_FIBROID' else None)
            variants={r['attrs'].get(key) for r in anchors}-{None}
            if len(variants)>1:
                for value in sorted(variants):
                    same=[r for r in group if r['attrs'].get(key)==value or (key not in r['attrs'] and 'sizeMm' not in r['attrs'])]
                    coherent_groups.append((side,same))
                unknown=[r for r in anchors if key not in r['attrs']]
                if unknown:coherent_groups.append((side,unknown))
            else:
                # Diagnostic billing codes must not replace measured lesion types.
                if anchors:group=[r for r in group if r['block'].section!='diagnosis']
                coherent_groups.append((side,group))
        for side, group in coherent_groups:
            attrs, evidence = {}, []
            for row in sorted(group,key=lambda r:r["block"].section=="conclusion"):
                row['attrs'].update(extract_declared(row['block'].text,item))
                for key,value in row["attrs"].items():
                    if key in {"sizeMm","stenosisPct"} and key in attrs: value=max(value,attrs[key])
                    attrs[key]=value
                evidence.append(row["block"])
            if any(r["attrs"].get("uncertain") for r in group): attrs["uncertain"]=True
            for key in item.get('attributeExtractors',{}):
                values=[r['attrs'][key] for r in group if key in r['attrs']]
                if values and any(v!=values[0] for v in values):attrs.pop(key,None)
            if side: attrs["side"]=side
            if side is None:attrs.pop('side',None)
            measured_rows=[r for r in group if 'sizeMm' in r['attrs']]
            distinct={}
            for row in measured_rows:
                # A repeated conclusion with the same size is corroboration.
                signature=(row['attrs']['sizeMm'],row['attrs'].get('count'),row['attrs'].get(scale),row['attrs'].get('figo'))
                # Two measured description rows may legitimately have the same
                # size. Only a repeated summary is evidence of the same lesion.
                if row['block'].section=='conclusion' and any(k[:4]==signature for k in distinct):continue
                distinct[(*signature,row['block'].start)]=row
            if len(distinct)>1:
                attrs['count']=sum(r['attrs'].get('count',1) for r in distinct.values())
            # Use same-side descriptive measurements when the conclusion only
            # names a finding. No organ measurements are borrowed here.
            for row in group:
                if row["attrs"].get("sizeMm") is not None:
                    attrs["sizeMm"] = max(attrs.get("sizeMm",0),row["attrs"]["sizeMm"])
            for cat,b in cats:
                if (b.side == side or (b.side is None and len(groups)==1)) and code=="OVARIAN_LESION" and sum(s==side for s,g in coherent_groups)==1:
                    attrs.update(cat); evidence.append(b)
            # Explicit global attributes with quote coverage, never age-derived.
            for b in source:
                if b.section in EXCLUDED_SECTIONS: continue
                if code=="BPH_URINARY_RETENTION":
                    clean=re.sub(r'\([^)]*норм[^)]*\)','',b.text,flags=re.I)
                    residual_match=re.search(r"остаточн\w*\s+моч|\bостаточ\.",clean,re.I)
                    residual=bool(residual_match)
                    m=re.search(rf"({NUM})\s*(?:мл|см\s*[³3]|куб\s*\.?\s*см|см\s*\.?\s*куб)",clean[residual_match.end():] if residual else clean,re.I)
                    organ_volume=(b.organ in {"study_organ",None} and re.search(r"об[ъь][её]м|\bV\b",clean,re.I)
                                  and not re.search(r"уз[ел]\w*|кист\w*|образовани\w*|мочев\w*\s+пузыр|семенн",clean,re.I))
                    if m and (residual or organ_volume):
                        key="residualUrineMl" if residual else "volumeMl"
                        attrs[key]=float(m[1].replace(",","."));evidence.append(b)
                if code=='UTERINE_FIBROID' and re.search(r'полост\w*',b.text,re.I):
                    value=explicit_bool(b.text,r'полост\w*[^.;]{0,30}\bдеформирован|деформ\w*\s+полост',r'полост\w*[^.;]{0,30}не\s+деформирован|не\s+деформ\w*\s+полост')
                    if value is not None:attrs['deformsCavity']=value;evidence.append(b)
                if "menopause" in item.get("attributes",[]) and re.search(r"\b(?:пост)?менопауз",b.text,re.I) and not re.search(r"нет\s+менопауз|менопауза\s*:\s*нет",b.text,re.I):
                    attrs["menopause"]=True; evidence.append(b)
                if code=="GALLSTONES":
                    val=measured(b.text,r"холедох\w*")
                    if val is not None: attrs["choledochMm"]=val; evidence.append(b)
                    dilated=explicit_bool(b.text,r"холедох\s+расширен|расширение\s+внутрипеч[её]ночных\s+протоков|билиарная\s+гипертензия",r"холедох\s+не\s+расширен|протоки\s+не\s+расширены|желчн\w*\s+ходы\s+не\s+расширены|билиарн\w*\s+русло\s+не\s+расширено")
                    if dilated is not None: attrs["ductsDilated"]=dilated; evidence.append(b)
                if code=="ECTOPIC_PREGNANCY":
                    if re.search(r"положительн\w*\s+(?:ХГЧ|тест\s+на\s+беременность)|ХГЧ\s*[:—-]?\s*положительн",b.text,re.I): attrs["hcgPositive"]=True; evidence.append(b)
                    fluid=re.search(r"свободн\w*\s+жидкост\w*",b.text,re.I)
                    if fluid and not negates(b.text,fluid.start(),fluid.end()): attrs["freeFluid"]=True;evidence.append(b)
                if code in {"THYROID_NODULE","BREAST_LESION"} and re.search(r"лимфоуз|лимфатическ\w*\s+уз",b.text,re.I):
                    if (not b.side or b.side in {side,'both'}) and re.search(r"без\s+дифференциров|нарушенн\w*\s+дифференциров|не\s*четк\w*\s+кортико.медулярн\w*\s+дифференциров|утолщ[её]нн\w*\s+корков|кальцинат|кистозн",b.text,re.I): attrs["suspiciousLymphNodes"]=True; evidence.append(b)
            stone_rows=[r for i in items if i.get('extractionProfile',i['code'])=='GALLSTONES' for r in all_candidates[i['code']]]
            if code=="ACUTE_CHOLECYSTITIS" and any(not r["reason"] for r in stone_rows):
                attrs["withStones"]=True
                evidence.extend(r["block"] for r in stone_rows if not r["reason"])
            allowed=item.get("attributes",["uncertain","sizeMm","side"])
            attrs={k:v for k,v in attrs.items() if k in allowed}
            start,end=min(b.start for b in evidence),max(b.end for b in evidence)
            found.append({"code":output_code,"evidence":{"text":full[start:end],"start":start,"end":end},"attributes":attrs})
    # Symmetric vascular maxima describe one bilateral fact. Categories for
    # paired glands remain separate, as required by their dictionary contract.
    for code in (i['code'] for i in items if i.get('extractionProfile',i['code']) in {'ARTERIAL_STENOSIS','VENOUS_INSUFFICIENCY'}):
        right=[f for f in found if f['code']==code and f['attributes'].get('side')=='right']
        left=[f for f in found if f['code']==code and f['attributes'].get('side')=='left']
        if not v2 and len(right)==len(left)==1:
            a,b=right[0],left[0]
            if {k:v for k,v in a['attributes'].items() if k!='side'}=={k:v for k,v in b['attributes'].items() if k!='side'}:
                a['attributes']['side']='both'
                start=min(a['evidence']['start'],b['evidence']['start']);end=max(a['evidence']['end'],b['evidence']['end'])
                a['evidence']={'text':full[start:end],'start':start,'end':end};found.remove(b)
    # Unique diagnostic rejections, preserving original evidence.
    unique={(r["code"],r["reason"],r["evidence"]["text"]):r for r in rejected}
    return found,list(unique.values())
