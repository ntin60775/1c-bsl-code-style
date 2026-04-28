#!/usr/bin/env python3
"""Проверяет tab-rhythm пустых строк внутри BSL-методов."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

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


@dataclass(frozen=True)
class Violation:
    path: Path
    line_number: int
    actual_tabs: int
    expected_tabs: int
    reason: str


def _strip_newline(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def _leading_tabs(text: str) -> int:
    return len(text) - len(text.lstrip("\t"))


def _statement_text(text: str) -> str:
    return text.lstrip("\t ")


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


def _line_reason(body: str, actual_tabs: int, expected_tabs: int) -> str:
    if body == "":
        return "blank line has no tabs inside method body"
    if body.strip("\t") != "":
        return "blank line contains spaces instead of tab-only indentation"
    if actual_tabs < expected_tabs:
        return "blank line has fewer tabs than current BSL block level"
    return "blank line has more tabs than current BSL block level"


def _decode(raw: bytes) -> tuple[str, bool]:
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), has_bom


def analyze_path(path: Path, fix: bool = False) -> list[Violation]:
    raw = path.read_bytes()
    text, has_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    violations: list[Violation] = []
    changed = False

    method_start: int | None = None
    for index, line in enumerate(lines):
        body, newline = _strip_newline(line)
        if method_start is None:
            if _is_method_start(body):
                method_start = index
            continue

        method_end = index if _is_method_end(body) else None
        if body.strip("\t ") == "":
            expected_tabs = _expected_tabs(lines, index, method_start, method_end if method_end is not None else len(lines) - 1)
            actual_tabs = _leading_tabs(body)
            expected_body = "\t" * expected_tabs
            if body != expected_body:
                violations.append(
                    Violation(
                        path=path,
                        line_number=index + 1,
                        actual_tabs=actual_tabs,
                        expected_tabs=expected_tabs,
                        reason=_line_reason(body, actual_tabs, expected_tabs),
                    )
                )
                if fix:
                    lines[index] = expected_body + newline
                    changed = True

        if method_end is not None:
            method_start = None

    if fix and changed:
        output = "".join(lines)
        path.write_bytes(("\ufeff" if has_bom else "").encode("utf-8") + output.encode("utf-8"))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверяет пустые строки BSL на tab-rhythm внутри методов.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--fix", action="store_true", help="Исправить отступы пустых строк на ожидаемое число табов.")
    args = parser.parse_args(argv)

    all_violations: list[Violation] = []
    for path in args.paths:
        all_violations.extend(analyze_path(path, fix=args.fix))

    for violation in all_violations:
        print(
            f"{violation.path}:{violation.line_number}: "
            f"expected {violation.expected_tabs} tab(s), found {violation.actual_tabs}: {violation.reason}"
        )

    if all_violations:
        action = "fixed" if args.fix else "found"
        print(f"blank_line_tab_rhythm_{action}={len(all_violations)}")
        return 0 if args.fix else 1

    print("blank_line_tab_rhythm_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
