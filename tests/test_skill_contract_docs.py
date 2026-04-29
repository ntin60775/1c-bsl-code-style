from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillContractDocsTest(unittest.TestCase):
    def test_linear_branching_rule_is_public_contract(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        principles_text = (ROOT / "references" / "principles.md").read_text(encoding="utf-8")
        method_text = (ROOT / "references" / "method-composition.md").read_text(encoding="utf-8")
        checks_text = (ROOT / "checks.jsonc").read_text(encoding="utf-8")

        for text in (skill_text, principles_text, method_text):
            self.assertIn("`Если...Тогда`", text)
            self.assertIn("глубже двух уровней", text)
            self.assertIn("утвердительн", text)

        self.assertIn('"id": "CMP-005"', checks_text)
        self.assertIn("не глубже двух уровней", checks_text)
        self.assertIn('"mandatory_for": ["real-code"]', checks_text)

    def test_skill_json_version_and_description_match_public_files(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        skill_json = json.loads((ROOT / "skill.json").read_text(encoding="utf-8"))
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertEqual(skill_json["version"], version)
        self.assertIn(f'description: "{skill_json["description"]}"', skill_text)


if __name__ == "__main__":
    unittest.main()
