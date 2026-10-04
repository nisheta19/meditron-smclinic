"""Frozen synthetic regression cases, independent of production rule definitions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from app.clinical import analyze_protocol
from app.dictionary import DEFAULT_DICTIONARY, load_dictionary
from app.evaluate import fact_matches, matched_count
from app.generalization import validate_gold, TRANSFORMS
from app.parser import parse_text
from app.text_units import logical_lines

FIXTURES = Path(__file__).parent / 'fixtures'
HASHES = {'development': '2d3d7599fa34c1f75b546a336544c4cb75ac948a676e8920fac3b2b2fc2f3e0d',
          'validation': 'bf897b1870cea8b24d519ac3aaa3ddd4e9ca9169cb096721c68ea3defc0e1fb9'}


class GeneralizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionary = load_dictionary(DEFAULT_DICTIONARY)

    def analyze(self, text, study, dictionary=None):
        parsed = parse_text(text)
        found, _ = analyze_protocol(parsed, text, study, dictionary or self.dictionary,
                    {'patient': {'sex': 'M' if study == 'PROSTATE' else 'F'},
                     'protocol': {'studyDate': '2026-09-08'}})
        for finding in found:
            e = finding['evidence']
            self.assertEqual(parsed['full_text'][e['start']:e['end']], e['text'])
        return found

    def check_row(self, row, transform=lambda x: x):
        actual = self.analyze(transform(row['text']), row['studyType'])
        gold = row['expected']['findings']
        self.assertEqual(matched_count(gold, actual, fact_matches), len(gold), actual)
        self.assertEqual(len(actual), len(gold), actual)

    def test_frozen_gold_checksums(self):
        for name, digest in HASHES.items():
            data = (FIXTURES / f'generalization-{name}.json').read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
            validate_gold(json.loads(data), self.dictionary)

    def test_formatted_validation(self):
        rows = json.loads((FIXTURES / 'generalization-validation.json').read_text('utf-8'))['protocols']
        for name in ('wrap35', 'upper', 'upper_wrap55', 'headers'):
            for row in rows:
                with self.subTest(variant=name, file=row['file']):
                    self.check_row(row, TRANSFORMS[name])

    def test_formatted_development(self):
        rows = json.loads((FIXTURES / 'generalization-development.json').read_text('utf-8'))['protocols']
        for name in ('wrap35', 'upper', 'upper_wrap55'):
            for row in rows:
                with self.subTest(variant=name, file=row['file']):
                    self.check_row(row, TRANSFORMS[name])

    def test_new_dictionary_code_keeps_multiline_size(self):
        dictionary = deepcopy(self.dictionary)
        dictionary['findings'].append({'code': 'CUSTOM_FOCUS', 'name': 'Особый очаг',
            'synonyms': ['тестовый очаг'], 'studyTypes': ['BREAST'],
            'attributes': ['side', 'sizeMm', 'uncertain', 'stiffnessKpa'],
            'attributeExtractors': {'stiffnessKpa': {'type': 'number',
                                     'labels': ['жесткость'], 'unit': 'кПа'}}})
        actual = self.analyze('Описание исследования:\nОсобый очаг слева размером\n1,6 на 0,7 см, жесткость 19 кПа.', 'BREAST', dictionary)
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0]['code'], 'CUSTOM_FOCUS')
        self.assertEqual(actual[0]['attributes'],
                         {'side': 'left', 'sizeMm': 16, 'uncertain': False, 'stiffnessKpa': 19})
        self.assertFalse(self.analyze('Заключение врача: Особого очага в левой молочной железе\nне обнаружено.', 'BREAST', dictionary))

    def test_negative_field_and_next_positive_statement_stay_separate(self):
        text = 'Образования: не выявлены\nНа границе квадрантов имеется узел 12 мм'
        self.assertEqual(logical_lines(text), text.splitlines())
        self.assertEqual(logical_lines(text.upper()), text.upper().splitlines())

    def test_contour_colon_is_a_continuation_not_a_new_field(self):
        text = 'Узел с\nчеткими ровными контурами: 18 на 9 мм'
        self.assertEqual(logical_lines(text), ['Узел с четкими ровными контурами: 18 на 9 мм'])

    def test_unknown_gold_code_and_path_are_rejected(self):
        gold = {'annotationStatus': 'synthetic', 'protocols': [{'file': 'one.docx',
                'studyType': 'BREAST', 'text': 'Норма.',
                'expected': {'findings': [{'code': 'MISSING_CODE', 'attributes': {}}]}}]}
        with self.assertRaises(ValueError):validate_gold(gold, self.dictionary)
        gold['protocols'][0]['expected']['findings'] = []
        for name in ('../outside.docx', '..\\outside.docx'):
            gold['protocols'][0]['file'] = name
            with self.assertRaises(ValueError):validate_gold(gold, self.dictionary)


def make_case(row):
    def test(self):self.check_row(row)
    return test


for suite in HASHES:
    cases = json.loads((FIXTURES / f'generalization-{suite}.json').read_text('utf-8'))['protocols']
    for index, row in enumerate(cases, 1):
        setattr(GeneralizationTests, f'test_{suite}_{index:03d}_{row["studyType"]}', make_case(row))
