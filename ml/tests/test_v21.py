import copy
import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from app.asgi import create_app
from app.benchmark_v2 import score
from app.clinical import analyze_protocol
from app.clinical_v2 import context_attributes
from app.contracts import ContractError
from app.demo import docx
from app.dictionary import DEFAULT_DICTIONARY, enrich_remote, load_dictionary
from app.mis import build_event
from app.parser import parse_text
from app.processing import process_event
from app.service import MLService
from app.validation import validate_for_dictionary


class V21Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.dictionary=load_dictionary(DEFAULT_DICTIONARY)

    def extract(self,text,study):
        parsed=parse_text(text)
        found,nt=analyze_protocol(parsed,text,study,self.dictionary)
        for f in found:
            e=f['evidence'];self.assertEqual(parsed['full_text'][e['start']:e['end']],e['text'])
        return found,nt

    def test_dictionary_has_48_active_codes_and_original_policies(self):
        self.assertEqual(self.dictionary['version'],'dict-v2.1')
        self.assertEqual(len(self.dictionary['findings']),48)
        self.assertTrue(all(f['active'] for f in self.dictionary['findings']))
        self.assertIn('returnPolicy',self.dictionary['ml'])

    def test_omitted_description_fact_survives_normal_conclusion(self):
        f,_=self.extract('Описание\nПолип эндометрия 13 мм.\nЗаключение\nПатологии не выявлено.','PELVIS_FEMALE')
        self.assertEqual(f[0]['attributes']['sizeMm'],13)
        self.assertIn({'code':'DISCREPANCY'},f[0]['flags'])

    def test_description_negated_in_conclusion_is_discrepancy(self):
        f,_=self.extract('Описание\nПолип эндометрия 13 мм.\nЗаключение\nПолип эндометрия не выявлен.','PELVIS_FEMALE')
        self.assertTrue(f)
        self.assertIn({'code':'DISCREPANCY'},f[0]['flags'])

    def test_hernia_negative_attribute_preserves_finding(self):
        f,_=self.extract('Заключение\nПаховая грыжа справа, ворота 17 мм, вправимая, без признаков ущемления.','SOFT_TISSUE')
        self.assertEqual(f[0]['code'],'HERNIA');self.assertFalse(f[0]['attributes']['incarcerated'])

    def test_kwak_category_and_units(self):
        f,_=self.extract('Описание\nУзел слева 1.7х1.2 см.\nЗаключение\nУзел левой доли щитовидной железы, TI-RADS 4c.','THYROID')
        a=f[0]['attributes'];self.assertEqual((a['sizeMm'],a['tirads'],a['tiradsRaw'],a['tiradsSystem']),(17,5,'4c','KWAK'))

    def test_superficial_thrombus_is_not_deep_thrombus(self):
        f,_=self.extract('Заключение\nТромбофлебит ствола БПВ слева, тромб в 4 см от СФС, не флотирует.','LOWER_LIMB_VESSELS')
        self.assertNotIn('DEEP_VEIN_THROMBOSIS',[x['code'] for x in f])
        a=next(x['attributes'] for x in f if x['code']=='SUPERFICIAL_THROMBOPHLEBITIS')
        self.assertEqual(a['distanceToJunctionMm'],40);self.assertFalse(a['floating'])

    def test_new_code_and_attribute_dsl(self):
        d=copy.deepcopy(self.dictionary)
        d['findings'].append({'code':'DEMO_NEW','name':'Учебный признак','synonyms':['учебная находка'],'studyTypes':['SOFT_TISSUE'],
             'attributes':['widthMm'],'attributeExtractors':{'widthMm':{'type':'number','labels':['ширина'],'unit':'см','multiplier':10}}})
        text='Заключение\nУчебная находка, ширина 2 см.'
        f,_=analyze_protocol(parse_text(text),text,'SOFT_TISSUE',d)
        self.assertEqual(next(x['attributes']['widthMm'] for x in f if x['code']=='DEMO_NEW'),20)

    def test_inactive_code_is_not_returned(self):
        d=copy.deepcopy(self.dictionary)
        for f in d['findings']:
            if f['code']=='HERNIA':f['active']=False
        text='Заключение\nПаховая грыжа справа.'
        self.assertFalse(analyze_protocol(parse_text(text),text,'SOFT_TISSUE',d)[0])

    def test_remote_root_is_not_discarded(self):
        d=enrich_remote(self.dictionary)
        self.assertEqual(d['ml'],self.dictionary['ml']);self.assertEqual(d['flags'],self.dictionary['flags'])

    def test_remote_other_version_not_enriched_from_current(self):
        d=enrich_remote({'version':'dict-future','findings':[{'code':'HERNIA','name':'New','synonyms':['new'],'studyTypes':['SOFT_TISSUE']}]})
        self.assertNotIn('attributes',d['findings'][0]);self.assertEqual(d['version'],'dict-future')

    def test_year_never_becomes_cycle_day(self):
        a=context_attributes('24.08.2026 день цикла 16',None)
        self.assertEqual(a['cycleDay'],16);self.assertNotIn('monthsSinceLmp',a)
        self.assertEqual(context_attributes('06.02.2026 день цикла 215',None)['monthsSinceLmp'],7)

    def test_negative_sludge_and_other_stone_do_not_cancel_each_other(self):
        f,_=self.extract('Описание\nЖелчный пузырь. Эховзвеси и конкрементов достоверно не определяется.\nЗаключение\nБез особенностей.','ABDOMEN')
        self.assertNotIn('BILIARY_SLUDGE',[x['code'] for x in f])

    def test_menopause_measurement_kept_even_if_missing_in_synthetic_gold(self):
        f,_=self.extract('Описание\nМенопауза 5 лет. Эндометрий 3 мм.\nЗаключение\nБез патологии.','PELVIS_FEMALE')
        a=next(x['attributes'] for x in f if x['code']=='ENDOMETRIAL_HYPERPLASIA')
        self.assertEqual(a['thicknessMm'],3);self.assertTrue(a['fromMeasurement'])

    def test_optional_does_not_mask_duplicate_prediction(self):
        f={'code':'X','attributes':{'side':'left'}}
        row={'file':'test','expected':{'findings':[f]},'optional':{'findings':[]},'prediction':{'findings':[f,f]},'seconds':0}
        m=score([row])['fullFacts'];self.assertEqual((m['tp'],m['fp'],m['fn']),(1,1,0))

    def test_failed_document_counts_as_missed_findings(self):
        row={'file':'bad.docx','expected':{'findings':[{'code':'X'}]},'prediction':{'status':'FAILED'},'seconds':0}
        report=score([row])
        self.assertEqual(report['fullFacts']['fn'],1)
        self.assertEqual(report['failedDocuments'],['bad.docx'])
        self.assertIsNone(score([])['timingSeconds']['mean'])

    def test_future_full_dictionary_uses_return_policy(self):
        d=copy.deepcopy(self.dictionary);d['version']='dict-v3'
        text='Заключение\nBI-RADS 1 справа.'
        f,nt=analyze_protocol(parse_text(text),text,'BREAST',d)
        self.assertFalse(f);self.assertTrue(any(x['reason']=='NORMAL' for x in nt))

    def test_inactive_arterial_code_not_reintroduced_by_profile(self):
        d=copy.deepcopy(self.dictionary)
        for f in d['findings']:
            if f['code']=='ARTERIAL_STENOSIS':f['active']=False
        text='Описание\nАртерии нижних конечностей. Справа ПБА: окклюзия.\nЗаключение\nОкклюзия ПБА справа.'
        f,_=analyze_protocol(parse_text(text),text,'LOWER_LIMB_VESSELS',d)
        self.assertNotIn('ARTERIAL_STENOSIS',[x['code'] for x in f])

    def test_superficial_thrombosis_does_not_hide_concurrent_deep_thrombosis(self):
        f,_=self.extract('Описание\nТромбоз глубоких вен справа.\nЗаключение\nТромбофлебит БПВ слева.','LOWER_LIMB_VESSELS')
        self.assertIn('DEEP_VEIN_THROMBOSIS',[x['code'] for x in f])
        self.assertIn('SUPERFICIAL_THROMBOPHLEBITIS',[x['code'] for x in f])

    def test_invalid_menstrual_date_does_not_abort_extraction(self):
        f,_=self.extract('Дата осмотра: 01.09.2026\nДПМ: 35.08.2026\nЗаключение\nПолип эндометрия 8 мм.','PELVIS_FEMALE')
        self.assertIn('ENDOMETRIAL_POLYP',[x['code'] for x in f])

    def test_past_deep_thrombosis_does_not_become_current(self):
        f,_=self.extract('Описание\nСо слов — тромбоз глубоких вен слева 2 года назад.\nЗаключение\nПосттромботические изменения слева. Данных за острый тромбоз не получено.','LOWER_LIMB_VESSELS')
        self.assertNotIn('DEEP_VEIN_THROMBOSIS',[x['code'] for x in f])

    def test_figo_conflict_flag_without_reclassifying_doctor(self):
        f,_=self.extract('Описание\nМиоматозный узел тип 6 по FIGO -22*23 мм.\nЗаключение\nМиома матки тип 5 по FIGO.','PELVIS_FEMALE')
        self.assertTrue(any({'code':'DISCREPANCY'} in x['flags'] for x in f if x['code']=='UTERINE_FIBROID'))

    def test_negative_obstruction_is_an_attribute_not_a_positive_sign(self):
        f,_=self.extract('Заключение\nПаховая грыжа справа, без признаков кишечной непроходимости.','SOFT_TISSUE')
        self.assertIsNot(next(x['attributes'] for x in f if x['code']=='HERNIA').get('obstruction'),True)

    def test_menopause_without_thickness_is_incomplete(self):
        f,_=self.extract('Описание\nМенопауза 6 лет.\nЗаключение\nГиперплазия эндометрия.','PELVIS_FEMALE')
        self.assertIn({'code':'INCOMPLETE'},next(x['flags'] for x in f if x['code']=='ENDOMETRIAL_HYPERPLASIA'))

    def test_fastapi_accept_retry_annul_and_malformed(self):
        class Backend:
            def send_once(self,result):pass
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);path=p/'sample.docx';docx(path,['Описание','Полип эндометрия 13 мм.'])
            service=MLService(p/'queue.sqlite3',Backend(),lambda:self.dictionary)
            event=build_event({'eventId':'v21-1','eventType':'PROTOCOL_SIGNED','patient':{'externalId':'p','fullName':'Пациент 001','birthDate':'1999-01-01','sex':'F'},'protocol':{'externalId':'q','version':1,'studyType':'PELVIS_FEMALE','studyDate':'2026-09-08'}},path)
            with TestClient(create_app(service)) as client:
                self.assertEqual(client.post('/api/mis/events',json=event).status_code,202)
                result=service.accept(event)
                self.assertEqual(result['status'],'DONE');self.assertEqual(result['dictionaryVersion'],'dict-v2.1')
                self.assertIn({'code':'NO_CONCLUSION'},result['flags'])
                validate_for_dictionary(result,self.dictionary)
                self.assertEqual(result['patient'],event['patient']);self.assertEqual(result['protocol'],event['protocol'])
                self.assertEqual(client.post('/api/mis/events',json=event).json()['resultId'],result['resultId'])
                bad=copy.deepcopy(event);bad['patient']['fullName']='Другой'
                self.assertEqual(client.post('/api/mis/events',json=bad).status_code,409)
                annul=copy.deepcopy(event);annul.update(eventId='v21-annul',eventType='PROTOCOL_ANNULLED');annul.pop('contentBase64');annul.pop('fileName')
                self.assertEqual(client.post('/api/mis/events',json=annul).json()['status'],'ANNULLED')
                self.assertEqual(client.post('/api/mis/events',content='bad',headers={'Content-Type':'application/json'}).status_code,400)
                self.assertEqual(client.post('/api/mis/events',content='bad').status_code,415)
                self.assertEqual(client.get('/api/mis/events/missing').status_code,404)
                self.assertEqual(client.post('/api/mis/events/missing/retry').status_code,404)
                self.assertEqual(client.get('/health').status_code,200)

    def test_backend_flags_rejected_from_ml(self):
        from app.contracts import validate_result
        result=json.loads((Path(__file__).parents[1]/'examples/result-positive.json').read_text('utf-8'))
        result['flags']=[{'code':'MINOR'}]
        with self.assertRaises(ContractError):validate_result(result)


if __name__=='__main__':unittest.main()
