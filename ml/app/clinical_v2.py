"""Dictionary-driven v2 fact extraction. No routes or gold data are read here.

The shared parser supplies source spans. Profiles add clinical attribute semantics;
new dictionary codes/synonyms work through the generic extractor, and the existing
attributeExtractors DSL can describe new fields without executable expressions.
"""
from copy import deepcopy
from datetime import date, datetime
import re

from .clinical import (analyze_legacy, blocks, expand_lesion_blocks, dimensions, attributes,
                       measured, explicit_bool, phrase_pattern, negates, NUM,
                       EXCLUDED_SECTIONS, Block, side_of)
from .dictionary import normalize_dictionary
from .extensions import extract_declared


def has(pattern, text):
    return re.search(pattern, text, re.I) is not None


def number(pattern, text):
    m = re.search(pattern, text, re.I)
    return float(m[1].replace(',', '.')) if m else None


def put(attrs, key, value):
    if value is not None:
        attrs[key] = value


def positive(pattern, text):
    return any(not negates(text, m.start(), m.end()) for m in re.finditer(pattern, text, re.I))


def inflected_pattern(phrase):
    """Inflection of dictionary literals, never executable YAML expressions."""
    tokens=[]
    for word in phrase.split():
        if re.fullmatch(r'[а-яё]{5,}',word.lower()):
            root=re.sub(r'(?:иями|ами|ями|ого|его|ыми|ими|ых|их|ый|ий|ой|ая|ое|ые|ия|ие|ии|ов|ев|ам|ям|ах|ях|а|я|ы|и|у|ю|е|о)$','',word.lower())
            tokens.append(re.escape(root).replace('ё','[её]')+r'\w*')
        else:tokens.append(re.escape(word))
    return r'(?<!\w)'+r'\s+'.join(tokens)+r'(?!\w)'


def flag(code):
    return {'code': code}


def protocol_flags(parsed):
    result = []
    if not any(s['name'] == 'conclusion' and s['text'].strip() for s in parsed['sections']):
        result.append(flag('NO_CONCLUSION'))
    if has(r'не\s+натощак|после\s+еды|после\s+при[её]ма\s+пищи', parsed['full_text']):
        result.append(flag('PREP_VIOLATED'))
    return result


def context_attributes(text, context):
    a = {}
    if positive(r'\b(?:пост)?менопауз\w*', text): a['menopause'] = True
    if positive(r'кровянист\w*\s+выделен|мажущ\w*\s+выделен|кровотечен|\bАМК\b', text): a['bleeding'] = True
    if has(r'положительн\w*\s+(?:ХГЧ|тест\s+на\s+беременность)|ХГЧ\s*[:—-]?\s*положительн', text): a['hcgPositive'] = True
    m=re.search(r'(?:день\s*(?:МЦ|цикла)|день\s+менструальн\w*\s+цикла)\s*[:—–-]?\s*(\d+)',text,re.I)
    if not m:m=re.search(r'(?<!\d)(\d{1,3})\s*(?:день\s+(?:менструальн\w*\s+)?цикла|д\.?\s*м\.?\s*ц)',text,re.I)
    if m: a['cycleDay'] = int(m[1])
    if a.get('cycleDay',0)>60:a['monthsSinceLmp']=round(a['cycleDay']/30.4375)
    months = number(rf'(?:менструац\w*\s+(?:нет|отсутств\w*)|аменорея)[^.;]{{0,20}}?({NUM})\s*мес', text)
    if months is not None: a['monthsSinceLmp'] = months
    m = re.search(r'(?:ДПМ|последн\w*\s+менструац\w*)\s*[:—-]?\s*(\d{2}\.\d{2}\.\d{4})', text, re.I)
    if m and context:
        try:
            delta = (date.fromisoformat(context['protocol']['studyDate']) - datetime.strptime(m[1], '%d.%m.%Y').date()).days
            if delta >= 0: a['monthsSinceLmp'] = round(delta / 30.4375, 1)
        except (ValueError, KeyError): pass
    if positive(r'\bЗГТ\b', text): a['hrt'] = True
    if positive(r'\bКОК\b|комбинированн\w*\s+оральн\w*|при[её]м\s+силуэт', text): a['onCOC'] = True
    return a


