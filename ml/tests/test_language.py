"""Hand-written synthetic language regressions, independent of corpus labels."""
import unittest
from app.findings import analyze

D = [
    {"code": "CYST", "name": "киста", "synonyms": ["кисты", "кист"], "studyTypes": ["BREAST"]},
    {"code": "NODE", "name": "узел", "synonyms": ["узлы", "узлов"], "studyTypes": ["BREAST"]},
]


class LanguageTests(unittest.TestCase):
    def test_negation_scopes(self):
        cases = [
            ("Кисты не выявлены.", [], ["CYST"]),
            ("Без кист и узлов.", [], ["CYST", "NODE"]),
            ("Кист и узлов не выявлено.", [], ["CYST", "NODE"]),
            ("Не выявлено кист.", [], ["CYST"]),
            ("Киста не лоцируется.", [], ["CYST"]),
            ("Киста не определяется, но узел 5 мм.", ["NODE"], ["CYST"]),
            ("Киста без динамики.", ["CYST"], []),
            ("Киста слева не выявлена; узел справа 8 мм.", ["NODE"], ["CYST"]),
        ]
        for text, positive, negative in cases:
            with self.subTest(text=text):
                found, rejected = analyze(text, "BREAST", D)
                self.assertEqual([f["code"] for f in found], positive)
                self.assertEqual([f["code"] for f in rejected], negative)

    def test_uncertainty_not_absence(self):
        for text in ("Нельзя исключить кисту", "Не исключается киста.", "Киста не исключается.", "Киста?", "Вероятно киста."):
            # Accusative requires an explicit dictionary form, never stemming.
            dictionary = [dict(D[0], synonyms=[*D[0]["synonyms"], "кисту"]), D[1]]
            with self.subTest(text=text):
                found, rejected = analyze(text, "BREAST", dictionary)
                self.assertEqual(len(found), 1)
                self.assertFalse(rejected)
                self.assertTrue(found[0]["attributes"]["uncertain"])

    def test_history_and_surgery_are_distinct(self):
        for text in ("После удаления кисты.", "Киста удалена."):
            found, rejected = analyze(text, "BREAST", D)
            self.assertFalse(found)
            self.assertEqual(rejected[0]["reason"], "POST_SURGERY")
        found, _ = analyze("В анамнезе киста. Узел 4 мм.", "BREAST", D)
        self.assertEqual(found[0]["attributes"]["temporality"], "historical")
        self.assertNotIn("temporality", found[1]["attributes"])

    def test_two_sides_and_missing_units(self):
        found, _ = analyze("Справа киста 5 мм; слева киста 1 см. Узел 8.", "BREAST", D)
        self.assertEqual([f["attributes"].get("side") for f in found], ["right", "left", None])
        self.assertEqual([f["attributes"].get("sizeMm") for f in found], [5, 10, None])

    def test_no_confidence_or_route_fabrication(self):
        found, _ = analyze("Киста.", "BREAST", D)
        self.assertNotIn("confidence", found[0])
        self.assertNotIn("route", found[0])
