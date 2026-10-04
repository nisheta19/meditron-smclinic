"""Section boundaries and lossless text preservation on synthetic protocols."""

import tempfile
import unittest
from pathlib import Path

from app.parser import parse_docx, parse_text
from app.sections import split_sections
from test_parser import paragraph, write_docx


class SectionTests(unittest.TestCase):
    def assert_preserved(self, text, sections):
        self.assertEqual("".join((s["title"] or "") + s["text"] for s in sections), text)

    def test_sections_preamble_and_original_text(self):
        text = ("Врач: Иванова Анна Петровна\nОписание\nРазмеры 10×12 мм.\n"
                "ЗАКЛЮЧЕНИЕ: Находка.\nРекомендации врача\nКонтроль.\n")
        result = parse_text(text)
        self.assertEqual(result["full_text"], " ".join(text.split()))
        self.assertEqual([s["name"] for s in result["sections"]],
                         ["unsectioned", "description", "conclusion", "recommendations"])
        self.assertEqual(result["sections"][2]["text"].strip(), "Находка.")
        self.assertEqual(
            "".join(text.split()),
            "".join("".join(((s["title"] or "") + s["text"]).split()) for s in result["sections"]),
        )
        self.assertTrue(all("\n" not in s["text"] for s in result["sections"]))

    def test_inline_repeated_headings_and_empty_section(self):
        text = "Описание: Текст.ЗАКЛЮЧЕНИЕ: Первое. Заключение: Второе. РЕКОМЕНДОВАНО:"
        sections = split_sections(text)
        self.assertEqual([s["name"] for s in sections],
                         ["description", "conclusion", "conclusion", "recommendations"])
        self.assertEqual(sections[-1]["text"], "")
        self.assert_preserved(text, sections)

    def test_disclaimer_and_ordinary_words_are_not_headings(self):
        text = ("Описание\nДанное заключение не является диагнозом.\n"
                "Врач обсуждает рекомендации и назначения.\n"
                "Заключение должно интерпретироваться специалистом.")
        sections = split_sections(text)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["name"], "description")
        self.assert_preserved(text, sections)

    def test_no_headings_and_unknown_heading_remain_in_text(self):
        text = "Текст без метаданных\nНЕИЗВЕСТНЫЙ РАЗДЕЛ\nЕщё текст."
        self.assertEqual(split_sections(text),
                         [{"name": "unsectioned", "title": None, "text": text}])

    def test_other_headings_nbsp_and_crlf(self):
        text = ("Жалобы: Нет.\r\nАнамнез заболевания: Текст.\r\n"
                "Диагноз\r\nТекст.\r\nНазначенные\xa0услуги\r\n"
                "Лабораторная диагностика\r\nАнализ.\r\nНазначения\r\nКонтроль.\r\n"
                "Заключение исследования\r\nТекст.\r\nРек-но: Контроль.\r\n"
                "Подпись врача: Иванова Анна Петровна")
        sections = split_sections(text)
        self.assertEqual([s["name"] for s in sections], ["complaints", "history", "diagnosis",
                         "ordered_services", "laboratory_tests", "prescriptions", "conclusion",
                         "recommendations", "signature"])
        self.assert_preserved(text, sections)

    def test_docx_tables_and_split_heading_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sections.docx"
            content = '<w:tbl><w:tr><w:tc>' + paragraph("Описание") + '</w:tc><w:tc>'
            content += paragraph("Первый абзац.") + paragraph("Второй абзац.")
            content += '</w:tc></w:tr></w:tbl>'
            content += '<w:p><w:r><w:t>Заклю</w:t></w:r><w:r><w:t>чение:</w:t></w:r></w:p>'
            content += paragraph("Текст заключения.")
            write_docx(path, content)
            result = parse_docx(path)
            self.assertEqual([s["name"] for s in result["sections"]], ["description", "conclusion"])
            self.assertIn("Первый абзац. Второй абзац.", result["sections"][0]["text"])
            self.assertEqual(
                "".join(result["full_text"].split()),
                "".join("".join(((s["title"] or "") + s["text"]).split()) for s in result["sections"]),
            )
