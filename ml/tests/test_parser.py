"""Synthetic protocols only: no source medical documents are copied into tests."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

from app.parser import DocumentError, extract_text, parse_docx, parse_text

METADATA = ("doctor_first_name", "doctor_last_name", "patient_age", "examination_date")


def write_docx(path, content, header=None):
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{content}</w:body></w:document>'
        ))
        if header:
            archive.writestr("word/header1.xml", header)


def paragraph(text):
    return f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>"


class ParserTests(unittest.TestCase):
    def test_full_name_numeric_date_and_age(self):
        result = parse_text("Врач: Иванова Анна Петровна\nВозраст на момент осмотра: 42\nДата приема: 03.10.2026")
        self.assertEqual({key: result[key] for key in METADATA}, dict(doctor_first_name="Анна", doctor_last_name="Иванова",
                                     patient_age=42, examination_date="2026-10-03"))

    def test_signature_supplies_surname(self):
        result = parse_text("Врач: Анна Петровна\nДата выполнения: 3 октября 2026 г.\n"
                            "Дата рождения: 4 октября 1980 г.\nПодпись врача: Иванова Анна Петровна")
        self.assertEqual(result["doctor_last_name"], "Иванова")
        self.assertEqual(result["patient_age"], 45)

    def test_missing_surname_is_not_patronymic(self):
        result = parse_text("Врач: Анна Петровна\nОписание\nНаправлена врачом Смирновым")
        self.assertEqual(result["doctor_first_name"], "Анна")
        self.assertIsNone(result["doctor_last_name"])

    def test_birthday_today_and_leap_year(self):
        for birth, exam, expected in [("03.10.1980", "03.10.2026", 46),
                                      ("29.02.2000", "28.02.2025", 24)]:
            result = parse_text(f"Дата рождения: {birth}\nДата осмотра: {exam}")
            self.assertEqual(result["patient_age"], expected)

    def test_explicit_age_priority(self):
        result = parse_text("Возраст пациента: 50 лет\nДата рождения: 01.01.1980\nДата приема: 03.10.2026")
        self.assertEqual(result["patient_age"], 50)

    def test_invalid_missing_and_conflicting_values(self):
        for text in ["Дата осмотра: 31.02.2026", "Дата рождения: 01.01.1980",
                     "Дата приема: 01.10.2026\nДата осмотра: 02.10.2026"]:
            result = parse_text(text)
            self.assertIsNone(result["examination_date"])
            self.assertIsNone(result["patient_age"])
        self.assertTrue(all(parse_text("Нет метаданных")[key] is None for key in METADATA))

    def test_conflicting_doctors_are_not_combined(self):
        result = parse_text("Врач: Анна Петровна\nПодпись врача: Иванов Петр Сергеевич")
        self.assertIsNone(result["doctor_first_name"])
        self.assertIsNone(result["doctor_last_name"])

    def test_initials_do_not_expand(self):
        result = parse_text("Врач: Иванова А. П.")
        self.assertIsNone(result["doctor_first_name"])
        self.assertEqual(result["doctor_last_name"], "Иванова")

    def test_patient_name_and_historical_date_not_used(self):
        result = parse_text("ФИО пациента: Иванова Анна Петровна\nОписание: контроль после 01.02.2020")
        self.assertTrue(all(result[key] is None for key in METADATA))

    def test_docx_tables_split_runs_header_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "протокол с пробелами.docx"
            body = '<w:tbl><w:tr><w:tc>' + paragraph("Врач:") + '</w:tc><w:tc>'
            body += '<w:p><w:r><w:t>Ива</w:t></w:r><w:r><w:t>нова Анна Петровна</w:t></w:r></w:p>'
            body += '</w:tc></w:tr></w:tbl>' + paragraph("Возраст на момент осмотра:\u00a042")
            header = ('<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                      + paragraph("Дата осмотра: 2026-10-03") + '</w:hdr>')
            write_docx(path, body, header)
            self.assertIn("Иванова", extract_text(path))
            result = parse_docx(path)
            self.assertEqual(result["doctor_last_name"], "Иванова")
            self.assertEqual(result["examination_date"], "2026-10-03")
            cli = subprocess.run([sys.executable, "-m", "app", str(path)], capture_output=True)
            self.assertEqual(cli.returncode, 0)
            self.assertEqual(cli.stderr, b"")
            self.assertEqual(json.loads(cli.stdout.decode("utf-8")), result)

    def test_bad_file_and_cli_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.docx"
            path.write_text("Not a DOCX", encoding="utf-8")
            with self.assertRaises(DocumentError):
                parse_docx(path)
            cli = subprocess.run([sys.executable, "-m", "app", str(path)], capture_output=True)
            self.assertEqual(cli.returncode, 2)
            self.assertEqual(cli.stdout, b"")
            self.assertIn("error", json.loads(cli.stderr.decode("utf-8")))
            with self.assertRaises(DocumentError):
                parse_docx(Path(tmp) / "image.pdf")

    def test_deleted_text_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revised.docx"
            write_docx(path, '<w:del>' + paragraph("Врач: Петров Петр Сергеевич") + '</w:del>'
                       + paragraph("Врач: Иванова Анна Петровна"))
            self.assertEqual(parse_docx(path)["doctor_first_name"], "Анна")


if __name__ == "__main__":
    unittest.main()