def analyze(parsed, raw, study, dictionary, context=None):
    full = parsed['full_text']
    items = {i['code']: i for i in normalize_dictionary(dictionary)
             if study in i['studyTypes'] and i.get('active', True)}
    local = deepcopy(dictionary)
    local['findings'] = list(items.values())
    found, rejected = analyze_legacy(parsed, raw, study, local)
    source = [b for b in expand_lesion_blocks(blocks(raw, full), full, study)
              if b.section not in EXCLUDED_SECTIONS]
    if study=='PELVIS_FEMALE':
        ovary_side=None;section=None
        for b in source:
            if b.section!=section:ovary_side=None;section=b.section
            if re.match(r'^(?:ПРАВЫЙ|ЛЕВЫЙ)\s+ЯИЧНИК',b.text,re.I):ovary_side=side_of(b.text)
            elif re.match(r'^(?:ШЕЙКА|МАТКА|ЭНДОМЕТРИЙ|М-ЭХО|Цервикальный)',b.text,re.I):ovary_side=None
            if ovary_side:b.organ='ovary';b.side=ovary_side
    conclusion = ' '.join(b.text for b in source if b.section == 'conclusion')
    clinical_text = ' '.join(b.text for b in source)
    patient_attrs = context_attributes(full, context)
    if 'cycleDay' not in patient_attrs and parsed.get('examination_date'):
        m=re.search(r'(?:первый\s+день\s+последней\s+менструации|ДПМ)\s*:\s*(\d{2}\.\d{2}\.\d{4})',full,re.I)
        if m:
            try:
                delta=(date.fromisoformat(parsed['examination_date'])-datetime.strptime(m[1],'%d.%m.%Y').date()).days
                if 0<=delta<60:patient_attrs['cycleDay']=delta+1
            except ValueError:pass

    def evidence(bs):
        start, end = min(b.start for b in bs), max(b.end for b in bs)
        return {'text': full[start:end], 'start': start, 'end': end}

    def reject(code, bs, reason='NORMAL'):
        if code in items and bs:
            rejected.append({'code': code, 'evidence': evidence(bs), 'reason': reason})

    def add(code, bs, attrs=None, flags=None):
        if code not in items or not bs: return
        a = dict(attrs or {})
        side = {b.side for b in bs} - {None, 'both'}
        if 'side' in items[code].get('attributes', []) and len(side) == 1:
            a.setdefault('side', next(iter(side)))
        found.append({'code': code, 'attributes': a, 'evidence': evidence(bs), 'flags': flags or []})

    def select(pattern, organ=None):
        return [b for b in source if (organ is None or b.organ in organ)
                and positive(pattern, b.text)]

    for code,item in items.items():
        if any(f['code']==code for f in found):continue
        pattern='|'.join(inflected_pattern(s) for s in [item['name']]+item['synonyms'])
        for b in source:
            m=re.search(pattern,b.text,re.I)
            if not m or has(r'морфолог|гистолог|\bв\s+анамнезе\b',b.text):continue
            if negates(b.text,m.start(),m.end()):reject(code,[b],'NEGATION');continue
            if code in {'DEEP_VEIN_THROMBOSIS','ARTERIAL_STENOSIS','THYROID_NODULE','BREAST_LESION','GALLSTONES','OVARIAN_LESION'}:continue
            add(code,[b],attributes(code,b,m.end()))

    # Description-only facts, vocabulary aliases and anatomical patterns.
    patterns = {
        'CERVICAL_RETENTION_CYSTS': r'эндоцервикоз|наботов|ретенционн\w*\s+кист|кист[аы]\b',
        'ENDOCERVICITIS': r'эндоцервицит|эндоцервикс[^.;]*утолщ[^.;]*неоднород',
        'BILIARY_SLUDGE': r'\bсладж|холестаз|эхоген\w*\s+(?:осадок|взвесь)|мелкодисперсн\w*\s+взвесь',
        'HEPATIC_STEATOSIS': r'эхогенност\w*[^.;]{0,35}повышен|диффузн\w*\s+изменени\w*\s+(?:паренхимы\s+)?печени',
        'ADENOMYOSIS': r'миометри\w*[^.;]{0,25}неоднород|неоднород\w*[^.;]{0,25}миометри',
        'HYDROSALPINX': r'гидросальпин[кг]с\w*',
        'ENDOMETRIAL_HYPERPLASIA': r'эндометри\w*[^.;]*не\s+соответств\w*\s+дню',
        'SUPERFICIAL_THROMBOPHLEBITIS': r'(?:варико)?тромбофлебит\w*',
        'ACUTE_CHOLECYSTITIS': r'остр\w*\s+(?:калькул[её]зн\w*\s+)?холецистит\w*',
        'OVARIAN_TORSION': r'перекрут\w*\s+(?:(?:прав|лев)\w*\s+)?(?:придатк|яичник)\w*',
        'INTRAUTERINE_SYNECHIAE': r'внутриматочн\w*\s+синехи\w*',
        'THYROID_DIFFUSE_AIT': r'\bАИТ\b|по\s+типу\s+тиреоидит',
        'PELVIC_VARICOSE_VEINS': r'вен\w*\s+(?:параметри|таза)[^.;]*(?:расширен|\d\s*мм)|параметральн\w*\s+вен\w*[^.;]*расширен',
        'BPH': r'гиперплази\w*[^.;]{0,50}предстательн|по\s+типу\s+хроническ\w*\s+простатит',
        'FREE_FLUID': r'(?:позадиматочн|дугласов|подпеч[её]ночн|боков\w*\s+канал)[^.;]*жидкост|гемоперитонеум',
    }
    for code, pattern in patterns.items():
        for b in select(pattern):
            if code == 'CERVICAL_RETENTION_CYSTS' and b.organ != 'cervix' and not has(r'наботов|эндоцервикоз|шейки', b.text): continue
            if code == 'HEPATIC_STEATOSIS' and not (has(r'печень|печени', b.text) or (b.organ == 'other' and any(has(r'печень', p.text) for p in source if p.start <= b.start and b.start-p.end < 500) and not any(has(r'поджелудочн',p.text) for p in source if 0<=b.start-p.start<500))): continue
            if code == 'BILIARY_SLUDGE' and b.organ not in {'gallbladder', None} and not has(r'сладж|холестаз', b.text): continue
            if code == 'ADENOMYOSIS' and (has(r'узел|узлы|миома', b.text) or not has(r'включен|асимметри|аденомиоз', b.text)): continue
            if not any(f['code'] == code and f['evidence']['start'] <= b.start <= f['evidence']['end'] for f in found):
                add(code, [b], {'uncertain': True} if code in {'ADENOMYOSIS','HEPATIC_STEATOSIS'} else {})

    if patient_attrs.get('menopause') and 'ENDOMETRIAL_HYPERPLASIA' in items and not any(f['code']=='ENDOMETRIAL_HYPERPLASIA' for f in found):
        bs=[b for b in source if b.organ=='endometrium' and measured(b.text,r'эндометри\w*|м\s*[-–—]\s*эхо') is not None]
        if bs:add('ENDOMETRIAL_HYPERPLASIA',bs,dict(menopause=True,fromMeasurement=True,uncertain=True))
    if 'BILIARY_SLUDGE' in items:
        bs=[b for b in source if b.organ=='gallbladder' and positive(r'взвес\w*|взвесь',b.text)]
        if bs and not any(f['code']=='BILIARY_SLUDGE' for f in found):add('BILIARY_SLUDGE',bs)
    if study=='THYROID':
        bs=[b for b in source if has(r'общий\s+об[ъь][её]м|общим\s+об[ъь][её]м',b.text)]
        volume=number(rf'общ(?:ий|им)\s+об[ъь][её]м\w*[^\d]{{0,35}}({NUM})', ' '.join(b.text for b in bs))
        sex=(context or {}).get('patient',{}).get('sex')
        volume=number(rf'общ(?:ий|им)\s+об[ъь][её]м\w*[^\d]{{0,35}}({NUM})',full)
        for i,b in enumerate(source):
            if b in bs and i+1<len(source) and re.match(r'^\d',source[i+1].text):bs.append(source[i+1]);break
        if bs and (has(r'увеличен', ' '.join(b.text for b in bs)) or (volume is not None and sex in {'F','M'} and volume>(18 if sex=='F' else 25))):add('THYROID_ENLARGEMENT',bs,{'volumeCm3':volume})
    if study=='PELVIS_FEMALE':
        if patient_attrs.get('monthsSinceLmp',0)>=3 and 'AMENORRHEA_HISTORY' in items:
            bs=[b for b in source if has(r'день\s+цикла|ДПМ|менструаци',b.text)]
            if bs:add('AMENORRHEA_HISTORY',bs,{'monthsSinceLmp':patient_attrs['monthsSinceLmp']})
        adeno=[b for b in source if has(r'эндометриоз\w*\s+(?:тела\s+)?матки',b.text) or (b.organ=='uterus' and has(r'неоднородн|не\s+однородн',b.text) and has(r'гиперэхоген\w*\s+(?:линейн\w*\s+)?включен|гетероген\w*\s+включен|асимметр',b.text))]
        if adeno and not any(f['code']=='ADENOMYOSIS' for f in found):add('ADENOMYOSIS',adeno,{'uncertain':not any(b.section=='conclusion' for b in adeno)})
        if has(r'патологи\w*\s+эндометрия',conclusion):
            bs=[b for b in source if b.organ=='endometrium' and has(r'участок\s+повышенной\s+эхогенности',b.text)]
            if bs and not any(f['code']=='ENDOMETRIAL_POLYP' for f in found):
                vals=[v[0] for b in bs for v in dimensions(b.text.split('участок')[-1])]
                add('ENDOMETRIAL_POLYP',bs,{'uncertain':True,**({'sizeMm':max(vals)} if vals else {})})
    if study=='ABDOMEN':
        liver=False;bs=[]
        for b in source:
            if has(r'\bПЕЧЕНЬ\b',b.text):liver=True
            if has(r'желчн\w*\s+пузыр|поджелудочн|селез[её]нк',b.text):liver=False
            if liver and has(r'эхогенност[^.;]*повышен',b.text):bs.append(b)
        if bs and not any(f['code']=='HEPATIC_STEATOSIS' for f in found):add('HEPATIC_STEATOSIS',bs,{'uncertain':True},[flag('DISCREPANCY')])
        bs=[b for b in source if b.organ=='gallbladder' and has(r'несмещаем\w*\s+образован|неподвижн\w*\s+.*образован',b.text) and has(r'без\s+акустическ\w*\s+тени',b.text)]
        if bs and not any(f['code']=='GALLBLADDER_POLYP' for f in found):
            vals=[v[0] for b in bs for v in dimensions(b.text)]
            add('GALLBLADDER_POLYP',bs,{'sizeMm':max(vals)} if vals else {})
    if study=='BREAST' and not any(f['code']=='BREAST_LESION' for f in found):
        bs=[b for b in source if has(r'фиброзн\w*\s+изменен|участк\w*\s+(?:линейн\w*\s+)?фиброз',b.text)]
        for side in ('right','left'):
            selected=[b for b in bs if b.side in {side,'both',None}]
            if selected:add('BREAST_LESION',selected,{'side':side,'benignChanges':True})
    if study=='LOWER_LIMB_VESSELS':
        for side in ('right','left'):
            bs=[b for b in source if b.side==side and has(r'БПВ|МПВ',b.text) and has(r'расширен',b.text) and has(r'без\s+искажения',b.text)]
            if bs:
                a={'side':side,'vein':'БПВ' if has('БПВ',bs[0].text) else 'МПВ'}
                put(a,'diameterMm',measured(' '.join(b.text for b in bs),r'диаметр\w*'))
                add('SAPHENOUS_DILATION',bs,a,[flag('DISCREPANCY'),flag('INCOMPLETE')])
                found=[f for f in found if not (f['code']=='VENOUS_INSUFFICIENCY' and f['attributes'].get('side')==side)]
        if has(r'\bC1\w*',conclusion) and not any(b.section=='description' and positive(r'варикозн\w*\s+(?:расширен|трансформац|деформац)',b.text) for b in source):
            found=[f for f in found if f['code']!='VENOUS_INSUFFICIENCY']

    # Regional fluid, superficial thrombosis, and a past thrombosis are different
    # entities. Do not reuse a broad word like "тромб" across anatomy.
    if study == 'LOWER_LIMB_VESSELS':
        arterial = has(r'УЗДС\s+артерий|артерий\s+нижних|аневризм', clinical_text) and not has(r'тромбоз\w*\s+глубок', conclusion)
        superficial = has(r'тромбофлебит|тромбоз\w*\s+(?:БПВ|МПВ|поверхност)', conclusion)
        post = has(r'посттромбот|реканализац', conclusion)
        explicit_deep=any(positive(r'тромбоз\w*\s+глубок\w*\s+вен|глубок\w*\s+вен\w*[^.;]{0,40}тромбоз',b.text) and not has(r'в\s+анамнезе|\d+\s*(?:лет|года?|месяц\w*)\s+назад|перенес[её]н',b.text) for b in source)
        if (arterial or superficial or post) and not explicit_deep:
            found = [f for f in found if f['code'] != 'DEEP_VEIN_THROMBOSIS']
        normals = [b for b in source if has(r'глубок\w*\s+вен', b.text) and has(r'проходим|данных[^.;]*не\s+получено|не\s+выявлен', b.text)]
        reject('DEEP_VEIN_THROMBOSIS', normals, 'NEGATION')
        if arterial:
            found = [f for f in found if f['code'] not in {'VENOUS_INSUFFICIENCY','POST_THROMBOTIC_CHANGES'}]
        if not has(r'артери|\bАСБ\b', clinical_text):
            found = [f for f in found if f['code'] != 'ARTERIAL_STENOSIS']

    # Disambiguate explicit physiological descriptions from masses.
    phys = [b for b in source if has(r'ж[её]лт\w*\s+тело|доминантн\w*\s+фолликул', b.text) and not has(r'кист', b.text)
            and (not dimensions(re.split(r'ж[её]лт\w*\s+тело|доминантн\w*\s+фолликул',b.text,flags=re.I)[-1]) or max(x[0] for x in dimensions(re.split(r'ж[её]лт\w*\s+тело|доминантн\w*\s+фолликул',b.text,flags=re.I)[-1])) <= 30)]
    if phys: reject('OVARIAN_LESION', phys)
    reject('OVARIAN_LESION',[b for b in source if has(r'[OО]\s*[-–]?\s*RADS\s*(?:1|I)\b',b.text) and not has(r'кист|образован',b.text)])
    reject('IUD_MALPOSITION',[b for b in source if has(r'ВМС',b.text) and has(r'типично|у\s+дна|правильно',b.text)])
    reject('SUPERFICIAL_THROMBOPHLEBITIS',[b for b in source if has(r'подкожн\w*\s+вен|поверхностн\w*\s+вен',b.text) and has(r'проходим|тромбоз\w*\s+не\s+выявлен|не\s+получено',b.text)],'NEGATION')
    for f in list(found):
        code, a = f['code'], f['attributes']
        side = a.get('side')
        if code == 'BREAST_LESION' and a.get('birads') == 1 and not any(has(r'кожн\w*\s+покров\w*[^.;]{0,30}утолщ|кожа[^.;]{0,30}утолщ',b.text) for b in source) and not any(a.get(k) for k in ('sizeMm','skinThickening','suspiciousLymphNodes','inflammation')):
            reject(code, [Block(f['evidence']['text'], f['evidence']['start'], f['evidence']['end'], 'conclusion')]);found.remove(f)
        if code == 'OVARIAN_LESION':
            same = [b for b in source if b.side in {side, None}]
            same_text = ' '.join(b.text for b in same)
            normal_conclusion = has(r'ж[её]лт\w*\s+тело|O\s*[-–]?\s*RADS\s*(?:1|I)\b', ' '.join(b.text for b in same if b.section == 'conclusion')) and not has(r'кист', conclusion)
            competing = has(r'апоплекс|тубоовариальн|трубн\w*\s+беременн|перекрут', conclusion) and not has(r'киста\s+яичника|цистаденом|тератом', conclusion)
            if normal_conclusion or competing:
                if normal_conclusion: reject(code, same)
                found.remove(f)
        if code == 'OVARIAN_APOPLEXY' and not has(r'апоплекс|разрыв|гемоперитонеум', conclusion): found.remove(f)
        if code == 'BPH_URINARY_RETENTION' and not has(r'остаточн\w*\s+моч|остаточ\.', clinical_text): found.remove(f)
        if code=='BILIARY_SLUDGE' and has(r'взвес\w*\s+и\s+конкремент\w*[^.;]{0,20}не\s+определ',f['evidence']['text']):
            reject(code,[Block(f['evidence']['text'],f['evidence']['start'],f['evidence']['end'],'description')],'NEGATION');found.remove(f)
        if code=='THYROID_NODULE' and 'sizeMm' not in a and has(r'узл\w*\s+нет|об[ъь][её]мн\w*\s+образовани\w*[^.;]*не\s+выявлен',clinical_text):found.remove(f)
        elif code=='THYROID_NODULE' and a.get('tirads')==1 and 'sizeMm' not in a:found.remove(f)
        if code == 'FREE_FLUID' and not has(r'свободн\w*\s+жидк|позадиматоч|дугласов|асцит|гемоперитонеум|боков\w*\s+канал', f['evidence']['text']):
            if has(r'перивезик|перипузыр|грыжев', f['evidence']['text']): found.remove(f)
        if code=='FREE_FLUID' and has(r'жидкост\w*[^.;]{0,70}не\s+(?:лоцирован|определ|выявлен|визуализ)|жидкост\w*[^.;]{0,20}нет',f['evidence']['text']) and not has(r'\d\s*мл|выпот',f['evidence']['text']):found.remove(f)

    # PCOM needs quantitative evidence, not merely the word multifollicular.
    if 'PCOM' in items:
        found = [f for f in found if f['code'] != 'PCOM']
        for side in ('right', 'left'):
            bs = [b for b in source if b.organ == 'ovary' and b.side == side and b.section != 'conclusion']
            t = ' '.join(b.text for b in bs)
            vol = number(rf'(?:об[ъь][её]м(?:\s+яичника)?|V)\s*[:=—–-]?\s*({NUM})\s*(?:см|мл)', t)
            computed = False
            if vol is None:
                m = re.search(rf'({NUM})\s*[xх×*]\s*({NUM})\s*[xх×*]\s*({NUM})\s*(мм|см)', t, re.I)
                if m:
                    vals = [float(m[i].replace(',', '.')) for i in (1,2,3)]
                    vol = round(.523 * vals[0]*vals[1]*vals[2] / (1000 if m[4].lower() == 'мм' else 1), 1); computed = True
            count = number(r'(?:до\s*)?(\d+)\s*фолликул', t)
            low_frequency=has(r'трансабдоминальн|ТАУЗИ',clinical_text)
            probe=number(rf'(?:частот\w*\s*)({NUM})\s*(?:МГц|MHz)',clinical_text)
            if probe is not None and probe<8:low_frequency=True
            if computed and has(r'кист|образовани\w*|ж[её]лт\w*\s+тело',t):vol=None
            if not has(r'перекрут|апоплекс|абсцесс', conclusion) and ((vol is not None and vol >= 10) or (count is not None and (count >= 20 or low_frequency and count>10)) or has(r'поликистоз', t)):
                a = {'side': side}
                put(a, 'ovaryVolumeCm3', vol);put(a, 'follicleCount', int(count) if count is not None else None)
                if computed: a['volumeCalculated'] = True
                structure_text=t+' '+' '.join(b.text for b in source if b.section=='conclusion' and b.side in {side,'both'})
                if positive(r'ж[её]лт\w*\s+тело|доминантн\w*\s+фолликул|кист', structure_text): a['dominantStructure'] = True
                if low_frequency: a['lowFrequencyProbe'] = True
                add('PCOM', bs, a)

    # Keep separate gallbladder and common duct stones. Descriptive dimensions
    # of an organ/wall are never used as the stone size.
    if any(f['code'] == 'GALLSTONES' for f in found):
        old = [f for f in found if f['code'] == 'GALLSTONES']
        found = [f for f in found if f['code'] != 'GALLSTONES']
        for location in ('choledoch', 'gallbladder'):
            if location == 'choledoch':
                bs = [b for b in source if has(r'хол[еи]дох', b.text) and positive(r'литиаз|конкремент|акустическ\w*\s+тень', b.text)]
                for idx,b in enumerate(source):
                    if has(r'хол[еи]дох', b.text) and idx+1 < len(source) and source[idx+1].section==b.section and has(r'дистальн\w*\s+отдел[^.;]*(?:гиперэхоген|конкремент)', source[idx+1].text): bs.append(source[idx+1])
            else:
                bs = [b for b in source if (b.organ == 'gallbladder' or has(r'ЖКБ|холецистолитиаз|калькул[её]з', b.text))
                      and (positive(r'конкремент\w*|микролит\w*|ЖКБ|холецистолитиаз|калькул[её]з', b.text) or (has(r'гиперэхоген\w*\s+образовани',b.text) and positive(r'акустическ\w*\s+тен',b.text))) and not has(r'хол[еи]дохолитиаз', b.text)]
            bs=[b for b in bs if not has(r'конкремент\w*[^.;]{0,25}не\s+выявлен|конкремент\w*[^.;]{0,25}нет',b.text)]
            if bs:
                t = ' '.join(b.text for b in bs)
                a = {'location': location}
                values = []
                for b in bs:
                    m = re.search(r'конкремент\w*|микролит\w*|структур\w*|образовани\w*', b.text, re.I)
                    if m: values += [v[0] for v in dimensions(b.text[m.end():])]
                if values: a['sizeMm'] = max(values)
                if has(r'множествен', t): a['count'] = 'множественные'
                elif has(r'одиночн|единствен|единичн', t): a['count'] = 1
                put(a, 'mobile', explicit_bool(t, r'смещаем|подвижн|перемещ', r'неподвижн|не\s+смещ|несмещ'))
                add('GALLSTONES', bs, a)
        if not any(f['code'] == 'GALLSTONES' for f in found): found.extend(old)
        if has(r'холецистэктом',clinical_text) and not any(positive(r'холедохолитиаз|конкремент\w*',b.text) and not has(r'не\s+выявлен|нет|свободен',b.text) for b in source):
            found=[f for f in found if f['code']!='GALLSTONES']

    # A side-less mention of an empty uterine cavity corroborates the sided
    # ectopic finding; it is not another pregnancy.
    ectopic=[f for f in found if f['code']=='ECTOPIC_PREGNANCY']
    if any(f['attributes'].get('side') in {'left','right'} for f in ectopic):
        found=[f for f in found if f['code']!='ECTOPIC_PREGNANCY' or f['attributes'].get('side') in {'left','right'}]

    # Enrich each entity with same-side, same-organ descriptive facts.
    organ_map = {'CERVICAL_RETENTION_CYSTS': {'cervix'}, 'CERVICAL_POLYP': {'cervix'},
                 'ENDOMETRIAL_HYPERPLASIA': {'endometrium'}, 'GALLBLADDER_HYDROPS': {'gallbladder'},
                 'GALLBLADDER_POLYP': {'gallbladder'}, 'ACUTE_CHOLECYSTITIS': {'gallbladder'},
                 'OVARIAN_TORSION': {'ovary'}, 'TUBO_OVARIAN_ABSCESS': {'ovary'},
                 'OVARIAN_LESION': {'ovary'}, 'HYDRONEPHROSIS': {'kidney'}, 'KIDNEY_STONES': {'kidney'}}
    for f in found:
        code, a = f['code'], f['attributes']
        side = a.get('side')
        anchors = [b for b in source if f['evidence']['start'] <= b.start and b.end <= f['evidence']['end']]
        related = [b for b in source if (not side or b.side in {side, None, 'both'})]
        if code in organ_map: related = [b for b in related if b.organ in organ_map[code] or (code=='TUBO_OVARIAN_ABSCESS' and has(r'в\s+проекции\s+придатков',b.text))]
        elif code not in {'HERNIA','DEEP_VEIN_THROMBOSIS','SUPERFICIAL_THROMBOPHLEBITIS','POST_THROMBOTIC_CHANGES','VENOUS_INSUFFICIENCY','ARTERIAL_STENOSIS','BPH','BPH_URINARY_RETENTION','FREE_FLUID','OVARIAN_APOPLEXY','ECTOPIC_PREGNANCY','IUD_MALPOSITION','HEPATIC_STEATOSIS','THYROID_NODULE','BREAST_LESION','THYROID_ENLARGEMENT'}:
            related = anchors
        t = ' '.join(b.text for b in related)
        original = f['evidence']['text']
        a.update({k:v for k,v in patient_attrs.items() if k in items[code].get('attributes', [])})
        if has(r'по\s+типу', original) and code in {'ADENOMYOSIS','THYROID_DIFFUSE_AIT','ENDOCERVICITIS'}: a['uncertain'] = True
        if code == 'THYROID_NODULE':
            category_text=' '.join(b.text for b in anchors if b.side==side) or original
            cat = re.search(r'(EU\s*[-–]?\s*T[IІ]\s*[-–]?\s*RADS|ACR\s*TI\s*[-–]?\s*RADS|TI\s*[-–]?\s*RADS|TR)\s*[-:=]?\s*([1-5])([abcабв])?', category_text, re.I)
            if cat:
                raw_cat = cat[2] + (cat[3] or '').lower().translate(str.maketrans('абв','abc'))
                a['tiradsRaw'] = raw_cat
                a['tiradsSystem'] = 'EU' if cat[1].upper().startswith('EU') else 'ACR' if cat[1].upper().startswith(('ACR','TR')) else 'KWAK' if cat[3] else 'UNKNOWN'
                a['tirads'] = 5 if raw_cat in {'4b','4c'} else int(cat[2])
            elif has(r'губчат', original) and 'tirads' not in a: a.update(tirads=2,tiradsSystem='UNKNOWN')
            if positive(r'микрокальцинат\w*', t): a['suspiciousFeatures'] = sorted(set(a.get('suspiciousFeatures', []) + ['микрокальцинаты']))
        if code == 'BREAST_LESION':
            if not side and has(r'с\s+обеих\s+сторон|обеих\s+молочн|справа\s+и\s+слева',clinical_text):a['side']='both'
            values=[]
            for b in related:
                if b.organ=='study_organ' and positive(r'образовани\w*|кист[аы]|фиброаденом\w*',b.text):
                    m=re.search(r'образовани\w*|кист[аы]|фиброаденом\w*',b.text,re.I)
                    values += [v[0] for v in dimensions(b.text[m.end():])]
            if values and 'sizeMm' not in a:a['sizeMm']=max(values)
            if any(b.organ=='lymph' and has(r'подозрительн|ворота\s+не\s+дифференц|нарушен\w*\s+дифференц',b.text) for b in related):a['suspiciousLymphNodes']=True
            if has(r'кист|фиброз|фиброаденом|мастопат', original): a['benignChanges'] = True
            elif has(r'имплант|эндопротез|жиров\w*\s+инволюц',clinical_text):a['benignChanges']=False
            if has(r'\bмастит|воспалительн\w*\s+изменен|гиперемир',t):a['inflammation']=True
            if any(positive(r'утолщ\w*[^.;]{0,15}\bкож[аиу]\b|\bкожа\b[^.;]{0,30}утолщ|кожн\w*\s+покров\w*[^.;]{0,30}утолщ',b.text) for b in related):a['skinThickening']=True
            if has(r'проток[^.;]*содержим', t): a['ductContent'] = True
        if code == 'OVARIAN_LESION':
            for pattern,value in [(r'параовариальн','paraovarian'),(r'эндометрио|эндометриома','endometrioma'),(r'дермоид|тератом','dermoid'),(r'фолликулярн\w*\s+кист|киста\s+ж[её]лт|геморрагическ\w*\s+кист','functional'),(r'прост\w*\s+кист|однокамерн','simple')]:
                if has(pattern, original): a['lesionType'] = value;break
            if positive(r'солидн\w*\s+компонент|кистозно.солидн', t): a['solid'] = True
            if positive(r'многокамерн|перегородк', t): a['septated'] = True
            if has(r'локус\w*\s+кровоток|кровоток\s+в\s+(?:образован|солидн)', t): a['vascularized'] = True
        if code == 'UTERINE_FIBROID':
            if has(r'рождающ|пролабир', original): a['prolapsing'] = True
            cats=[]
            for b in source:
                if b.section=='conclusion':continue
                cats += [int(x) for x in re.findall(r'(?:FIGO\s*[:—-]?\s*|тип\s*)([0-8])(?!\d)',b.text,re.I)]
            if len(set(cats))==1 and 'figo' in a and a['figo']!=cats[0]:
                f.setdefault('flags',[]).append(flag('DISCREPANCY'))
            weeks=number(r'соответств\w*\s+(\d+)\s+недел',original)
            if weeks is not None:a['uterusWeeks']=int(weeks)
            if positive(r'перекрут\w*\s+ножк',original):a['pedicleTorsion']=True
            if positive(r'некроз\w*\s+узл|нарушени\w*\s+кровообращени\w*\s+в\s+узле',original):a['degeneration']=True
            if positive(r'сдавлен\w*\s+(?:мочев|мочеточ|киш)',original):a['compression']=True
        if code=='ADENOMYOSIS':
            if has(r'узлов\w*\s+форм',original):a['form']='nodular'
            elif has(r'диффуз',original):a['form']='diffuse'
        if code in {'OVARIAN_TORSION','TUBO_OVARIAN_ABSCESS','GALLBLADDER_HYDROPS'}:
            candidates = [b for b in related if dimensions(b.text) and (has(r'увеличен|образован|абсцесс|\bяичник\s*:', b.text))]
            if candidates: a['sizeMm'] = max(dimensions(b.text)[0][0] for b in candidates)
            if code == 'OVARIAN_TORSION':
                if has(r'кровоток[^.;]*не\s+регистр|отсутств\w*[^.;]*кровоток', t): a['noFlow'] = True
                if has(r'водоворот|скрученн\w*\s+ножк', t): a['whirlpool'] = True
        if code in {'TUBO_OVARIAN_ABSCESS','ECTOPIC_PREGNANCY'} and has(r'ВМС\s+(?:установлена|в\s+полости)', clinical_text): a['iudInPlace'] = True
        if code == 'FREE_FLUID':
            related = [b for b in source if has(r'жидкост|выпот|асцит|гемоперитонеум', b.text) and not has(r'полости\s+матки|грыжев|перивезик|перипузыр', b.text) and not has(r'жидкост\w*\s+(?:образован|структур)', b.text)]
            t = ' '.join(b.text for b in related)
            volumes = re.findall(rf'({NUM})\s*мл', t, re.I)
            if volumes: a['volumeMl'] = max(float(v.replace(',','.')) for v in volumes)
            if has(r'сгустк', t): a['echogenic'] = 'со сгустками'
            elif positive(r'взвес\w*|неоднородн\w*\s+жидкост', t): a['echogenic'] = 'со взвесью'
            elif has(r'без\s+взвеси',t):a['echogenic']='анэхогенная'
            elif has(r'однородн\w*\s+жидкост|анэхоген', t): a['echogenic'] = 'анэхогенная'
            if has(r'подпеч[её]ноч|Морисон', t): a.update(location='подпечёночно',beyondPelvis=True)
            elif has(r'боков\w*\s+канал', t): a.update(location='боковой канал',beyondPelvis=True)
            elif has(r'межпетель', t): a.update(location='межпетельно',beyondPelvis=True)
            elif has(r'поддиафрагм', t): a.update(location='поддиафрагмально',beyondPelvis=True)
            elif has(r'позадиматоч|мал\w*\s+таз|дугласов', t): a['location'] = 'малый таз'
            if has(r'сгустк', t) and not has(r'сгустк|гемоперитонеум', conclusion): f.setdefault('flags', []).append(flag('DISCREPANCY'))
        if code == 'OVARIAN_APOPLEXY':
            fluid_rows=[b for b in source if has(r'жидкост',b.text)]
            vals=[float(m.replace(',','.')) for b in fluid_rows for m in re.findall(rf'({NUM})\s*мл',b.text)]
            if vals:a['freeFluidMl']=max(vals);related+=fluid_rows
        if code in {'GALLSTONES','GALLBLADDER_POLYP','ACUTE_CHOLECYSTITIS','CHRONIC_CHOLECYSTITIS'}:
            if code == 'GALLSTONES':
                put(a, 'choledochMm', measured(clinical_text, r'хол[еи]дох\w*'))
                if has(r'билиарн\w*\s+гипертензи|хол[еи]дох\s+расширен', clinical_text): a['ductsDilated'] = True
                if has(r'сладж|эхоген\w*\s+взвесь|осадок', clinical_text): a['sludge'] = True
            else:
                if any(x['code']=='GALLSTONES' for x in found):a['withStones']=True
                elif has(r'конкремент\w*[^.;]{0,25}не\s+(?:выявлен|определ)|без\s+(?:камней|конкремент)',clinical_text):a['withStones']=False
                else:a.pop('withStones',None)
            if code == 'GALLBLADDER_POLYP':
                put(a, 'sessile', explicit_bool(t, r'широк\w*\s+основан', r'на\s+ножке'))
                if has(r'локус\w*\s+кровоток', t): a['vascularized'] = True
            if code == 'ACUTE_CHOLECYSTITIS':
                put(a, 'wallThicknessMm', measured(t, r'стенк\w*'))
                put(a, 'doubleContour', explicit_bool(t,r'двойн\w*\s+контур',r'двойн\w*\s+контур\w*\s+нет|без\s+двойн'))
                if has(r'(?:перивезик|перипузыр)[^.;]*жидкост|жидкост[^.;]*перивезик', t): a['pericholecysticFluid'] = True
                put(a, 'murphy', explicit_bool(t,r'Мерфи\s+положительн',r'Мерфи\s+отрицательн'))
        if code in {'HERNIA'}:
            put(a, 'sizeMm', measured(t, r'грыжев\w*\s+ворот\w*|дефект\w*\s+апоневроз\w*'))
            put(a, 'reducible', explicit_bool(t,r'вправим|вправляется',r'невправим|не\s+вправляется'))
            put(a, 'incarcerated', explicit_bool(t,r'ущемл[её]нн',r'без\s+(?:признаков\s+)?ущемления|признаков\s+ущемления\s+нет'))
            put(a,'obstruction',explicit_bool(t,r'непроходим|маятникообразн',r'без\s+(?:признаков\s+)?(?:кишечн\w*\s+)?непроходим|непроходим\w*[^.;]{0,20}(?:нет|не\s+выявлен)'))
            for pat,val in [(r'предбрюшинн\w*\s+(?:жиров\w*\s+)?клетчат','предбрюшинная клетчатка'),(r'петл\w*\s+тонк\w*\s+киш','петля тонкой кишки'),(r'сальник','сальник')]:
                if positive(pat,t): a['content']=val;break
        if code in {'KIDNEY_STONES','HYDRONEPHROSIS'}:
            if code == 'KIDNEY_STONES':
                structures = [b for b in related if positive(r'конкремент\w*|гиперэхоген\w*\s+(?:структур|включен)', b.text)]
                values = [v[0] for b in structures for v in dimensions(b.text[re.search(r'конкремент|структур|включен',b.text,re.I).start():])]
                if values: a['sizeMm'] = max(values)
                if has(r'мочеточник|интрамуральн', original): a['location'] = 'ureter'
                if has(r'уретерогидронефроз|ЧЛС\s+расширена|признак\w*\s+обструкц',t): a['obstruction'] = True
                elif has(r'ЧЛС\s+не\s+расширен|расширени\w*\s+ЧЛС\s+нет|без\s+обструкц',t): a['obstruction'] = False
            else:
                put(a, 'pelvisMm', measured(t, r'лоханк\w*'))
                put(a, 'ureterDilated', explicit_bool(t,r'мочеточник\s+расширен',r'мочеточник\s+не\s+расширен'))
        if code in {'DEEP_VEIN_THROMBOSIS','POST_THROMBOTIC_CHANGES'}:
            names=[]
            for pat,val in [(r'бедренн','бедренная'),(r'подколенн','подколенная'),(r'задни\w*\s+большеберцов','задние большеберцовые')]:
                if has(pat,original): names.append(val)
            if names: a['vein'] = ', '.join(names)
            if code == 'POST_THROMBOTIC_CHANGES':
                if has(r'полн\w*\s+реканализац|реканализац\w*\s+полная',t): a['recanalization']='полная'
                elif has(r'частичн\w*\s+реканализац|реканализац\w*\s+частичн',t): a['recanalization']='частичная'
            else:
                put(a, 'floating', explicit_bool(t,r'флотир|флотаци',r'не\s+флотир|без\s+флотац'))
                put(a,'occlusive',explicit_bool(t,r'окклюзивн|просвет\s+полностью\s+заполнен',r'неокклюзивн|не\s+окклюзивн'))
        if code == 'SUPERFICIAL_THROMBOPHLEBITIS':
            veins = [v for v in ('БПВ','МПВ','ПДПВ') if has(r'\b'+v+r'\b', original)]
            if veins: a['vein']=', '.join(veins)
            if has(r'ствол', original): a['location']='trunk'
            elif has(r'подфасциальн',original): a['location']='perforatorSubfascial'
            elif has(r'приустьев',original): a['location']='tributaryNearJunction'
            elif has(r'приток',original): a['location']='tributaryDistal'
            m=re.search(rf'({NUM})\s*(мм|см)\s*(?:от|до)\s*(?:СФС|СПС|сафено)',t,re.I)
            if m:a['distanceToJunctionMm']=float(m[1].replace(',','.'))*(10 if m[2].lower()=='см' else 1)
            put(a,'floating',explicit_bool(t,r'флотир',r'не\s+флотир|без\s+флотац'))
        if code == 'VENOUS_INSUFFICIENCY':
            if has(r'варикоз',original):a['varicose']=True
            elif has(r'рефлюкс|недостаточност',original):a['varicose']=False
            for val in ('СФС','СПС'):
                if has(val+r'\s+несостоятельн',t):a['refluxSource']=val
            if has(r'несостоятельност\w*\s+(?:прав\w*\s+|лев\w*\s+)?сафено.подколенн',t):a['refluxSource']='СПС'
            if has(r'несостоятельност\w*\s+(?:прав\w*\s+|лев\w*\s+)?сафено.феморальн',t):a['refluxSource']='СФС'
            put(a,'refluxSec',number(rf'рефлюкс[^.;]{{0,65}}?({NUM})\s*с\b',t))
        if code == 'ARTERIAL_STENOSIS':
            descriptive=' '.join(b.text for b in related if b.section!='conclusion' and (b.side in {side,None} or side=='both') )
            values=re.findall(rf'({NUM})\s*%',descriptive)
            if not values:values=re.findall(rf'({NUM})\s*%',original)
            if values:a['maxStenosisPct']=max(float(v.replace(',','.')) for v in values)
            m=re.search(r'\b(ОБА|ПБА|ГБА|ПкА|ЗББА|ПББА)\b',original)
            if m:a['artery']=m[1]
            if has(r'кровоток\s+магистральн',t):a['bloodFlowType']='магистральный'
            if has(r'без\s+отрицательн\w*\s+динамик|без\s+динамик',clinical_text):a['growth']=False
            if a.get('maxStenosisPct',100)<50 and has(r'гемодинамически\s+значим',conclusion):f.setdefault('flags',[]).append(flag('DISCREPANCY'))
        if code == 'BPH':
            volumes=[b for b in source if not has(r'остаточ|мочев\w*\s+пузыр|семенн',b.text)]
            clean=re.sub(r'\([^)]*(?:норм|N\s*объема)[^)]*\)','', ' '.join(b.text for b in volumes),flags=re.I)
            put(a,'volumeCm3',number(rf'(?:об[ъь][её]м\w*(?:\s+железы)?|\bV(?:\s+предстательной\s+железы)?)\s*[:=—–-]?\s*({NUM})\s*(?:см|мл|куб)',clean))
            put(a,'intravesicalMm',measured(t,r'внутрипузырн\w*\s+протрузи\w*'))
            if has(r'простатит',t):a['prostatitisPattern']=True
        if code == 'BPH_URINARY_RETENTION':
            put(a,'residualUrineMl',number(rf'остаточн\w*\s+моч\w*\s*\(?\s*({NUM})\s*мл',t))
        if code == 'ENDOMETRIAL_HYPERPLASIA':
            explicit=measured(t,r'эндометрий\s*[:—–-]')
            put(a,'thicknessMm',explicit if explicit is not None else measured(t,r'эндометри\w*|м\s*[-–]\s*эхо'))
            if has(r'неоднород',t):a['heterogeneous']=True
            if has(r'тонк|не\s+соответств\w*\s+дню',t) and a.get('thicknessMm',100)<6:a.update(thin=True,uncertain=True)
        if code == 'CERVICAL_RETENTION_CYSTS':
            vals=[]
            for b in related:
                m=re.search(r'кист\w*|анэхогенн\w*\s+включени\w*|полост\w*',b.text,re.I)
                if m:vals += [v[0] for v in dimensions(b.text[m.start():])]
            if not vals:
                vals=[v[0] for b in related if has(r'ретенционн',b.text) for v in dimensions(b.text)]
            if vals:a['sizeMm']=max(vals)
            put(a,'deformsCanal',explicit_bool(t,r'канал[^.;]*деформирован',r'канал[^.;]*не\s+(?:деформирован|расширен)|канал\s+сомкнут'))
            if has(r'эндоцервикоз',original):f.setdefault('flags',[]).append(flag('OUTDATED_TERM'))
        if code == 'BILIARY_SLUDGE' and has(r'холестаз',original):f.setdefault('flags',[]).append(flag('INCORRECT_TERM'))
        if code == 'HEPATIC_STEATOSIS':
            if not has(r'гепатоз|стеатоз|жиров\w*\s+инфильтрац',conclusion):a['uncertain']=True;f.setdefault('flags',[]).append(flag('DISCREPANCY'))
            if has(r'гепатомегал|печень\s*:\s*увеличен',t):a['hepatomegaly']=True
            if has(r'диффузн\w*\s+изменени\w*\s+поджелудочн',t):a['pancreasChanges']=True
        if code == 'IUD_MALPOSITION':
            for pat,val in [(r'частичн\w*\s+экспульс','partialExpulsion'),(r'внедрен','myometrium'),(r'не\s+визуализ','notVisualized'),(r'цервикальн','cervical'),(r'низк','low')]:
                if has(pat,original):a['position']=val;break
        if code=='UTERINE_CAVITY_FLUID':
            for p,v in [(r'серозометр','serous'),(r'гематометр','blood'),(r'пиометр','pus')]:
                if has(p,original):a['content']=v
        if code=='UTERINE_PROLAPSE':
            put(a,'grade',int(number(r'(\d)\s*(?:степен|ст\.)',original)) if number(r'(\d)\s*(?:степен|ст\.)',original) is not None else None)
        if code=='PELVIC_VARICOSE_VEINS':
            vals=[v[0] for b in anchors for v in dimensions(b.text)]
            if vals:a['veinDiameterMm']=max(vals)
        if code=='CERVICAL_POLYP' and has(r'активн\w*\s+кровоток|локус\w*\s+кровоток',t):a['vascularized']=True
        if code=='LOW_OVARIAN_RESERVE':
            put(a,'afc',int(number(r'КАФ\s*[:—–-]?\s*(\d+)',full)) if number(r'КАФ\s*[:—–-]?\s*(\d+)',full) is not None else None)
            if 'afc' not in a:
                counts=[]
                for s in ('right','left'):
                    vals=[number(r'(\d+)\s+фолликул',b.text) for b in source if b.organ=='ovary' and b.side==s]
                    vals=[x for x in vals if x is not None]
                    if vals:counts.append(max(vals))
                if len(counts)==2:a['afc']=int(sum(counts))
        if code=='SOFT_TISSUE_INFLAMMATION':
            if has(r'лев\w*\s+стоп',original):a['location']='левая стопа'
            elif has(r'прав\w*\s+стоп',original):a['location']='правая стопа'
        if code=='LIVER_HEMANGIOMA':
            bs=[b for b in source if has(r'гемангиом|гиперэхоген\w*\s+(?:аваскулярн\w*\s+)?образован',b.text)]
            vals=[v[0] for b in bs for v in dimensions(b.text)]
            if vals:a['sizeMm']=max(vals)
            if any(has(r'четк\w*\s+(?:ровн\w*\s+)?контур|ч[её]ткими',b.text) and not has(r'неоднород',b.text) for b in bs):a['atypical']=False
            related+=bs
        if code=='HYDROSALPINX':
            vals=[v[0] for b in anchors for v in dimensions(b.text)]
            if vals:a['sizeMm']=max(vals)
            if any('?' in b.text for b in anchors):a['uncertain']=True
        if code == 'UNRECOGNIZED_ABNORMALITY':
            cs=[b for b in anchors if b.section=='conclusion' and has(r'аневризм',b.text)]
            if cs:a['text']=cs[0].text.rstrip('. ')
        # Evidence covers every descriptive/context attribute that was considered.
        coverage=anchors+related
        if patient_attrs:coverage+= [b for b in source if has(r'менопауз|цикла|ДПМ|ХГЧ|беременность|выделен|\bКОК\b|\bЗГТ\b',b.text)]
        if coverage:f['evidence']=evidence(coverage)
        a.update(extract_declared(t,items[code]))
        f['attributes']={k:v for k,v in a.items() if k in items[code].get('attributes',a.keys()) and v is not None}
        f.setdefault('flags',[])
        if code in {'BREAST_LESION','THYROID_NODULE'} and ('birads' if code=='BREAST_LESION' else 'tirads') not in a:f['flags'].append(flag('INCOMPLETE'))
        if code=='SUPERFICIAL_THROMBOPHLEBITIS' and a.get('location')=='trunk' and 'distanceToJunctionMm' not in a:f['flags'].append(flag('INCOMPLETE'))
        if code=='ENDOMETRIAL_HYPERPLASIA' and a.get('menopause') and 'thicknessMm' not in a:f['flags'].append(flag('INCOMPLETE'))
        # Same-side conclusion presence; broad summary without side can corroborate.
        relevant_conclusions=[b for b in source if b.section=='conclusion' and (not side or b.side in {None,side,'both'})]
        patterns_for_code=[re.compile(inflected_pattern(s),re.I) for s in [items[code]['name']]+items[code]['synonyms']]
        affirmed=any(any((m:=p.search(b.text)) and not negates(b.text,m.start(),m.end()) for p in patterns_for_code) for b in relevant_conclusions)
        if conclusion and not affirmed:f['flags'].append(flag('DISCREPANCY'))
        if code=='VENOUS_INSUFFICIENCY' and ('refluxSec' not in a or 'refluxSource' not in a):f['flags'].append(flag('INCOMPLETE'))
        if code=='VENOUS_INSUFFICIENCY' and has(r'несостоятельност',conclusion) and not any(has(r'рефлюкс|ретроградн|проб\w*\s+Вальсальв',b.text) for b in related if b.section!='conclusion'):f['flags'].append(flag('DISCREPANCY'))
        if code in {'SOFT_TISSUE_INFLAMMATION','PELVIC_VARICOSE_VEINS'} and not any(b.section!='conclusion' and any(p.search(b.text) for p in patterns_for_code) for b in source):f['flags'].append(flag('DISCREPANCY'))
        if code=='PCOM' and a.get('volumeCalculated') and has(r'мультифолликуляр',conclusion):f['flags'].append(flag('DISCREPANCY'))
        if code=='LOW_OVARIAN_RESERVE' and a.get('afc',0)>5:f['flags'].append(flag('DISCREPANCY'))
        if code=='BREAST_LESION':
            ct=' '.join(b.text for b in relevant_conclusions)
            for key,pattern in [('inflammation',r'мастит|гипереми|воспален'),('suspiciousLymphNodes',r'лимфоуз|лимфатическ'),('skinThickening',r'кож'),('ductContent',r'проток')]:
                if a.get(key) and not has(pattern,ct):f['flags'].append(flag('DISCREPANCY'))
        if code=='PELVIC_VARICOSE_VEINS' and has(r'(?:N|норм\w*)\s*(?:до)?\s*7\s*мм',original) and 5<a.get('veinDiameterMm',0)<=7:f['flags'].append(flag('TEMPLATE_NORM'))
        f['flags']=list({x['code']:x for x in f['flags']}.values())

    if any(f['code']=='GALLSTONES' for f in found):found=[f for f in found if f['code']!='BILIARY_SLUDGE']
    for code in {'HYDROSALPINX'}:
        sided=[f for f in found if f['code']==code and f['attributes'].get('side')]
        if sided:found=[f for f in found if f['code']!=code or f['attributes'].get('side')]
    # Merge repeated mentions; keep different categories and locations separate.
    groups={}
    for f in found:
        a=f['attributes'];key=(f['code'],)+(tuple(a.get(k) for k in ('side','location','figo','birads','orads','tirads')))
        if key not in groups:groups[key]=f;continue
        old=groups[key]
        for k,v in a.items():
            if k in {'sizeMm','maxStenosisPct'} and k in old['attributes']:v=max(v,old['attributes'][k])
            old['attributes'][k]=v
        start=min(old['evidence']['start'],f['evidence']['start']);end=max(old['evidence']['end'],f['evidence']['end'])
        old['evidence']={'text':full[start:end],'start':start,'end':end}
        old['flags']=list({x['code']:x for x in old['flags']+f['flags']}.values())
    merged=list(groups.values())
    # Preserve a distinct occluded arterial segment instead of attaching its
    # name to a maximum stenosis measured in another artery.
    if study=='LOWER_LIMB_VESSELS' and 'ARTERIAL_STENOSIS' in items:
        occlusions=[b for b in source if b.section!='conclusion' and has(r'окклюзи|кровоток[^.;]*не\s+(?:лоцир|регистр)',b.text) and has(r'ПББА|ЗББА|ОБА|ПБА|артер',b.text)]
        for b in occlusions:
            m=re.search(r'\b(ПББА|ЗББА|ОБА|ПБА)\b',b.text)
            if not m:continue
            for f in merged:
                if f['code']=='ARTERIAL_STENOSIS' and f['attributes'].get('side')==b.side:f['attributes'].pop('occlusion',None)
            a={'artery':m[1],'occlusion':True,'uncertain':has(r'\?|кальциноз|достоверно\s+не',b.text)}
            if b.side:a['side']=b.side
            merged.append({'code':'ARTERIAL_STENOSIS','attributes':a,'evidence':evidence([b]),'flags':[flag('DISCREPANCY')]})
    if study=='LOWER_LIMB_VESSELS':
        for code in ('ARTERIAL_STENOSIS',):
            right=[f for f in merged if f['code']==code and f['attributes'].get('side')=='right']
            left=[f for f in merged if f['code']==code and f['attributes'].get('side')=='left']
            if len(right)==len(left)==1 and {k:v for k,v in right[0]['attributes'].items() if k!='side'}=={k:v for k,v in left[0]['attributes'].items() if k!='side'}:
                f,g=right[0],left[0];f['attributes']['side']='both'
                start=min(f['evidence']['start'],g['evidence']['start']);end=max(f['evidence']['end'],g['evidence']['end'])
                f['evidence']={'start':start,'end':end,'text':full[start:end]};merged.remove(g)
    return merged, list({(r['code'],r['reason'],r['evidence']['text']):r for r in rejected if r['code'] in items}.values())
