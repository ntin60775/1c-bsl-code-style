from pathlib import Path
import tempfile
import unittest

from scripts.check_bsl_blank_line_tab_rhythm import analyze_path


class BlankLineTabRhythmTest(unittest.TestCase):
    def write_case(self, text: str) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "Module.bsl"
        path.write_bytes(("\ufeff" + text).encode("utf-8"))
        return path

    def test_top_level_blank_lines_are_ignored(self):
        path = self.write_case("Процедура Один()\r\n\tСообщить(1);\r\nКонецПроцедуры\r\n\r\nПроцедура Два()\r\n\tСообщить(2);\r\nКонецПроцедуры\r\n")
        self.assertEqual(analyze_path(path), [])

    def test_empty_line_inside_method_is_reported(self):
        path = self.write_case("Процедура Тест()\r\n\tСообщить(1);\r\n\r\n\tСообщить(2);\r\nКонецПроцедуры\r\n")
        violations = analyze_path(path)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].line_number, 3)
        self.assertEqual(violations[0].expected_tabs, 1)

    def test_nested_blank_line_before_closing_block_uses_body_level(self):
        path = self.write_case("Процедура Тест()\r\n\tЕсли Условие Тогда\r\n\t\tСообщить(1);\r\n\r\n\tКонецЕсли;\r\nКонецПроцедуры\r\n")
        violations = analyze_path(path)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].expected_tabs, 2)

    def test_fix_preserves_bom_and_crlf(self):
        path = self.write_case("Процедура Тест()\r\n\tСообщить(1);\r\n\r\n\tСообщить(2);\r\nКонецПроцедуры\r\n")
        violations = analyze_path(path, fix=True)
        self.assertEqual(len(violations), 1)
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n\t\r\n", raw)
        self.assertNotIn(b"\n\n", raw)


if __name__ == "__main__":
    unittest.main()
