from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.bsl_style_check import CHECK_IDS


ROOT = Path(__file__).resolve().parents[1]


def _doc_paths() -> list[Path]:
    paths = [ROOT / "SKILL.md"]
    paths.extend(sorted((ROOT / "references").glob("*.md")))
    paths.extend(sorted((ROOT / "profiles").glob("*.md")))
    return paths


class SkillContractDocsTest(unittest.TestCase):
    def test_core_rules_are_public_contract(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        method_text = (ROOT / "references" / "method-composition.md").read_text(encoding="utf-8")
        formatting_text = (ROOT / "references" / "bsl-formatting.md").read_text(encoding="utf-8")

        self.assertIn("`Если...Тогда`", skill_text)
        self.assertIn("глубже двух уровней", skill_text)
        self.assertIn("глубже двух уровней", method_text)
        self.assertIn("утвердительн", method_text)
        self.assertIn("`Не`", skill_text)
        self.assertIn("`Или`", skill_text)
        self.assertIn("НЕ", formatting_text)
        self.assertIn("ИЛИ", formatting_text)
        self.assertIn("scripts/bsl_style_check.py", skill_text)

    def test_guard_covers_hard_rules(self) -> None:
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
        self.assertTrue((ROOT / "scripts" / "bsl_style_check.py").exists())

    def test_removed_layers_are_not_referenced(self) -> None:
        removed_terms = (
            "checks.jsonc",
            "full-reference-pass",
            "subagent",
            "субагент",
            "scout",
            "single-writer",
            "coverage-plan",
            "process/",
            "examples/",
            "agents/",
        )
        for path in _doc_paths():
            text = path.read_text(encoding="utf-8")
            for term in removed_terms:
                self.assertNotIn(term, text, f"{path}: найден удалённый слой `{term}`")

    def test_removed_files_are_absent(self) -> None:
        for relative in (
            "checks.jsonc",
            "process",
            "agents",
            "examples",
            "references/checklist.md",
            "references/runtime-contract.md",
            "references/few-shots.md",
            "references/verify-recipes.md",
            "references/query-texts.md",
            "references/orchestration.md",
            "scripts/check_bsl_blank_line_tab_rhythm.py",
        ):
            self.assertFalse((ROOT / relative).exists(), f"{relative} должен быть удалён")

    def test_every_rule_file_is_linked_from_skill(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for path in _doc_paths()[1:]:
            self.assertIn(str(path.relative_to(ROOT)), skill_text)

    def test_skill_json_version_and_description_match_public_files(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        skill_json = json.loads((ROOT / "skill.json").read_text(encoding="utf-8"))
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertEqual(skill_json["version"], version)
        self.assertIn(f'description: "{skill_json["description"]}"', skill_text)


if __name__ == "__main__":
    unittest.main()
