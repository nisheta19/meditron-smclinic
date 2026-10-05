"""Regression tests for scope, repeated entities and formatting (synthetic text)."""
import unittest
from copy import deepcopy

from app.clinical import analyze_protocol
from app.dictionary import DEFAULT_DICTIONARY, load_dictionary
from app.evaluate import fact_matches, matched_count
from app.generalization import TRANSFORMS
from app.parser import parse_text


class CompositionalExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionary=load_dictionary(DEFAULT_DICTIONARY)

    def check(self,study,text,expected,dictionary=None):
        for variant in ('original','wrap35','wrap55','upper_wrap55','nbsp'):
            source=TRANSFORMS[variant](text);parsed=parse_text(source)
            found,_=analyze_protocol(parsed,source,study,dictionary or self.dictionary)
            with self.subTest(variant=variant):
                self.assertEqual(matched_count(expected,found,fact_matches),len(expected),found)
                self.assertEqual(len(found),len(expected),found)
                for f in found:
                    e=f['evidence']
                    self.assertEqual(parsed['full_text'][e['start']:e['end']],e['text'])
                    self.assertFalse(any(k.startswith('_') for k in f))

    def test_terminal_negation_applies_to_enumerated_findings(self):
        self.check('ABDOMEN','Описание: Желчный пузырь: полипы, конкременты и взвесь не выявлены.\nЗаключение: Без патологии.',[])

    def test_negative_finding_does_not_cancel_adjacent_positive(self):
        self.check('ABDOMEN','Описание: Эхогенная взвесь в желчном пузыре.\nЗаключение: Билиарный сладж, конкрементов нет.',
                   [{'code':'BILIARY_SLUDGE','attributes':{'uncertain':False,'withStones':False}}])

    def test_negative_attribute_is_not_negative_entity(self):
        self.check('SOFT_TISSUE','Заключение: Паховая грыжа справа без признаков кишечной непроходимости.',
                   [{'code':'HERNIA','attributes':{'side':'right','obstruction':False}}])

    def test_negative_attribute_after_anatomical_modifier(self):
        self.check('LOWER_LIMB_VESSELS','Описание: В правой подколенной вене окклюзивный тромб. Флотирующей верхушки нет.\nЗаключение: Тромбоз глубоких вен справа.',
                   [{'code':'DEEP_VEIN_THROMBOSIS','attributes':{'side':'right','occlusive':True,'floating':False}}])

    def test_single_sided_hernia_keeps_unsided_measurement_in_other_section(self):
        self.check('SOFT_TISSUE','Заключение: Ущемлённая паховая грыжа слева. Содержимое не вправляется.\nОписание: Ворота грыжи 11 мм.',
                   [{'code':'HERNIA','attributes':{'side':'left','sizeMm':11,'incarcerated':True,'reducible':False}}])

    def test_vessel_acronym_after_hard_wrap_keeps_own_side(self):
        self.check('LOWER_LIMB_VESSELS','Описание: Справа тромб в глубокой бедренной вене, не флотирует. Слева тромбофлебит БПВ, тромб в 62 мм от СФС, без флотации.\nЗаключение: Тромбоз глубоких вен справа. Тромбофлебит\nБПВ слева.',
                   [{'code':'DEEP_VEIN_THROMBOSIS','attributes':{'side':'right','floating':False}},
                    {'code':'SUPERFICIAL_THROMBOPHLEBITIS','attributes':{'side':'left','vein':'БПВ','distanceToJunctionMm':62,'floating':False}}])

    def test_unsided_umbilical_hernia_is_separate_from_inguinal_hernia(self):
        self.check('SOFT_TISSUE','Описание: Пупочная грыжа, ворота 13 мм, содержит сальник, вправимая. Справа паховая грыжа с воротами 21 мм, вправимая.\nЗаключение: Пупочная грыжа и паховая грыжа справа.',
                   [{'code':'HERNIA','attributes':{'sizeMm':13,'reducible':True,'content':'сальник'}},
                    {'code':'HERNIA','attributes':{'side':'right','sizeMm':21,'reducible':True}}])

    def test_zero_residual_does_not_create_retention(self):
        self.check('PROSTATE','Описание: Простата 57 мл. Остаточная моча 0 мл.\nЗаключение: ДГПЖ.',
                   [{'code':'BPH','attributes':{'volumeCm3':57}}])

    def test_stone_size_is_not_duct_diameter(self):
        self.check('ABDOMEN','Описание: В холедохе конкремент 9 мм. Диаметр холедоха 15 мм, он расширен. Желчный пузырь удалён.\nЗаключение: Холедохолитиаз.',
                   [{'code':'GALLSTONES','attributes':{'location':'choledoch','sizeMm':9,'choledochMm':15,'ductsDilated':True}}])

    def test_separate_categories_keep_separate_sizes(self):
        self.check('THYROID','Описание: В правой доле два узла: первый 8 мм, EU-TIRADS 3; второй 25 мм, EU-TIRADS 4.\nЗаключение: Узлы справа.',
                   [{'code':'THYROID_NODULE','attributes':{'side':'right','sizeMm':8,'tirads':3}},
                    {'code':'THYROID_NODULE','attributes':{'side':'right','sizeMm':25,'tirads':4}}])

    def test_ovarian_context_does_not_overwrite_cervix(self):
        self.check('PELVIS_FEMALE','Описание: Левый яичник с простой кистой 32 мм, O-RADS 2. Шейка матки: наботовы кисты 5 мм, канал не деформирован.\nЗаключение: Простая киста слева. Ретенционные кисты шейки матки.',
                   [{'code':'OVARIAN_LESION','attributes':{'side':'left','sizeMm':32,'orads':2}},
                    {'code':'CERVICAL_RETENTION_CYSTS','attributes':{'sizeMm':5,'deformsCanal':False}}])

    def test_anatomical_word_ending_is_not_negation(self):
        self.check('LOWER_LIMB_VESSELS','Описание: В левой подколенной вене окклюзивный тромб, флотации нет.\nЗаключение: Тромбоз глубоких вен слева.',
                   [{'code':'DEEP_VEIN_THROMBOSIS','attributes':{'side':'left','occlusive':True,'floating':False}}])

    def test_unknown_dictionary_code_uses_general_negation_rules(self):
        d=deepcopy(self.dictionary)
        d['findings'].append({'code':'NEW_FOCUS','name':'Особый очаг','synonyms':['особый очаг'],
            'studyTypes':['BREAST'],'attributes':['side','sizeMm','uncertain']})
        self.check('BREAST','Описание: Особый очаг в правой молочной железе не обнаружен.',[],d)
        self.check('BREAST','Описание: Особый очаг слева 15 мм.',
                   [{'code':'NEW_FOCUS','attributes':{'side':'left','sizeMm':15}}],d)


if __name__=='__main__':unittest.main()
