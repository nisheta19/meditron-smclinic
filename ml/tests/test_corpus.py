import json
from pathlib import Path
import tempfile
import unittest
from app.corpus import audit, study_type
from test_parser import paragraph, write_docx


class CorpusTests(unittest.TestCase):
    def test_audit_preserves_sections_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            file = source / "synthetic.docx"
            write_docx(file, paragraph("Описание") + paragraph("Щитовидная железа. Размер 1,2 см.") + paragraph("Заключение: Узел?"))
            before = file.read_bytes()
            result = audit(source, root / "output")
            self.assertEqual(result["textConserved"], 1)
            self.assertEqual(file.read_bytes(), before)
            record = json.loads((root / "output/documents.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(record["studyType"], "THYROID")
            self.assertEqual(record["flags"], [])
            self.assertTrue((root / "output/review.html").exists())

    def test_type_is_not_assigned_from_folder(self):
        self.assertEqual(study_type("Артерии нижних конечностей")[0], "LOWER_LIMB_VESSELS")
        self.assertIsNone(study_type("Описание без названия органа")[0])
        self.assertIsNone(study_type("Щитовидная железа и молочная железа")[0])
        self.assertEqual(study_type("Органы малого таза: предстательная железа")[0], "PROSTATE")

    def test_source_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                audit(tmp, Path(tmp) / "output")
