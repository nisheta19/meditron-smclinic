"""Regression checks for source attribution, normal findings and formatting."""
import json
from copy import deepcopy
from pathlib import Path
import unittest

from app.clinical import analyze_protocol
from app.dictionary import load_dictionary, DEFAULT_DICTIONARY
from app.evaluate import matched_count
from app.generalization import TRANSFORMS
from app.parser import parse_text


class BindingV9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionary = load_dictionary(DEFAULT_DICTIONARY)

    def verify(self, row):
        for name in ('original', 'wrap35', 'upper_wrap55'):
            with self.subTest(variant=name, file=row['file']):
                text = TRANSFORMS[name](row['text'])
                parsed = parse_text(text)
                found, _ = analyze_protocol(parsed, text, row['studyType'], self.dictionary,
                    {'patient': {'sex': 'M' if row['studyType']=='PROSTATE' else 'F'},
                     'protocol': {'studyDate': '2026-10-05'}})
                gold = deepcopy(row['expected']['findings'])
                # Explicit erratum from the immutable v8 evaluation report.
                if row['file']=='typical-006.docx':gold[0]['attributes']['uncertain']=True
                self.assertEqual(matched_count(gold, found), len(gold), found)
                self.assertEqual(len(found), len(gold), found)
                for fact in found:
                    e = fact['evidence']
                    self.assertEqual(parsed['full_text'][e['start']:e['end']], e['text'])

    def test_unsided_measured_conclusion_repeats_one_breast_lesion(self):
        self.verify({'file':'measured-summary', 'studyType':'BREAST',
            'text':'Описание: Правая молочная железа без очаговых образований. Левая молочная железа: неоднородный участок 21х15 мм, нельзя исключить мастит. Заключение: Неоднородный участок 21х15 мм, нельзя исключить мастит. BI-RADS 1 справа. BI-RADS 4 слева.',
            'expected':{'findings':[{'code':'BREAST_LESION','attributes':{'side':'left','sizeMm':21,'inflammation':True,'uncertain':True,'birads':4}}]}})

    def test_tubal_uncertainty_survives_repeated_conclusion(self):
        self.verify({'file':'tubal-summary', 'studyType':'PELVIS_FEMALE',
            'text':'Описание: Справа рядом с яичником тубулярное жидкостное образование до 14 мм — гидросальпинкс? Заключение: Правосторонний гидросальпинкс.',
            'expected':{'findings':[{'code':'HYDROSALPINX','attributes':{'side':'right','sizeMm':14,'uncertain':True}}]}})


def make_case(row):
    def test(self):self.verify(row)
    return test


root = Path(__file__).resolve().parents[1]
for file, selected in [('eval/typical-v8-20261005/gold.json',
                         {6,13,25,26,37,41,43,45,50,51,71,73,74,75,78,79,80,85,87}),
                        ('eval/v8/round6-gold.json', {2,5,27,32,33}),
                        ('eval/v9/round1-gold.json', {1,13,22,25,28,32,33,35}),
                        ('eval/v9/round2-gold.json', {1,4,6,10,14,15,20,28,37}),
                        ('eval/v9/round3-gold.json', {1,10,16,18,20,28,38,45})]:
    rows = json.loads((root/file).read_text('utf-8'))['protocols']
    for i in selected:
        row=rows[i-1]
        setattr(BindingV9Tests, 'test_'+row['file'].replace('.docx','').replace('-','_'), make_case(row))
