"""Declarative dictionary extensions. Labels are literal text, never executable code.

New codes automatically use the common mention/negation/size/side pipeline.
Optional extractionProfile reuses a specialized anatomical adapter; optional
attributeExtractors adds labeled numeric, string or boolean facts without code.
The prose extraction/notThis fields are documentation, not executable rules.
"""
import math
import re
from .contracts import ContractError

PROFILES = frozenset({
    'ENDOMETRIAL_POLYP','ENDOMETRIAL_HYPERPLASIA','UTERINE_FIBROID',
    'OVARIAN_LESION','ECTOPIC_PREGNANCY','OVARIAN_TORSION','OVARIAN_APOPLEXY',
    'CERVICAL_POLYP','GALLSTONES','GALLBLADDER_POLYP','ACUTE_CHOLECYSTITIS',
    'FREE_FLUID','BREAST_LESION','THYROID_NODULE','DEEP_VEIN_THROMBOSIS',
    'VENOUS_INSUFFICIENCY','ARTERIAL_STENOSIS','HERNIA','HYDRONEPHROSIS',
    'KIDNEY_STONES','BPH_URINARY_RETENTION',
})


def validate_extensions(item):
    profile=item.get('extractionProfile')
    if profile is not None and (not isinstance(profile,str) or profile not in PROFILES):
        raise ContractError('Словарь: неизвестный extractionProfile')
    if profile is not None and 'attributes' not in item:
        raise ContractError('extractionProfile требует attributes')
    specs=item.get('attributeExtractors',{})
    if not isinstance(specs,dict):raise ContractError('attributeExtractors должен быть объектом')
    if specs and 'attributes' not in item:raise ContractError('attributeExtractors требует attributes')
    for key,spec in specs.items():
        if key not in item['attributes'] or not isinstance(spec,dict):
            raise ContractError('attributeExtractors: неизвестный атрибут или неверное описание')
        if set(spec)-{'type','labels','unit','multiplier','positive','negative'}:
            raise ContractError('attributeExtractors: неизвестное поле')
        kind=spec.get('type')
        if not isinstance(kind,str) or kind not in {'number','integer','string','boolean'}:raise ContractError('attributeExtractors: неизвестный type')
        fields=['positive','negative'] if kind=='boolean' else ['labels']
        for field in fields:
            values=spec.get(field,[])
            if not isinstance(values,list) or any(not isinstance(v,str) or not v.strip() or len(v)>200 for v in values):
                raise ContractError('attributeExtractors: требуются непустые строковые метки длиной до 200')
        if not any(spec.get(f) for f in fields):raise ContractError('attributeExtractors: отсутствуют метки')
        if 'unit' in spec and (kind not in {'number','integer'} or not isinstance(spec['unit'],str) or not spec['unit'].strip()):
            raise ContractError('attributeExtractors: некорректная единица')
        multiplier=spec.get('multiplier',1)
        if type(multiplier) not in {int,float} or not math.isfinite(multiplier) or multiplier<=0:
            raise ContractError('attributeExtractors: multiplier должен быть положительным конечным числом')


def literal(value):
    return r'(?<!\w)'+r'\s+'.join(re.escape(w) for w in value.split())+r'(?!\w)'


def validate_declared_attributes(attrs,item):
    for name,spec in item.get('attributeExtractors',{}).items():
        if name not in attrs:continue
        value=attrs[name];kind=spec['type']
        valid=(kind=='number' and type(value) in {int,float} and math.isfinite(value)
               or kind=='integer' and type(value) is int
               or kind=='boolean' and type(value) is bool
               or kind=='string' and isinstance(value,str))
        if not valid:raise ContractError(f'{name}: значение не соответствует attributeExtractors.type')


def extract_declared(text,item):
    attrs={}
    for key,spec in item.get('attributeExtractors',{}).items():
        kind=spec['type']
        if kind=='boolean':
            # Negative explicit label wins; positive substring inside a negated
            # statement must never become True.
            if any(re.search(literal(v),text,re.I) for v in spec.get('negative',[])):attrs[key]=False
            elif any(not re.search(r'(?:\bне|\bнет|\bбез)\s*$',text[:m.start()],re.I)
                     for v in spec.get('positive',[]) for m in re.finditer(literal(v),text,re.I)):attrs[key]=True
            continue
        values=[]
        for label in spec['labels']:
            pattern=literal(label)+r'\s*[:=—-]?\s*'
            if kind=='string':pattern+=r'([^,;.!?\n]+)'
            else:
                pattern+=r'([+-]?\d+(?:[.,]\d+)?)'
                if spec.get('unit'):pattern+=r'\s*'+re.escape(spec['unit'])+r'(?!\w)'
                else:pattern+=r'(?![\w.,])'
            for m in re.finditer(pattern,text,re.I):
                if kind=='string':value=m[1].strip()
                else:
                    value=float(m[1].replace(',','.'))*spec.get('multiplier',1)
                    if not math.isfinite(value):continue
                    value=round(value,6)
                    if kind=='integer':
                        if not value.is_integer():continue
                        value=int(value)
                values.append(value)
        # Conflicting values stay unknown, rather than arbitrary last-wins.
        if values and all(v==values[0] for v in values):attrs[key]=values[0]
    return attrs
