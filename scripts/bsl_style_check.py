#!/usr/bin/env python3
"""Машинный guard детерминированных правил стиля `1c-bsl-code-style`.

Check-id:
- tab-rhythm          пустые строки внутри методов держат tab-уровень блока (fix);
- operator-case       операторы только `Не`, `И`, `Или` (fix);
- empty-ctor-parens   пустой конструктор пишется со скобками (fix);
- comma-space         после запятой в списке аргументов стоит пробел (fix);
- struct-ctor-args    `Новый Структура` не более чем с одним значением (report);
- if-nesting          вложенность `Если...Тогда` не глубже двух уровней (report);
- return-expression   нет прямого `Возврат Выражение;`, кроме финального
                      `Возврат ВозвращаемоеЗначение;` (report).

Строковые литералы (включая многострочные с `|`) и комментарии пропускаются.
При `--fix` кодировка, BOM и переводы строк сохраняются.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

CHECK_IDS = (
    "tab-rhythm",
    "operator-case",
    "empty-ctor-parens",
    "comma-space",
    "struct-ctor-args",
    "if-nesting",
    "return-expression",
)

FIXABLE = frozenset({"tab-rhythm", "operator-case", "empty-ctor-parens", "comma-space"})

METHOD_START = ("Процедура", "Функция")
METHOD_END = ("КонецПроцедуры", "КонецФункции")
BRANCH_OR_BLOCK_START = (
    "Если ",
    "ИначеЕсли ",
    "Иначе",
    "Для ",
    "Пока ",
    "Попытка",
    "Исключение",
)
CLOSING_OR_BRANCH = (
    "ИначеЕсли ",
    "Иначе",
    "Исключение",
    "КонецЕсли",
    "КонецЦикла",
    "КонецПопытки",
    "КонецПроцедуры",
    "КонецФункции",
)

_WORD = "А-Яа-яЁёA-Za-z0-9_"
_OPERATOR_RE = re.compile(rf"(?<![{_WORD}])(Не|НЕ|не|И|и|Или|ИЛИ|или)(?![{_WORD}])")
_OPERATOR_CANON = {"не": "Не", "и": "И", "или": "Или"}
_CTOR_HEAD_RE = re.compile(rf"(?<![{_WORD}])Новый(\s+)([{_WORD}]+)")
_STRUCT_CTOR_RE = re.compile(r'Новый\s+Структура\s*\(\s*"([^"]*)"')
_COMMA_RE = re.compile(r",(?=[^\s)])")
_RETURN_RE = re.compile(r"Возврат\s+(.+?)\s*;\s*$")
_IF_OPEN_RE = re.compile(r"Если(?:\s|\()")
_IF_CLOSE_RE = re.compile(r"КонецЕсли\b")


@dataclass(frozen=True)
class Violation:
    path: Path
    line_number: int
    check: str
    message: str


# ---------------------------------------------------------------------------
# Базовые лексические помощники
# ---------------------------------------------------------------------------


def _strip_newline(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def _decode(raw: bytes) -> tuple[str, bool]:
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), has_bom


def _leading_tabs(text: str) -> int:
    return len(text) - len(text.lstrip("\t"))


def _statement_text(text: str) -> str:
    return text.lstrip("\t ")


def _code_spans(lines: list[str]) -> list[list[tuple[int, int]]]:
    """Для каждой строки (с переводом строки) вернуть спаны BSL-кода.

    Спаны (start, end) не включают строковые литералы (в том числе
    многострочные с продолжением `|`) и комментарии `//`.
    """
    spans_per_line: list[list[tuple[int, int]]] = []
    in_string = False
    for raw in lines:
        body, _ = _strip_newline(raw)
        n = len(body)
        spans: list[tuple[int, int]] = []
        i = 0
        span_start: int | None = 0
        if in_string:
            span_start = None
            while i < n and body[i] in " \t":
                i += 1
            if i < n and body[i] == "|":
                i += 1
            while i < n:
                if body[i] == '"':
                    if i + 1 < n and body[i + 1] == '"':
                        i += 2
                        continue
                    i += 1
                    in_string = False
                    span_start = i
                    break
                i += 1
        while i < n:
            if body[i] == "/" and i + 1 < n and body[i + 1] == "/":
                break
            if body[i] == '"':
                if span_start is not None and i > span_start:
                    spans.append((span_start, i))
                span_start = None
                i += 1
                in_string = True
                while i < n:
                    if body[i] == '"':
                        if i + 1 < n and body[i + 1] == '"':
                            i += 2
                            continue
                        i += 1
                        in_string = False
                        break
                    i += 1
                if not in_string:
                    span_start = i
                continue
            i += 1
        if span_start is not None and span_start < i:
            spans.append((span_start, i))
        spans_per_line.append(spans)
    return spans_per_line


def _code_view(lines: list[str], spans: list[list[tuple[int, int]]]) -> list[str]:
    """Строки, где строки-литералы и комментарии заменены пробелами."""
    view: list[str] = []
    for raw, line_spans in zip(lines, spans):
        body, _ = _strip_newline(raw)
        chars = [" "] * len(body)
        for start, end in line_spans:
            chars[start:end] = body[start:end]
        view.append("".join(chars))
    return view


# ---------------------------------------------------------------------------
# tab-rhythm (перенесено из check_bsl_blank_line_tab_rhythm.py)
# ---------------------------------------------------------------------------


def _is_method_start(text: str) -> bool:
    stripped = _statement_text(text)
    return any(stripped.startswith(keyword + " ") or stripped.startswith(keyword + "(") for keyword in METHOD_START)


def _is_method_end(text: str) -> bool:
    stripped = _statement_text(text)
    return any(stripped.startswith(keyword) for keyword in METHOD_END)


def _opens_body(text: str) -> bool:
    stripped = _statement_text(text)
    if _is_method_start(text):
        return True
    if stripped.endswith(" Тогда") or stripped.endswith(" Цикл"):
        return True
    return any(stripped.startswith(keyword) for keyword in BRANCH_OR_BLOCK_START)


def _is_closing_or_branch(text: str) -> bool:
    stripped = _statement_text(text)
    return any(stripped.startswith(keyword) for keyword in CLOSING_OR_BRANCH)


def _previous_nonblank(lines: list[str], start: int, method_start: int) -> int | None:
    for index in range(start - 1, method_start - 1, -1):
        body, _ = _strip_newline(lines[index])
        if body.strip("\t "):
            return index
    return None


def _next_nonblank(lines: list[str], start: int, method_end: int) -> int | None:
    for index in range(start + 1, method_end + 1):
        body, _ = _strip_newline(lines[index])
        if body.strip("\t "):
            return index
    return None


def _expected_tabs(lines: list[str], index: int, method_start: int, method_end: int) -> int:
    prev_index = _previous_nonblank(lines, index, method_start)
    next_index = _next_nonblank(lines, index, method_end)

    prev_text = _strip_newline(lines[prev_index])[0] if prev_index is not None else ""
    next_text = _strip_newline(lines[next_index])[0] if next_index is not None else ""

    if next_index is not None and _is_closing_or_branch(next_text):
        return max(1, _leading_tabs(next_text) + 1)
    if prev_index is not None and _opens_body(prev_text):
        return max(1, _leading_tabs(prev_text) + 1)
    if prev_index is not None and next_index is not None:
        return max(1, min(_leading_tabs(prev_text), _leading_tabs(next_text)))
    if prev_index is not None:
        return max(1, _leading_tabs(prev_text))
    if next_index is not None:
        return max(1, _leading_tabs(next_text))
    return 1


def _blank_line_reason(body: str, actual_tabs: int, expected_tabs: int) -> str:
    if body == "":
        return "пустая строка без табов внутри тела метода"
    if body.strip("\t") != "":
        return "пустая строка содержит пробелы вместо отступа из табов"
    if actual_tabs < expected_tabs:
        return "у пустой строки меньше табов, чем у текущего BSL-блока"
    return "у пустой строки больше табов, чем у текущего BSL-блока"


def _check_tab_rhythm(
    path: Path,
    raw_lines: list[str],
    code_lines: list[str],
) -> list[Violation]:
    violations: list[Violation] = []
    method_start: int | None = None
    for index, code_body in enumerate(code_lines):
        if method_start is None:
            if _is_method_start(code_body):
                method_start = index
            continue

        method_end = index if _is_method_end(code_body) else None
        body, _ = _strip_newline(raw_lines[index])
        if body.strip("\t ") == "":
            end_bound = method_end if method_end is not None else len(code_lines) - 1
            expected_tabs = _expected_tabs(code_lines, index, method_start, end_bound)
            actual_tabs = _leading_tabs(body)
            if body != "\t" * expected_tabs:
                violations.append(
                    Violation(
                        path=path,
                        line_number=index + 1,
                        check="tab-rhythm",
                        message=f"{_blank_line_reason(body, actual_tabs, expected_tabs)}: "
                        f"ожидается {expected_tabs} таб., найдено {actual_tabs}",
                    )
                )

        if method_end is not None:
            method_start = None
    return violations


def _fix_tab_rhythm(raw_lines: list[str], code_lines: list[str]) -> bool:
    changed = False
    method_start: int | None = None
    for index, code_body in enumerate(code_lines):
        if method_start is None:
            if _is_method_start(code_body):
                method_start = index
            continue

        method_end = index if _is_method_end(code_body) else None
        body, newline = _strip_newline(raw_lines[index])
        if body.strip("\t ") == "":
            end_bound = method_end if method_end is not None else len(code_lines) - 1
            expected_tabs = _expected_tabs(code_lines, index, method_start, end_bound)
            expected_body = "\t" * expected_tabs
            if body != expected_body:
                raw_lines[index] = expected_body + newline
                changed = True

        if method_end is not None:
            method_start = None
    return changed


# ---------------------------------------------------------------------------
# Проверки по code-спанам строк
# ---------------------------------------------------------------------------


def _spans_of_line(body: str, line_spans: list[tuple[int, int]]) -> list[str]:
    return [body[start:end] for start, end in line_spans]


def _check_operator_case(path: Path, lines: list[str], spans: list[list[tuple[int, int]]]) -> list[Violation]:
    violations: list[Violation] = []
    for index, (raw, line_spans) in enumerate(zip(lines, spans)):
        body, _ = _strip_newline(raw)
        bad: list[str] = []
        for segment in _spans_of_line(body, line_spans):
            for match in _OPERATOR_RE.finditer(segment):
                canon = _OPERATOR_CANON[match.group(1).lower()]
                if match.group(1) != canon:
                    bad.append(f"{match.group(1)}→{canon}")
        if bad:
            violations.append(
                Violation(
                    path=path,
                    line_number=index + 1,
                    check="operator-case",
                    message="неканонический регистр операторов: " + ", ".join(bad),
                )
            )
    return violations


def _fix_operator_case_segment(segment: str) -> str:
    return _OPERATOR_RE.sub(lambda m: _OPERATOR_CANON[m.group(1).lower()], segment)


def _check_empty_ctor_parens(path: Path, lines: list[str], spans: list[list[tuple[int, int]]]) -> list[Violation]:
    violations: list[Violation] = []
    for index, (raw, line_spans) in enumerate(zip(lines, spans)):
        body, _ = _strip_newline(raw)
        for segment in _spans_of_line(body, line_spans):
            for match in _CTOR_HEAD_RE.finditer(segment):
                rest = segment[match.end():]
                if not rest.lstrip(" \t").startswith("("):
                    violations.append(
                        Violation(
                            path=path,
                            line_number=index + 1,
                            check="empty-ctor-parens",
                            message=f"пустой конструктор без скобок: `{match.group(0).strip()}`",
                        )
                    )
    return violations


def _fix_empty_ctor_parens_segment(segment: str) -> str:
    def _insert(match: re.Match[str]) -> str:
        rest = segment[match.end():]
        if rest.lstrip(" \t").startswith("("):
            return match.group(0)
        return f"Новый{match.group(1)}{match.group(2)}()"

    return _CTOR_HEAD_RE.sub(_insert, segment)


def _check_comma_space(path: Path, lines: list[str], spans: list[list[tuple[int, int]]]) -> list[Violation]:
    violations: list[Violation] = []
    for index, (raw, line_spans) in enumerate(zip(lines, spans)):
        body, _ = _strip_newline(raw)
        for segment in _spans_of_line(body, line_spans):
            if _COMMA_RE.search(segment):
                violations.append(
                    Violation(
                        path=path,
                        line_number=index + 1,
                        check="comma-space",
                        message="после запятой в списке аргументов нет пробела",
                    )
                )
                break
    return violations


def _fix_comma_space_segment(segment: str) -> str:
    return _COMMA_RE.sub(", ", segment)


# ---------------------------------------------------------------------------
# Report-only проверки
# ---------------------------------------------------------------------------


def _check_struct_ctor_args(path: Path, lines: list[str], spans: list[list[tuple[int, int]]]) -> list[Violation]:
    violations: list[Violation] = []
    for index, (raw, line_spans) in enumerate(zip(lines, spans)):
        body, _ = _strip_newline(raw)
        for match in _STRUCT_CTOR_RE.finditer(body):
            if not any(start <= match.start() < end for start, end in line_spans):
                continue
            if "," in match.group(1):
                violations.append(
                    Violation(
                        path=path,
                        line_number=index + 1,
                        check="struct-ctor-args",
                        message="`Новый Структура` с более чем одним свойством; "
                        "нужна пустая структура и явные `Вставить(...)`",
                    )
                )
                break
    return violations


def _check_if_nesting(path: Path, code_lines: list[str]) -> list[Violation]:
    violations: list[Violation] = []
    depth = 0
    in_method = False
    for index, body in enumerate(code_lines):
        statement = _statement_text(body)
        if statement.startswith("#"):
            continue
        if not in_method and _is_method_start(body):
            in_method = True
            depth = 0
            continue
        if not in_method:
            continue
        if _is_method_end(body):
            in_method = False
            depth = 0
            continue
        if _IF_CLOSE_RE.match(statement):
            depth = max(0, depth - 1)
            continue
        if statement.startswith(("ИначеЕсли", "Иначе")):
            continue
        if _IF_OPEN_RE.match(statement):
            depth += 1
            if depth > 2:
                violations.append(
                    Violation(
                        path=path,
                        line_number=index + 1,
                        check="if-nesting",
                        message=f"вложенность `Если...Тогда` — {depth} уровня; допускается не более двух",
                    )
                )
    return violations


def _check_return_expression(path: Path, code_lines: list[str]) -> list[Violation]:
    violations: list[Violation] = []
    for index, body in enumerate(code_lines):
        statement = _statement_text(body).rstrip()
        match = _RETURN_RE.match(statement)
        if match and match.group(1).strip() != "ВозвращаемоеЗначение":
            violations.append(
                Violation(
                    path=path,
                    line_number=index + 1,
                    check="return-expression",
                    message="прямой `Возврат Выражение;`; нужна форма через `ВозвращаемоеЗначение`",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Драйвер
# ---------------------------------------------------------------------------


def analyze_path(path: Path, checks: set[str] | None = None, fix: bool = False) -> list[Violation]:
    selected = set(CHECK_IDS) if checks is None else set(checks)
    raw = path.read_bytes()
    text, has_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    spans = _code_spans(lines)
    code_lines = _code_view(lines, spans)

    violations: list[Violation] = []
    if "tab-rhythm" in selected:
        violations.extend(_check_tab_rhythm(path, lines, code_lines))
    if "operator-case" in selected:
        violations.extend(_check_operator_case(path, lines, spans))
    if "empty-ctor-parens" in selected:
        violations.extend(_check_empty_ctor_parens(path, lines, spans))
    if "comma-space" in selected:
        violations.extend(_check_comma_space(path, lines, spans))
    if "struct-ctor-args" in selected:
        violations.extend(_check_struct_ctor_args(path, lines, spans))
    if "if-nesting" in selected:
        violations.extend(_check_if_nesting(path, code_lines))
    if "return-expression" in selected:
        violations.extend(_check_return_expression(path, code_lines))

    if fix:
        changed = False
        if "tab-rhythm" in selected:
            changed |= _fix_tab_rhythm(lines, code_lines)
        if selected & {"operator-case", "empty-ctor-parens", "comma-space"}:
            for index, (raw_line, line_spans) in enumerate(zip(lines, spans)):
                body, newline = _strip_newline(raw_line)
                rebuilt: list[str] = []
                pos = 0
                for start, end in line_spans:
                    rebuilt.append(body[pos:start])
                    segment = body[start:end]
                    if "operator-case" in selected:
                        segment = _fix_operator_case_segment(segment)
                    if "empty-ctor-parens" in selected:
                        segment = _fix_empty_ctor_parens_segment(segment)
                    if "comma-space" in selected:
                        segment = _fix_comma_space_segment(segment)
                    rebuilt.append(segment)
                    pos = end
                rebuilt.append(body[pos:])
                fixed_body = "".join(rebuilt)
                if fixed_body != body:
                    lines[index] = fixed_body + newline
                    changed = True
        if changed:
            output = "".join(lines)
            path.write_bytes(("\ufeff" if has_bom else "").encode("utf-8") + output.encode("utf-8"))

    violations.sort(key=lambda v: (v.line_number, v.check))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Проверяет детерминированные правила стиля 1c-bsl-code-style.",
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--checks",
        default=",".join(CHECK_IDS),
        help="Список check-id через запятую; по умолчанию все.",
    )
    parser.add_argument("--fix", action="store_true", help="Исправить автоматически исправимые нарушения.")
    args = parser.parse_args(argv)

    selected = {item.strip() for item in args.checks.split(",") if item.strip()}
    unknown = selected - set(CHECK_IDS)
    if unknown:
        parser.error(f"неизвестные check-id: {', '.join(sorted(unknown))}")

    all_violations: list[Violation] = []
    for path in args.paths:
        all_violations.extend(analyze_path(path, checks=selected, fix=args.fix))
    all_violations.sort(key=lambda v: (str(v.path), v.line_number, v.check))

    for violation in all_violations:
        print(f"{violation.path}:{violation.line_number}: [{violation.check}] {violation.message}")

    if not all_violations:
        print("bsl_style_check_ok")
        return 0

    if args.fix:
        fixed = sum(1 for violation in all_violations if violation.check in FIXABLE)
        print(f"bsl_style_violations={len(all_violations)} fixed={fixed}")
        return 0 if fixed == len(all_violations) else 1

    print(f"bsl_style_violations={len(all_violations)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
