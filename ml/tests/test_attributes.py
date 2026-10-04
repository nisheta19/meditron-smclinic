import unittest
from app.attributes import categories
from app.findings import analyze

D = [{"code": "NODE", "name": "узел", "synonyms": [], "studyTypes": ["THYROID"]}]


class AttributeTests(unittest.TestCase):
    def extract(self, text):
        findings, rejected = analyze(text, "THYROID", D)
        for f in findings:
            e = f["evidence"]
            self.assertEqual(text[e["start"]:e["end"]], e["text"])
        return findings

    def test_size_units_side_category_with_exact_quote(self):
        f = self.extract("Слева узел 1,2×0,8 см, EU-TIRADS 3.")[0]
        self.assertEqual(f["attributes"]["sizeMm"], 12)
        self.assertEqual(f["attributes"]["side"], "left")
        self.assertEqual(f["attributes"]["category"], "EU-TIRADS 3")
        self.assertIn("1,2×0,8 см", f["evidence"]["text"])

    def test_decimal_point_is_not_sentence_boundary(self):
        self.assertEqual(self.extract("Узел 1.5 см.")[0]["attributes"]["sizeMm"], 15)

    def test_organ_size_not_assigned_to_finding(self):
        for text in ("Железа 40 мм. Узел.", "Узел, правая доля 40 мм.", "Узел. Железа 40 мм.", "Узел, киста 40 мм."):
            self.assertNotIn("sizeMm", self.extract(text)[0]["attributes"])

    def test_separate_findings_and_ambiguous_sizes(self):
        f = self.extract("Узел 5 мм; узел 8 мм.")
        self.assertEqual([x["attributes"]["sizeMm"] for x in f], [5, 8])
        self.assertNotIn("sizeMm", self.extract("Узел 5 мм и 8 мм.")[0]["attributes"])

    def test_category_scales_remain_distinct(self):
        self.assertEqual([c["value"] for c in categories("BI-RADS 4a, O-RADS 2, TI-RADS 3, EU-TIRADS 3")],
                         ["BI-RADS 4A", "O-RADS 2", "TI-RADS 3", "EU-TIRADS 3"])

    def test_volume_is_not_size(self):
        self.assertNotIn("sizeMm", self.extract("Узел объемом 5 см³.")[0]["attributes"])
