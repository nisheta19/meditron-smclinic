"""Generalized synthetic regressions, with no source protocol text or identifiers."""
from copy import deepcopy
import unittest

from app.clinical import analyze_protocol
from app.contracts import ContractError
from app.dictionary import DEFAULT_DICTIONARY, load_dictionary, normalize_dictionary, enrich_remote
from app.parser import parse_text
from app.extensions import extract_declared,validate_declared_attributes


class FactExtractionV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.dictionary=load_dictionary(DEFAULT_DICTIONARY.with_name('findings-dictionary-v1.yaml'))

    def run_text(self,text,study,code):
        parsed=parse_text(text)
        findings,_=analyze_protocol(parsed,text,study,self.dictionary)
        for f in findings:
            e=f['evidence'];self.assertEqual(parsed['full_text'][e['start']:e['end']],e['text'])
        return [f['attributes'] for f in findings if f['code']==code]

    def test_wrapped_size_and_cubic_centimeters(self):
        cases=[('мл',41),('см3',52),('см³',63),('куб.см.',74),('см.куб.',85)]
        for unit,value in cases:
            with self.subTest(unit=unit):
                rows=self.run_text(f'Описание\nПредстательная железа. Объем {value}{unit}\nУзел объемом 3 мл.\nЗаключение\nДГПЖ.','PROSTATE','BPH_URINARY_RETENTION')
                self.assertEqual(rows,[{'volumeMl':value}])

    def test_residual_volume_after_initial_in_same_sentence(self):
        rows=self.run_text('Описание\nПредстательная железа V=47 мл.\nМочевой пузырь V нач 240 мл, V остаточ. - 93 мл.\nЗаключение\nДГПЖ.','PROSTATE','BPH_URINARY_RETENTION')
        self.assertEqual(rows,[{'volumeMl':47,'residualUrineMl':93}])

    def test_inverted_hyperplasia_phrase_without_abbreviation(self):
        rows=self.run_text('Заключение\nГиперплазия и увеличение объема предстательной железы.','PROSTATE','BPH_URINARY_RETENTION')
        self.assertEqual(len(rows),1)

    def test_interstitial_nodes_count_and_maximum(self):
        rows=self.run_text('Описание\nМатка. Интерстициальные узлы 13х9 мм, 21х15 мм, 8 мм.\nЗаключение\nМиома матки.','PELVIS_FEMALE','UTERINE_FIBROID')
        self.assertEqual(rows[0]['sizeMm'],21)
        self.assertEqual(rows[0]['count'],3)

    def test_identical_size_nodes_in_separate_paragraphs_count_twice(self):
        rows=self.run_text('Описание\nМатка. Интрамуральный узел 11 мм.\nИнтрамуральный узел 11 мм.\nЗаключение\nМиома матки.','PELVIS_FEMALE','UTERINE_FIBROID')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['count'],2)

    def test_explicit_figo_types_in_one_sentence_stay_separate(self):
        rows=self.run_text('Описание\nМатка. Интрамурально-субсерозный узел 32х21 мм (5 тип), в области правого ребра субсерозный узел 19х14 мм (6 тип).\nЗаключение\nМиома матки.','PELVIS_FEMALE','UTERINE_FIBROID')
        self.assertEqual({(r['sizeMm'],r['figo']) for r in rows},{(32,5),(19,6)})

    def test_different_thyroid_categories_never_share_size(self):
        for small,large in [(6,22),(11,31),(15,39)]:
            rows=self.run_text(f'Описание\nПравая доля. Узел {small} мм, EU-TIRADS 5.\nУзел {large} мм, EU-TIRADS 2.\nЗаключение\nУзлы правой доли.','THYROID','THYROID_NODULE')
            self.assertEqual({(r['sizeMm'],r['tirads']) for r in rows},{(small,5),(large,2)})

    def test_node_count_ignores_normal_endometrial_measurement(self):
        rows=self.run_text('Описание\nЭндометрий: М-эхо 14 мм, образование 8х5 мм, образование 3х2 мм.\nЗаключение\nПолипоз эндометрия.','PELVIS_FEMALE','ENDOMETRIAL_POLYP')
        self.assertEqual(rows[0]['count'],2)
        self.assertEqual(rows[0]['sizeMm'],8)

    def test_bilateral_cysts_one_sentence_and_global_category(self):
        rows=self.run_text('Описание\nВ обеих молочных железах анэхогенные округлые образования, справа в количестве трех до 9 мм, слева в количестве двух до 6 мм.\nЗаключение\nКатегория BI-RADS 2.','BREAST','BREAST_LESION')
        self.assertEqual({(r['side'],r['sizeMm'],r['count'],r['birads']) for r in rows},{('right',9,3,2),('left',6,2,2)})

    def test_size_prefix_d_is_diameter_not_right_side(self):
        rows=self.run_text('Описание\nЛевая молочная железа. Киста d - 6 мм.\nЗаключение\nBI-RADS 2 слева.','BREAST','BREAST_LESION')
        self.assertEqual(rows[0]['side'],'left')

    def test_bilateral_categories_with_leading_side(self):
        rows=self.run_text('Заключение\nСправа BI-RADS 1, слева BI-RADS 2.','BREAST','BREAST_LESION')
        self.assertEqual({(r['side'],r['birads']) for r in rows},{('right',1),('left',2)})

    def test_negation_attached_to_lobe_label(self):
        rows=self.run_text('Описание\nПравая доля. Очаговые образования в правой доле: не лоцируются.\nЛевая доля. Узел 6 мм.\nЗаключение\nУзел слева EU-TIRADS 3.','THYROID','THYROID_NODULE')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['side'],'left')

    def test_isthmus_does_not_inherit_lobe_side(self):
        rows=self.run_text('Описание\nЛевая доля: объем 4 мл.\nПерешеек. Узел 6х4 мм.\nЗаключение\nУзел в перешейке.','THYROID','THYROID_NODULE')
        self.assertEqual(len(rows),1)
        self.assertNotIn('side',rows[0])

    def test_compact_measurement_list_and_no_normal_sizes(self):
        rows=self.run_text('Описание\nПравая доля: размеры 15х18х40 мм.\nУзлы: 3,2мм,3,2мм,5мм.\nЗаключение\nУзлы справа TI-RADS 2.','THYROID','THYROID_NODULE')
        self.assertEqual(rows[0]['count'],3)
        self.assertEqual(rows[0]['sizeMm'],5)

    def test_wrapped_lesion_size(self):
        rows=self.run_text('Описание\nВ правой доле изоэхогенное образование с четкими\nровными контурами размерами 11х7 мм.\nЗаключение\nУзел справа TI-RADS 3.','THYROID','THYROID_NODULE')
        self.assertEqual(rows[0]['sizeMm'],11)

    def test_question_about_neighbor_does_not_hedge_functional_cyst(self):
        rows=self.run_text('Описание\nПравый яичник: представлен анэхогенной структурой 26х19 мм, рядом с яичником определяется вытянутое образование - гидросальпингс?\nЗаключение\nФолликулярная киста справа.','PELVIS_FEMALE','OVARIAN_LESION')
        self.assertFalse(rows[0]['uncertain'])
        self.assertEqual(rows[0]['sizeMm'],26)

    def test_named_cyst_and_fibroadenoma_stay_separate(self):
        rows=self.run_text('Описание\nКиста справа 6 мм.\nФиброаденома справа 14 мм.\nЗаключение\nКиста справа. Фиброаденома справа?','BREAST','BREAST_LESION')
        self.assertEqual({(r['sizeMm'],r['uncertain']) for r in rows},{(6,False),(14,True)})

    def test_symmetric_vascular_maxima_and_summary_deduplicated(self):
        rows=self.run_text('Описание\nСправа АСБ до 25%.\nСлева АСБ до 25%.\nЗаключение\nСтенозирующий атеросклероз.','LOWER_LIMB_VESSELS','ARTERIAL_STENOSIS')
        self.assertEqual(rows,[{'side':'both','stenosisPct':25}])
        rows=self.run_text('Описание\nС обеих сторон стенозы до 55%.\nСправа стеноз до 55%.\nСлева стеноз до 35%.','LOWER_LIMB_VESSELS','ARTERIAL_STENOSIS')
        self.assertEqual({(r['side'],r['stenosisPct']) for r in rows},{('right',55),('left',35)})


