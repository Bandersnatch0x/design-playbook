"""Static bridge invariants, not a claim about live agent behavior."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "packages/design-playbook/scripts/adapter_templates/codex-agents.md"


class CodexWorkflowPromptTests(unittest.TestCase):
    def test_missing_preview_uses_skip_narration(self) -> None:
        install = TEMPLATE.read_text(encoding="utf-8").split("## Load order", 1)[0]

        self.assertNotIn("silently skips", install)
        self.assertIn("skip narration", install)

    def test_workflow_points_to_authority_instead_of_redeclaring_order(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        load_order = text.split("## Load order", 1)[1].split("## Compose", 1)[0]

        self.assertIn("skills/design-playbook/SKILL.md", load_order)
        self.assertNotIn("Standard order:", load_order)
        self.assertNotIn("Native desktop order:", load_order)
        self.assertIn("run_profile.py route", load_order)


if __name__ == "__main__":
    unittest.main()
