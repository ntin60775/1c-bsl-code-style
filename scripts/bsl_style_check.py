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

Строковые литералы (включая многострочные с `|`) и комментарии пропускаются:
ни проверки, ни `--fix` не меняют их содержимое. При `--fix` кодировка, BOM,
переводы строк и права файла сохраняются, запись атомарна.

Вывод: нарушения — в stdout строками `путь:строка: [check] сообщение` и ничего
больше; итог прогона — в stderr. Коды выхода: 0 — нарушений нет (или все
исправлены), 1 — нарушения остались, 2 — ошибка чтения или аргументов.
"""
from __future__ import annotations

import argparse
import bisect
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
import tempfile

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

_WORD = "А-Яа-яЁёA-Za-z0-9_"
_WORD_CLASS = rf"[{_WORD}]"
_NOT_WORD_BEFORE = rf"(?<!{_WORD_CLASS})"
_NOT_WORD_AFTER = rf"(?!{_WORD_CLASS})"

_METHOD_START_RE = re.compile(r"^(?:Асинх\s+)?(?:Процедура|Функция)" + _NOT_WORD_AFTER, re.IGNORECASE)
_METHOD_END_RE = re.compile(r"^(?:КонецПроцедуры|КонецФункции)" + _NOT_WORD_AFTER, re.IGNORECASE)
_CLOSING_OR_BRANCH_RE = re.compile(
    r"^(?:ИначеЕсли|Иначе|Исключение|КонецЕсли|КонецЦикла|КонецПопытки|КонецПроцедуры|КонецФункции)"
    + _NOT_WORD_AFTER,
    re.IGNORECASE,
)
_BLOCK_CLOSE_RE = re.compile(r"(?:КонецЕсли|КонецЦикла|КонецПопытки)" + _NOT_WORD_AFTER, re.IGNORECASE)
_BLOCK_OPEN_RE = re.compile(r"^(?:Если|ИначеЕсли|Для|Пока|Попытка|Иначе|Исключение)" + _NOT_WORD_AFTER, re.IGNORECASE)
_THEN_OR_LOOP_RE = re.compile(r"(?:Тогда|Цикл)\s*$", re.IGNORECASE)

_OPERATOR_RE = re.compile(rf"{_NOT_WORD_BEFORE}(Не|НЕ|не|И|и|Или|ИЛИ|или){_NOT_WORD_AFTER}")
_OPERATOR_CANON = {"не": "Не", "и": "И", "или": "Или"}
_CTOR_HEAD_RE = re.compile(rf"{_NOT_WORD_BEFORE}Новый[ \t]+([{_WORD}]+)", re.IGNORECASE)
_STRUCT_HEAD_RE = re.compile(rf"{_NOT_WORD_BEFORE}Новый[ \t]+Структура\s*\(", re.IGNORECASE)
# Запятая не в конце списка и не перед закрывающей скобкой: пробел обязателен.
# Табуляция тоже нарушение — правило про пробел.
_COMMA_RE = re.compile(r",(?![ \n\r)])")
_COMMA_FIX_RE = re.compile(r",[ \t]*(?=[^ \n\r)])")
_IF_TOKEN_RE = re.compile(rf"{_NOT_WORD_BEFORE}(ИначеЕсли|КонецЕсли|Если){_NOT_WORD_AFTER}", re.IGNORECASE)
_RETURN_STMT_RE = re.compile(rf"{_NOT_WORD_BEFORE}Возврат\s+(.+)$", re.IGNORECASE | re.DOTALL)
_STRING_LITERAL_RE = re.compile(r'"((?:[^"]|"")*)"')


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


def _code_spans(lines: list[str]) -> tuple[list[list[tuple[int, int]]], list[bool]]:
    """Спаны BSL-кода по строкам и признак «строка началась внутри литерала».

    Спаны (start, end) не включают строковые литералы (в том числе
    многострочные с продолжением `|`) и комментарии `//`. Строки, начавшиеся
    внутри многострочного литерала, помечаются: их пустая строка — часть
    литерала, а не пустая строка метода.
    """
    spans_per_line: list[list[tuple[int, int]]] = []
    literal_line: list[bool] = []
    in_string = False
    for raw in lines:
        body, _ = _strip_newline(raw)
        n = len(body)
        spans: list[tuple[int, int]] = []
        literal_line.append(in_string)
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
    return spans_per_line, literal_line


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


def _line_index(code_lines: list[str]) -> tuple[str, list[int], object]:
    """Склеенный code-view и таблица смещений начал строк."""
    joined = "\n".join(code_lines)
    starts: list[int] = []
    offset = 0
    for line in code_lines:
        starts.append(offset)
        offset += len(line) + 1
    return joined, starts, lambda position: bisect.bisect_right(starts, position)


# ---------------------------------------------------------------------------
# tab-rhythm
# ---------------------------------------------------------------------------


def _is_method_start(text: str) -> bool:
    return _METHOD_START_RE.match(_statement_text(text)) is not None


def _is_method_end(text: str) -> bool:
    return _METHOD_END_RE.match(_statement_text(text)) is not None


def _opens_body(text: str) -> bool:
    """Открывает ли строка тело блока — с учётом закрытия на той же строке."""
    stripped = _statement_text(text)
    if not stripped:
        return False
    if _is_method_start(stripped):
        return True
    if _BLOCK_CLOSE_RE.search(stripped):
        return False
    if _BLOCK_OPEN_RE.match(stripped):
        return True
    return _THEN_OR_LOOP_RE.search(stripped) is not None


def _is_closing_or_branch(text: str) -> bool:
    return _CLOSING_OR_BRANCH_RE.match(_statement_text(text)) is not None


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


def _blank_lines_to_check(
    code_lines: list[str],
    literal_line: list[bool],
) -> list[tuple[int, int, int]]:
    """Пустые строки тела метода: (индекс, method_start, method_end)."""
    result: list[tuple[int, int, int]] = []
    method_start: int | None = None
    for index, code_body in enumerate(code_lines):
        if method_start is None:
            if _is_method_start(code_body):
                method_start = index
            continue

        method_end = index if _is_method_end(code_body) else None
        if not literal_line[index] and code_body.strip("\t ") == "":
            end_bound = method_end if method_end is not None else len(code_lines) - 1
            result.append((index, method_start, end_bound))

        if method_end is not None:
            method_start = None
    return result


def _check_tab_rhythm(
    path: Path,
    raw_lines: list[str],
    code_lines: list[str],
    literal_line: list[bool],
) -> list[Violation]:
    violations: list[Violation] = []
    for index, method_start, method_end in _blank_lines_to_check(code_lines, literal_line):
        body, _ = _strip_newline(raw_lines[index])
        expected_tabs = _expected_tabs(code_lines, index, method_start, method_end)
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
    return violations


def _fix_tab_rhythm(
    raw_lines: list[str],
    code_lines: list[str],
    literal_line: list[bool],
) -> bool:
    changed = False
    for index, method_start, method_end in _blank_lines_to_check(code_lines, literal_line):
        body, newline = _strip_newline(raw_lines[index])
        expected_body = "\t" * _expected_tabs(code_lines, index, method_start, method_end)
        if body != expected_body:
            raw_lines[index] = expected_body + newline
            changed = True
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


def _ctor_matches_needing_parens(code_joined: str) -> list[int]:
    """Позиции конца `Новый <Тип>`, где скобки не открыты (в том числе на след. строке)."""
    positions: list[int] = []
    for match in _CTOR_HEAD_RE.finditer(code_joined):
        after = match.end()
        while after < len(code_joined) and code_joined[after] in " \t\n":
            after += 1
        if after < len(code_joined) and code_joined[after] == "(":
            continue
        positions.append(match.end())
    return positions


def _check_empty_ctor_parens(
    path: Path,
    code_lines: list[str],
) -> list[Violation]:
    joined, _starts, line_of = _line_index(code_lines)
    violations: list[Violation] = []
    for end in _ctor_matches_needing_parens(joined):
        line_number = line_of(end)
        violations.append(
            Violation(
                path=path,
                line_number=line_number,
                check="empty-ctor-parens",
                message="пустой конструктор без скобок",
            )
        )
    return violations


def _fix_empty_ctor_parens(raw_lines: list[str], code_lines: list[str]) -> bool:
    joined, starts, _line_of = _line_index(code_lines)
    positions = _ctor_matches_needing_parens(joined)
    if not positions:
        return False
    for position in sorted(positions, reverse=True):
        index = bisect.bisect_right(starts, position) - 1
        body, newline = _strip_newline(raw_lines[index])
        offset = position - starts[index]
        if 0 <= offset <= len(body):
            raw_lines[index] = body[:offset] + "()" + body[offset:] + newline
    return True


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
    return _COMMA_FIX_RE.sub(", ", segment)


# ---------------------------------------------------------------------------
# Report-only проверки
# ---------------------------------------------------------------------------


def _split_top_level_args(text: str) -> list[str]:
    """Аргументы вызова: запятые верхнего уровня, литералы не режутся."""
    parts: list[str] = []
    buffer: list[str] = []
    in_string = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            buffer.append(char)
            if char == '"':
                if index + 1 < len(text) and text[index + 1] == '"':
                    buffer.append('"')
                    index += 2
                    continue
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            buffer.append(char)
            index += 1
            continue
        if char == ",":
            parts.append("".join(buffer))
            buffer = []
            index += 1
            continue
        buffer.append(char)
        index += 1
    parts.append("".join(buffer))
    return parts


def _check_struct_ctor_args(path: Path, raw_joined: str, code_joined: str) -> list[Violation]:
    violations: list[Violation] = []
    starts: list[int] = []
    offset = 0
    for line in code_joined.split("\n"):
        starts.append(offset)
        offset += len(line) + 1

    for match in _STRUCT_HEAD_RE.finditer(code_joined):
        open_pos = match.end() - 1
        depth = 1
        index = match.end()
        while index < len(code_joined) and depth:
            char = code_joined[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        if depth:
            continue
        args_text = raw_joined[open_pos + 1:index - 1]
        args = [part for part in _split_top_level_args(args_text) if part.strip()]
        if not args:
            continue
        names = args[0].strip()
        names_count = 1
        literal = _STRING_LITERAL_RE.fullmatch(names)
        if literal is not None:
            names_count = len([part for part in literal.group(1).split(",") if part.strip()]) or 1
        bad = len(args) > 2 or (len(args) == 2 and names_count > 1)
        if bad:
            violations.append(
                Violation(
                    path=path,
                    line_number=bisect.bisect_right(starts, match.start()),
                    check="struct-ctor-args",
                    message="`Новый Структура` с более чем одним свойством; "
                    "нужна пустая структура и явные `Вставить(...)`",
                )
            )
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
        for token in _IF_TOKEN_RE.finditer(body):
            keyword = token.group(1).lower()
            if keyword == "конецесли":
                depth = max(0, depth - 1)
            elif keyword == "если":
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


def _statements(code_lines: list[str]) -> tuple[list[tuple[int, str]], list[int]]:
    """Операторы файла: (смещение начала, текст без `;`) и позиции переводов строк."""
    joined = "\n".join(code_lines)
    newlines = [index for index, char in enumerate(joined) if char == "\n"]
    result: list[tuple[int, str]] = []
    position = 0
    for part in joined.split(";"):
        result.append((position, part))
        position += len(part) + 1
    return result, newlines


def _check_return_expression(path: Path, code_lines: list[str]) -> list[Violation]:
    violations: list[Violation] = []
    statements, newlines = _statements(code_lines)
    for offset, statement in statements:
        match = _RETURN_STMT_RE.search(statement)
        if match is None:
            continue
        line_number = bisect.bisect_right(newlines, offset + match.start()) + 1
        expression = " ".join(match.group(1).split())
        if not expression or expression.casefold() == "возвращаемоезначение":
            continue
        violations.append(
            Violation(
                path=path,
                line_number=line_number,
                check="return-expression",
                message="прямой `Возврат Выражение;`; нужна форма через `ВозвращаемоеЗначение`",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# Драйвер
# ---------------------------------------------------------------------------


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """Запись через временный файл в каталоге цели; симлинк пишется в цель."""
    target = path.resolve() if path.is_symlink() else path
    descriptor, temporary = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.chmod(temporary, target.stat().st_mode & 0o7777)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def analyze_path(path: Path, checks: set[str] | None = None, fix: bool = False) -> list[Violation]:
    """Нарушения файла до применения `--fix`; при `fix` файл правится на месте."""
    selected = set(CHECK_IDS) if checks is None else set(checks)
    raw = path.read_bytes()
    text, has_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    spans, literal_line = _code_spans(lines)
    code_lines = _code_view(lines, spans)

    violations: list[Violation] = []
    if "tab-rhythm" in selected:
        violations.extend(_check_tab_rhythm(path, lines, code_lines, literal_line))
    if "operator-case" in selected:
        violations.extend(_check_operator_case(path, lines, spans))
    if "empty-ctor-parens" in selected:
        violations.extend(_check_empty_ctor_parens(path, code_lines))
    if "comma-space" in selected:
        violations.extend(_check_comma_space(path, lines, spans))
    if "struct-ctor-args" in selected:
        violations.extend(
            _check_struct_ctor_args(path, "\n".join(_strip_newline(line)[0] for line in lines), "\n".join(code_lines))
        )
    if "if-nesting" in selected:
        violations.extend(_check_if_nesting(path, code_lines))
    if "return-expression" in selected:
        violations.extend(_check_return_expression(path, code_lines))

    if fix:
        changed = False
        if "tab-rhythm" in selected:
            changed |= _fix_tab_rhythm(lines, code_lines, literal_line)
        if "empty-ctor-parens" in selected:
            spans, literal_line = _code_spans(lines)
            code_lines = _code_view(lines, spans)
            changed |= _fix_empty_ctor_parens(lines, code_lines)
        if selected & {"operator-case", "comma-space"}:
            spans, literal_line = _code_spans(lines)
            for index, (raw_line, line_spans) in enumerate(zip(lines, spans)):
                body, newline = _strip_newline(raw_line)
                rebuilt: list[str] = []
                pos = 0
                for start, end in line_spans:
                    rebuilt.append(body[pos:start])
                    segment = body[start:end]
                    if "operator-case" in selected:
                        segment = _fix_operator_case_segment(segment)
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
            _write_bytes_atomic(path, ("\ufeff" if has_bom else "").encode("utf-8") + output.encode("utf-8"))

    violations.sort(key=lambda v: (v.line_number, v.check))
    return violations


def _print_violations(violations: list[Violation]) -> None:
    for violation in violations:
        print(f"{violation.path}:{violation.line_number}: [{violation.check}] {violation.message}")


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
    errors = 0
    for path in args.paths:
        if path.is_dir():
            print(f"{path}: это каталог; чекер принимает файлы .bsl", file=sys.stderr)
            errors += 1
            continue
        if path.suffix.lower() != ".bsl":
            print(f"{path}: пропуск — не файл .bsl", file=sys.stderr)
            continue
        try:
            all_violations.extend(analyze_path(path, checks=selected, fix=args.fix))
        except OSError as error:
            print(f"{path}: ошибка чтения/записи: {error}", file=sys.stderr)
            errors += 1
        except UnicodeDecodeError as error:
            print(f"{path}: файл не в UTF-8 ({error}); чекер поддерживает только UTF-8", file=sys.stderr)
            errors += 1
    all_violations.sort(key=lambda v: (str(v.path), v.line_number, v.check))

    if errors:
        print(f"bsl_style_errors={errors}", file=sys.stderr)
        return 2

    if args.fix:
        residual: list[Violation] = []
        for path in args.paths:
            if path.suffix.lower() != ".bsl":
                continue
            try:
                residual.extend(analyze_path(path, checks=selected, fix=False))
            except (OSError, UnicodeDecodeError):
                continue
        residual.sort(key=lambda v: (str(v.path), v.line_number, v.check))
        _print_violations(residual)
        fixed = len(all_violations) - len(residual)
        print(f"bsl_style_violations={len(all_violations)} fixed={fixed}", file=sys.stderr)
        if residual:
            return 1
        print("bsl_style_check_ok", file=sys.stderr)
        return 0

    _print_violations(all_violations)
    if not all_violations:
        print("bsl_style_check_ok", file=sys.stderr)
        return 0
    print(f"bsl_style_violations={len(all_violations)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())