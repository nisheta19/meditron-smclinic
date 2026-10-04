import unittest
from app.dataset import split_records


def row(i, text, kind="BREAST"):
    return {"documentId": str(i), "sha256": str(i), "full_text": text,
            "sections": [{"name": "description", "text": text}], "studyType": kind}


class DatasetTests(unittest.TestCase):
    def test_duplicates_and_possible_patient_stay_together(self):
        records = [row(1, "Киста " * 100 + "10 мм"), row(2, "Киста " * 100 + "11 мм"),
                   row(3, "Дата рождения: 01.01.2000. Полип"),
                   row(4, "Дата рождения: 01.01.2000. Миома", "PELVIS_FEMALE")]
        result = split_records(records)
        by_id = {r["documentId"]: r for r in result["documents"]}
        self.assertEqual(by_id["1"]["groupId"], by_id["2"]["groupId"])
        self.assertEqual(by_id["3"]["split"], by_id["4"]["split"])
        self.assertEqual(result, split_records(list(reversed(records))))

    def test_all_documents_assigned_once_and_no_false_gold(self):
        result = split_records([row(i, str(i)) for i in range(20)])
        self.assertEqual(len({r["documentId"] for r in result["documents"]}), 20)
        self.assertEqual(set(result["counts"]), {"train", "dev", "test"})
        self.assertFalse(result["clinicalGoldLabels"])
