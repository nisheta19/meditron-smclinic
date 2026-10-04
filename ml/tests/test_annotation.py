import unittest
from app.annotation import annotate_record, provisional_dictionary
from app.findings import validate_dictionary


class AnnotationTests(unittest.TestCase):
    def test_lexical_labels_are_preliminary_and_have_evidence(self):
        text = "Киста. Тромбоз не выявлен. Нельзя исключить полип."
        row = annotate_record({"full_text": text, "studyType": "BREAST", "flags": []})
        self.assertEqual(row["annotationStatus"], "machine_preliminary_unreviewed")
        self.assertEqual({a["assertion"] for a in row["annotations"]}, {"present", "negated", "uncertain"})
        for a in row["annotations"]:
            self.assertTrue(a["code"].startswith("LOCAL_"))
            self.assertIn(a["evidence"]["text"], text)
            self.assertNotIn("confidence", a)
        validate_dictionary(provisional_dictionary())

    def test_mixed_mentions_are_marked_for_review(self):
        row = annotate_record({"full_text": "Киста справа. Киста слева не выявлена.", "studyType": "BREAST", "flags": []})
        # This is a context check, not a claim that left and right contradict.
        self.assertTrue(row["reviewRequired"])
        self.assertNotIn("route", row)
