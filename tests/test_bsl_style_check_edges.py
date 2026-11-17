"""Граничные случаи guard-а: литералы, переносы, регистр, IO, атомарность.

invariant: `--fix` не меняет содержимое строковых литералов и не портит файл
на переносе `(` у конструктора; структурные проверки не зависят от регистра
ключевых слов и формы записи (однострочный `Если`, многострочный `Возврат`,
`Асинх`); ошибка чтения — код 2 и сообщение, а не traceback.
"""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest

from scripts.bsl_style_check import analyze_path, main


class EdgeCaseTest(unittest.TestCase):
    def write_case(self, text: str, *, name: str = "Module.bsl", bom: bool = True) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / name
        path.write_bytes((("\ufeff" if bom else "") + text).encode("utf-8"))
        return path

    def write_bytes(self, raw: bytes, *, name: str = "Module.bsl") -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / name
        path.write_bytes(raw)
        return path

    def run_main(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    # -- литералы -------------------------------------------------------

    def test_multiline_literal_space_line_is_not_blank_line(self):
        text = (
            "Процедура Тест()\r\n"
            "\tТекст = \"Первая\r\n"
            "\t\t\t\t\t\t\r\n"
            "\t|Вторая\";\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        self.assertEqual(analyze_path(path, checks={"tab-rhythm"}), [])
        before = path.read_bytes()
        analyze_path(path, checks={"tab-rhythm"}, fix=True)
        self.assertEqual(path.read_bytes(), before, "литерал изменён автофиксом")

    def test_empty_line_inside_literal_keeps_content(self):
        text = (
            "Процедура Тест()\r\n"
            "\tТекст = \"Первая\r\n"
            "\r\n"
            "\t|Вторая\";\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        self.assertEqual(analyze_path(path, checks={"tab-rhythm"}), [])
        analyze_path(path, checks={"tab-rhythm"}, fix=True)
        self.assertIn("\r\n\r\n", path.read_bytes().decode("utf-8-sig"))

    # -- empty-ctor-parens ---------------------------------------------

    def test_ctor_parens_on_next_line_are_not_reported(self):
        text = "Процедура Тест()\r\n\tМ = Новый Массив\r\n\t\t();\r\nКонецПроцедуры\r\n"
        path = self.write_case(text)
        self.assertEqual(analyze_path(path, checks={"empty-ctor-parens"}), [])
        analyze_path(path, checks={"empty-ctor-parens"}, fix=True)
        self.assertIn("Новый Массив\r\n\t\t();", path.read_bytes().decode("utf-8-sig"))

    def test_ctor_parens_fix_inserts_single_pair(self):
        text = "Процедура Тест()\r\n\tМ = Новый Массив;\r\nКонецПроцедуры\r\n"
        path = self.write_case(text)
        analyze_path(path, checks={"empty-ctor-parens"}, fix=True)
        self.assertIn("Новый Массив();", path.read_bytes().decode("utf-8-sig"))

    # -- однострочные блоки и регистр -----------------------------------

    def test_one_line_if_does_not_raise_expected_tabs(self):
        text = (
            "Процедура Тест()\r\n"
            "\tЕсли А Тогда Возврат; КонецЕсли;\r\n"
            "\t\r\n"
            "\tСообщить(1);\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        self.assertEqual(analyze_path(path, checks={"tab-rhythm"}), [])

    def test_async_and_lowercase_method_are_recognized(self):
        text = (
            "Асинх Функция Тест()\r\n"
            "\tЕсли А Тогда\r\n"
            "\t\tЕсли Б Тогда\r\n"
            "\t\t\tЕсли В Тогда\r\n"
            "\t\t\t\tДействие();\r\n"
            "\t\t\tКонецЕсли;\r\n"
            "\t\tКонецЕсли;\r\n"
            "\tКонецЕсли;\r\n"
            "КонецФункции\r\n"
        )
        path = self.write_case(text)
        violations = analyze_path(path, checks={"if-nesting"})
        self.assertEqual([v.line_number for v in violations], [4])

    def test_if_nesting_counts_closers_on_same_line(self):
        text = (
            "Процедура Тест()\r\n"
            "\tЕсли А Тогда Возврат; КонецЕсли;\r\n"
            "\tЕсли Б Тогда\r\n"
            "\t\tЕсли В Тогда\r\n"
            "\t\t\tДействие();\r\n"
            "\t\tКонецЕсли;\r\n"
            "\tКонецЕсли;\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        self.assertEqual(analyze_path(path, checks={"if-nesting"}), [])

    # -- return-expression ---------------------------------------------

    def test_multiline_return_is_reported(self):
        text = (
            "Функция Тест()\r\n"
            "\tВозврат СтрШаблон(\"%1\",\r\n"
            "\t\tБ);\r\n"
            "КонецФункции\r\n"
        )
        path = self.write_case(text)
        violations = analyze_path(path, checks={"return-expression"})
        self.assertEqual([v.line_number for v in violations], [2])

    def test_lowercase_and_one_line_return_are_reported(self):
        text = (
            "Функция Тест()\r\n"
            "\tЕсли А Тогда возврат Х; КонецЕсли;\r\n"
            "\tВозврат ВозвращаемоеЗначение;\r\n"
            "КонецФункции\r\n"
        )
        path = self.write_case(text)
        violations = analyze_path(path, checks={"return-expression"})
        self.assertEqual([v.line_number for v in violations], [2])

    # -- struct-ctor-args ----------------------------------------------

    def test_multiline_struct_constructor_is_reported(self):
        text = (
            "Процедура Тест()\r\n"
            "\tР = Новый Структура(\r\n"
            "\t\t\"Контрагенты, ТоргТочки\",\r\n"
            "\t\tМассивА,\r\n"
            "\t\tМассивБ\r\n"
            "\t);\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        violations = analyze_path(path, checks={"struct-ctor-args"})
        self.assertEqual([v.line_number for v in violations], [2])

    def test_single_property_struct_and_empty_are_clean(self):
        text = (
            "Процедура Тест()\r\n"
            "\tА = Новый Структура(\"А\", А);\r\n"
            "\tБ = Новый Структура();\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        self.assertEqual(analyze_path(path, checks={"struct-ctor-args"}), [])

    # -- comma-space ---------------------------------------------------

    def test_comma_followed_by_tab_is_reported_and_fixed(self):
        text = "Процедура Тест()\r\n\tМетод(А,\tБ);\r\nКонецПроцедуры\r\n"
        path = self.write_case(text)
        violations = analyze_path(path, checks={"comma-space"})
        self.assertEqual(len(violations), 1)
        analyze_path(path, checks={"comma-space"}, fix=True)
        self.assertIn("Метод(А, Б);", path.read_bytes().decode("utf-8-sig"))

    # -- IO и CLI ------------------------------------------------------

    def test_directory_and_missing_file_exit_2_without_traceback(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        directory = Path(tmpdir.name) / "dir"
        directory.mkdir()
        for target, expected in ((str(directory), "каталог"), (str(Path(tmpdir.name) / "nope.bsl"), "ошибка")):
            code, out, err = self.run_main([target])
            self.assertEqual(code, 2, target)
            self.assertNotIn("Traceback", err + out, target)
            self.assertIn(expected, err, target)

    def test_non_utf8_reports_message_and_exit_2(self):
        path = self.write_bytes(b"\xff\xfe\x00bad")
        code, out, err = self.run_main([str(path)])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err + out)
        self.assertIn("UTF-8", err)

    def test_non_bsl_file_is_skipped(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "README.md"
        path.write_text("НЕ ИЛИ текст", encoding="utf-8")
        code, out, _ = self.run_main([str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_violations_only_in_stdout_summary_in_stderr(self):
        path = self.write_case("Процедура Тест()\r\n\tМетод(А,Б);\r\nКонецПроцедуры\r\n")
        code, out, err = self.run_main([str(path)])
        self.assertEqual(code, 1)
        self.assertIn("[comma-space]", out)
        self.assertNotIn("bsl_style_violations=", out)
        self.assertIn("bsl_style_violations=1", err)

    def test_fix_prints_residual_only(self):
        text = (
            "Процедура Тест()\r\n"
            "\tМ = Новый Массив;\r\n"
            "\tЕсли А Тогда\r\n"
            "\t\tЕсли Б Тогда\r\n"
            "\t\t\tЕсли В Тогда\r\n"
            "\t\t\t\tДействие();\r\n"
            "\t\t\tКонецЕсли;\r\n"
            "\t\tКонецЕсли;\r\n"
            "\tКонецЕсли;\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        code, out, err = self.run_main(["--fix", str(path)])
        self.assertEqual(code, 1)
        self.assertNotIn("empty-ctor-parens", out)
        self.assertIn("if-nesting", out)
        self.assertIn("fixed=1", err)

    # -- атомарность ---------------------------------------------------

    def test_fix_preserves_file_mode(self):
        path = self.write_case("Процедура Тест()\r\n\tМ = Новый Массив;\r\nКонецПроцедуры\r\n")
        os.chmod(path, 0o640)
        analyze_path(path, checks={"empty-ctor-parens"}, fix=True)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_symlink_target_is_updated(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        real = Path(tmpdir.name) / "Real.bsl"
        real.write_bytes("\ufeffПроцедура Тест()\r\n\tМ = Новый Массив;\r\nКонецПроцедуры\r\n".encode("utf-8"))
        link = Path(tmpdir.name) / "Link.bsl"
        link.symlink_to(real)
        analyze_path(link, checks={"empty-ctor-parens"}, fix=True)
        self.assertTrue(link.is_symlink())
        self.assertIn("Новый Массив();", real.read_bytes().decode("utf-8-sig"))


if __name__ == "__main__":
    unittest.main()