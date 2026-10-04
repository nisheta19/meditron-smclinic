"""One output validator used by both live processing and release preparation."""
import json
from .contracts import ContractError, validate_result
from .dictionary import normalize_dictionary, uses_v2_contract
from .extensions import validate_declared_attributes

MEASUREMENTS = {'sizeMm','thicknessMm','volumeMl','freeFluidMl','choledochMm',
                'wallThicknessMm','pelvisMm','residualUrineMl','volumeCm3','ovaryVolumeCm3',
                'intravesicalMm','distanceToJunctionMm','diameterMm','veinDiameterMm','refluxSec','monthsSinceLmp'}
BOOLEANS = {'uncertain','fromMeasurement','menopause','functional','solid','papillary',
            'vascularized','septated','growth','recurrent','deformsCavity','prolapsing',
            'sessile','mobile','obstruction','pericholecysticFluid','withStones',
            'inflammation','hcgPositive','freeFluid','suspiciousLymphNodes','floating',
            'occlusive','occlusion','reducible','incarcerated','ureterDilated','thin','heterogeneous',
            'bleeding','bilateral','iudInPlace','noFlow','whirlpool','deformsCanal','lowFrequencyProbe',
            'volumeCalculated','dominantStructure','onCOC','hrt','sludge','porcelain','doubleContour',
            'murphy','hepatomegaly','pancreasChanges','atypical','beyondPelvis','skinThickening',
            'varicose','prostatitisPattern','degeneration','pedicleTorsion','compression','ductsDilated','benignChanges','ductContent'}
LIMITS = {'birads':(0,6),'orads':(0,5),'tirads':(1,5),'figo':(0,8),'grade':(1,4)}


def validate_for_dictionary(result, dictionary):
    validate_result(result)
    if uses_v2_contract(dictionary) and result.get('status')=='DONE' and not isinstance(result.get('flags'),list):
        raise ContractError('DONE v2 требует flags')
    items={i['code']:i for i in normalize_dictionary(dictionary)}
    for key in ('findings','notTriggered'):
        for finding in result.get(key,[]):
            item=items.get(finding['code'])
            if not item or result['protocol']['studyType'] not in item['studyTypes']:
                raise ContractError('Код или studyType отсутствует в словаре')
            if uses_v2_contract(dictionary) and not item.get('active',True):raise ContractError('Неактивный код')
            attrs=finding.get('attributes',{})
            if 'attributes' in item and set(attrs)-set(item['attributes']):
                raise ContractError('Неизвестный атрибут находки')
            validate_declared_attributes(attrs,item)
            for name,value in attrs.items():
                if value is None:raise ContractError('Отсутствующий атрибут нужно опустить')
                if name in {'cycleDay','follicleCount','afc','uterusWeeks'} and (type(value) is not int or value<0):raise ContractError('Требуется неотрицательное целое число')
                if name in MEASUREMENTS and (type(value) not in (int,float) or not 0<=value<float('inf')):
                    raise ContractError('Некорректное измерение')
                if name in BOOLEANS and type(value) is not bool:
                    raise ContractError(f'{name}: требуется boolean')
                if name in LIMITS and (type(value) is not int or not LIMITS[name][0]<=value<=LIMITS[name][1]):
                    raise ContractError(f'{name}: недопустимая категория')
                if name=='count' and value != 'множественные' and (type(value) is not int or value<1):
                    raise ContractError('count: требуется положительное целое число')
                if name in {'stenosisPct','maxStenosisPct'} and (type(value) not in (int,float) or not 0<=value<=100):
                    raise ContractError('stenosisPct: требуется процент 0–100')
                if name=='side' and value not in {'left','right','both'}:
                    raise ContractError('Некорректная сторона')
                if name=='biradsSub' and (value not in {'a','b','c'} or attrs.get('birads')!=4):
                    raise ContractError('biradsSub: подкатегория допустима только для BI-RADS 4')
                if name=='tiradsSystem' and value not in {'EU','ACR','KWAK','UNKNOWN'}:
                    raise ContractError('Некорректная система TI-RADS')
                if name=='suspiciousFeatures' and (not isinstance(value,list) or any(not isinstance(v,str) for v in value)):
                    raise ContractError('suspiciousFeatures: требуется массив строк')
    try:
        json.dumps(result,allow_nan=False)
    except (ValueError,TypeError) as exc:
        raise ContractError('Результат содержит недопустимое значение JSON') from exc