class DictionaryExtensionV5Tests(unittest.TestCase):
    def entry(self):
        return {'code':'CUSTOM_FACT','name':'Тестовый очаг','synonyms':['особый очаг'],
                'studyTypes':['BREAST'],'attributes':['side','sizeMm','uncertain','stiffnessKpa'],
                'attributeExtractors':{'stiffnessKpa':{'type':'number','labels':['жесткость','жёсткость'],'unit':'кПа'}}}

    def run_dictionary(self,dictionary,text):
        normalize_dictionary(dictionary)
        return analyze_protocol(parse_text(text),text,'BREAST',dictionary)[0]

    def test_new_code_and_new_attribute_in_existing_dictionary(self):
        dictionary=load_dictionary(DEFAULT_DICTIONARY)
        dictionary['findings'].append(self.entry())
        result=self.run_dictionary(dictionary,'Описание\nОсобый очаг слева 9 мм, жесткость: 17,5кПа.')
        self.assertEqual(result[0]['code'],'CUSTOM_FACT')
        self.assertEqual(result[0]['attributes'],{'side':'left','sizeMm':9,'uncertain':False,'stiffnessKpa':17.5})

    def test_synonym_updates_work_without_python_changes(self):
        item=self.entry();item['synonyms']=['другой очаг']
        self.assertFalse(self.run_dictionary([item],'Особый очаг слева 9 мм.'))
        self.assertTrue(self.run_dictionary([item],'Другой очаг слева 9 мм.'))

    def test_new_code_negation_history_and_uncertainty(self):
        for text in ['Заключение\nОсобый очаг не выявлен.','Анамнез\nОсобый очаг 9 мм.\nЗаключение\nБез патологии.','Рекомендации\nИсключить особый очаг.']:
            self.assertFalse(self.run_dictionary([self.entry()],text))
        result=self.run_dictionary([self.entry()],'Заключение\nВозможно особый очаг слева 9 мм.')
        self.assertTrue(result[0]['attributes']['uncertain'])

    def test_profile_reuses_category_adapter_and_preserves_output_code(self):
        item=self.entry();item.update(code='CUSTOM_BREAST',extractionProfile='BREAST_LESION',attributes=['birads','side','uncertain'])
        item.pop('attributeExtractors')
        result=self.run_dictionary([item],'Заключение\nBI-RADS 1 справа, BI-RADS 2 слева.')
        self.assertEqual({r['code'] for r in result},{'CUSTOM_BREAST'})
        self.assertEqual({(r['attributes']['side'],r['attributes']['birads']) for r in result},{('right',1),('left',2)})

    def test_remote_preserves_custom_extraction_fields(self):
        item=self.entry();dictionary=enrich_remote([item])
        self.assertEqual(dictionary['findings'][0]['attributeExtractors'],item['attributeExtractors'])
        self.assertEqual([i['code'] for i in dictionary['findings']],['CUSTOM_FACT'])

    def test_units_multiplier_integer_boolean_and_string(self):
        item={'attributeExtractors':{
            'value':{'type':'number','labels':['величина'],'unit':'см','multiplier':10},
            'count':{'type':'integer','labels':['число']},
            'flag':{'type':'boolean','positive':['признак присутствует'],'negative':['признак отсутствует']},
            'location':{'type':'string','labels':['расположение']}}}
        self.assertEqual(extract_declared('Величина 1,7 см; число 4; признак отсутствует; расположение: верхняя треть.',item),{'value':17,'count':4,'flag':False,'location':'верхняя треть'})
        self.assertNotIn('count',extract_declared('Число 1,5.',item))
        self.assertNotIn('flag',extract_declared('Не  признак присутствует.',item))

    def test_conflicting_numeric_values_are_not_guessed(self):
        item=self.entry()
        result=self.run_dictionary([item],'Особый очаг, жесткость 7 кПа, жесткость 10 кПа.')
        self.assertNotIn('stiffnessKpa',result[0]['attributes'])

    def test_declared_attribute_type_is_enforced(self):
        for bad in [True,'17.5',None,float('inf')]:
            with self.subTest(value=bad),self.assertRaises(ContractError):
                validate_declared_attributes({'stiffnessKpa':bad},self.entry())
        validate_declared_attributes({'stiffnessKpa':17.5},self.entry())

    def test_full_docx_pipeline_with_new_dictionary_attribute(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from app.demo import docx
        from app.mis import build_event
        from app.processing import process_event
        from app.validation import validate_for_dictionary
        with TemporaryDirectory() as directory:
            path=Path(directory)/'synthetic.docx'
            docx(path,['Заключение','Особый очаг слева 12 мм, жесткость 22 кПа.'])
            event=build_event({'eventId':'extension-test','eventType':'PROTOCOL_SIGNED',
                'patient':{'externalId':'synthetic','fullName':'Пациент 001','birthDate':'1990-01-01','sex':'F'},
                'protocol':{'externalId':'synthetic','version':1,'studyType':'BREAST','studyDate':'2026-09-01'}},path)
            result=process_event(event,lambda:[self.entry()])
            validate_for_dictionary(result,[self.entry()])
            self.assertEqual(result['status'],'DONE')
            self.assertEqual(result['findings'][0]['attributes']['stiffnessKpa'],22)

    def test_invalid_extension_configuration_is_rejected(self):
        for change in [{'extractionProfile':'not-a-profile'},{'extractionProfile':[]},
                       {'attributeExtractors':[]},{'attributeExtractors':{'unknown':{'type':'number','labels':['размер']}}},
                       {'attributeExtractors':{'stiffnessKpa':{'type':'number','labels':[]}}},
                       {'attributeExtractors':{'stiffnessKpa':{'type':'number','labels':['жесткость'],'multiplier':float('nan')}}}]:
            item=deepcopy(self.entry());item.update(change)
            with self.subTest(change=change),self.assertRaises(ContractError):normalize_dictionary([item])


if __name__=='__main__':unittest.main()
