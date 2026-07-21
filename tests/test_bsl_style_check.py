from pathlib import Path
import tempfile
import unittest

from scripts.bsl_style_check import CHECK_IDS, analyze_path, main


class BslStyleCheckTest(unittest.TestCase):
    def write_case(self, text: str) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "Module.bsl"
        path.write_bytes(("\ufeff" + text).encode("utf-8"))
        return path

    # ------------------------------------------------------------------
    # tab-rhythm
    # ------------------------------------------------------------------

    def test_top_level_blank_lines_are_ignored(self):
        path = self.write_case("Процедура Один()\r\n\tСообщить(1);\r\nКонецПроцедуры\r\n\r\nПроцедура Два()\r\n\tСообщить(2);\r\nКонецПроцедуры\r\n")
        self.assertEqual(analyze_path(path), [])

    def test_empty_line_inside_method_is_reported(self):
        path = self.write_case("Процедура Тест()\r\n\tСообщить(1);\r\n\r\n\tСообщить(2);\r\nКонецПроцедуры\r\n")
        violations = analyze_path(path)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].line_number, 3)
        self.assertEqual(violations[0].check, "tab-rhythm")
        self.assertIn("ожидается 1 таб.", violations[0].message)

    def test_nested_blank_line_before_closing_block_uses_body_level(self):
        path = self.write_case("Процедура Тест()\r\n\tЕсли Условие Тогда\r\n\t\tСообщить(1);\r\n\r\n\tКонецЕсли;\r\nКонецПроцедуры\r\n")
        violations = analyze_path(path)
        self.assertEqual(len(violations), 1)
        self.assertIn("ожидается 2 таб.", violations[0].message)

    def test_fix_preserves_bom_and_crlf(self):
        path = self.write_case("Процедура Тест()\r\n\tСообщить(1);\r\n\r\n\tСообщить(2);\r\nКонецПроцедуры\r\n")
        violations = analyze_path(path, fix=True)
        self.assertEqual(len(violations), 1)
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n\t\r\n", raw)
        self.assertNotIn(b"\n\n", raw)

    # ------------------------------------------------------------------
    # operator-case
    # ------------------------------------------------------------------

    def test_operator_case_fixes_and_preserves_strings_and_comments(self):
        text = (
            "Процедура Тест()\r\n"
            "\tЕсли НЕ Готово ИЛИ Пусто Тогда\r\n"
            "\t\tСообщить(\"НЕ ИЛИ\"); // НЕ ИЛИ\r\n"
            "\tКонецЕсли;\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        violations = analyze_path(path, checks={"operator-case"}, fix=True)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].line_number, 2)
        lines = path.read_bytes().decode("utf-8-sig").splitlines()
        self.assertEqual(lines[1], "\tЕсли Не Готово Или Пусто Тогда")
        self.assertEqual(lines[2], '\t\tСообщить("НЕ ИЛИ"); // НЕ ИЛИ')

    def test_operator_case_ignores_identifiers_and_canonical_forms(self):
        text = (
            "Процедура Тест()\r\n"
            "\tНеОтключать = Истина;\r\n"
            "\tЕсли Не Готово Или Пусто И Активно Тогда\r\n"
            "\tКонецЕсли;\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        self.assertEqual(analyze_path(path, checks={"operator-case"}), [])

    # ------------------------------------------------------------------
    # empty-ctor-parens
    # ------------------------------------------------------------------

    def test_empty_ctor_parens_fixes_only_missing_parens(self):
        text = (
            "Процедура Тест()\r\n"
            "\tМ = Новый Массив;\r\n"
            "\tС = Новый Структура();\r\n"
            "\tЗ = Новый Запрос(\"Текст\");\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        violations = analyze_path(path, checks={"empty-ctor-parens"}, fix=True)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].line_number, 2)
        lines = path.read_bytes().decode("utf-8-sig").splitlines()
        self.assertEqual(lines[1], "\tМ = Новый Массив();")
        self.assertEqual(lines[2], "\tС = Новый Структура();")

    # ------------------------------------------------------------------
    # comma-space
    # ------------------------------------------------------------------

    def test_comma_space_fixes_code_and_preserves_strings(self):
        text = (
            "Процедура Тест()\r\n"
            "\tМетод(А,Б);\r\n"
            "\tТекст = СтрШаблон(\"%1,%2\", А, Б);\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        violations = analyze_path(path, checks={"comma-space"}, fix=True)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].line_number, 2)
        lines = path.read_bytes().decode("utf-8-sig").splitlines()
        self.assertEqual(lines[1], "\tМетод(А, Б);")
        self.assertEqual(lines[2], '\tТекст = СтрШаблон("%1,%2", А, Б);')

    # ------------------------------------------------------------------
    # struct-ctor-args
    # ------------------------------------------------------------------

    def test_struct_ctor_args_reports_multi_value_constructor(self):
        text = (
            "Процедура Тест()\r\n"
            "\tП = Новый Структура(\"А, Б\", А, Б);\r\n"
            "\tД = Новый Структура(\"А\", А);\r\n"
            "\tПустая = Новый Структура();\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        violations = analyze_path(path, checks={"struct-ctor-args"})
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].line_number, 2)

    # ------------------------------------------------------------------
    # if-nesting
    # ------------------------------------------------------------------

    def test_if_nesting_reports_third_level(self):
        text = (
            "Процедура Тест()\r\n"
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
        violations = analyze_path(path, checks={"if-nesting"})
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].line_number, 4)

    def test_if_nesting_allows_two_levels_and_preprocessor(self):
        text = (
            "Процедура Тест()\r\n"
            "\t#Если Сервер Тогда\r\n"
            "\tЕсли А Тогда\r\n"
            "\t\tЕсли Б Тогда\r\n"
            "\t\t\tДействие();\r\n"
            "\t\tКонецЕсли;\r\n"
            "\tКонецЕсли;\r\n"
            "\t#КонецЕсли\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        self.assertEqual(analyze_path(path, checks={"if-nesting"}), [])

    # ------------------------------------------------------------------
    # return-expression
    # ------------------------------------------------------------------

    def test_return_expression_reports_direct_return(self):
        text = (
            "Функция Тест()\r\n"
            "\tЕсли А Тогда\r\n"
            "\t\tВозврат Х;\r\n"
            "\tКонецЕсли;\r\n"
            "\tВозврат ВозвращаемоеЗначение;\r\n"
            "КонецФункции\r\n"
        )
        path = self.write_case(text)
        violations = analyze_path(path, checks={"return-expression"})
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].line_number, 3)

    def test_return_expression_allows_plain_and_canonical_return(self):
        text = (
            "Процедура Тест()\r\n"
            "\tЕсли А Тогда\r\n"
            "\t\tВозврат;\r\n"
            "\tКонецЕсли;\r\n"
            "КонецПроцедуры\r\n"
        )
        path = self.write_case(text)
        self.assertEqual(analyze_path(path, checks={"return-expression"}), [])

    # ------------------------------------------------------------------
    # CLI и выбор проверок
    # ------------------------------------------------------------------

    def test_checks_selection_limits_scope(self):
        text = "Процедура Тест()\r\n\tЕсли НЕ А Тогда\r\n\r\n\tКонецЕсли;\r\nКонецПроцедуры\r\n"
        path = self.write_case(text)
        violations = analyze_path(path, checks={"tab-rhythm"})
        self.assertEqual([v.check for v in violations], ["tab-rhythm"])

    def test_main_exit_codes(self):
        path = self.write_case("Процедура Тест()\r\n\tМ = Новый Массив;\r\nКонецПроцедуры\r\n")
        self.assertEqual(main([str(path)]), 1)
        self.assertEqual(main(["--fix", str(path)]), 0)
        self.assertEqual(main([str(path)]), 0)

    def test_main_fix_keeps_report_only_failure(self):
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
        self.assertEqual(main(["--fix", str(path)]), 1)

    def test_multiline_string_is_fully_protected(self):
        text = (
            "Функция ТекстЗапроса()\r\n"
            "\tВозвращаемоеЗначение = \"\r\n"
            "\t|ВЫБРАТЬ\r\n"
            "\t|\tНоменклатура.Ссылка,Номенклатура.Наименование\r\n"
            "\t|ГДЕ\r\n"
            "\t|\tНЕ Номенклатура.ПометкаУдаления\r\n"
            "\t|\tИ Номенклатура.ЭтоГруппа = &Новый Структура\";\r\n"
            "\tВозврат ВозвращаемоеЗначение;\r\n"
            "КонецФункции\r\n"
        )
        path = self.write_case(text)
        self.assertEqual(analyze_path(path), [])

    def test_expected_check_ids(self):
        self.assertEqual(
            set(CHECK_IDS),
            {
                "tab-rhythm",
                "operator-case",
                "empty-ctor-parens",
                "comma-space",
                "struct-ctor-args",
                "if-nesting",
                "return-expression",
            },
        )


if __name__ == "__main__":
    unittest.main()
