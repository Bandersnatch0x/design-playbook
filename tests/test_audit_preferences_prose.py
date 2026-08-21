#!/usr/bin/env python3
"""Prose-contract lockstep for the audit-preferences orchestration integration.

Issue #70 (ADR-0033 D7/D10): the design-playbook SKILL.md consumes the
audit_preferences module output — these tests pin the prose seam so the
read -> trim -> skip-list -> limitation flow, the folded first ask, the
write-back semantics, and the skeleton forgery boundary cannot drift out
of the skill silently. Prose has no runtime surface; this lockstep is its
machine-checked face, mirroring the AdaptiveRoutingSkillContractTests
precedent.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
MAIN_SKILL = PKG / "skills" / "design-playbook" / "SKILL.md"
CODEX_AGENTS = PKG / "codex" / "AGENTS.md"
README_EN = ROOT / "README.md"
README_ZH = ROOT / "README-zh.md"


def _section(text: str, heading: str, end: str) -> str:
    start = text.index(heading)
    stop = text.index(end, start)
    return text[start:stop]


class AuditPreferencesProseContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = MAIN_SKILL.read_text(encoding="utf-8")
        self.section = _section(self.text, "## Audit preferences (ADR-0033)",
                                "\n## Steps")

    def test_section_consumes_the_module_without_reconstructing_it(self) -> None:
        # D7: prose reads the module output; no decision-table rebuild.
        self.assertIn(
            "audit_preferences.py plan --repo-root", self.section)
        self.assertIn("--declaration", self.section)
        self.assertIn("never reconstruct its precedence", self.section)
        self.assertIn("run_profile.py route", self.section)
        self.assertIn("receives no preference input", self.section)

    def test_first_ask_folds_into_tier_confirmation(self) -> None:
        # D10 + security boundary: one interruption; repo authors cannot
        # pre-authorize audit skips on behalf of the current user.
        self.assertIn("asked: false", self.section)
        self.assertIn("tier-confirmation exchange", self.section)
        self.assertIn("one interruption, not two", self.section)
        self.assertIn("source: repo", self.section)
        self.assertIn("not proof of this user's choice", self.section)
        self.assertIn("Never silently treat repository `asked: true`", self.section)

    def test_write_back_semantics_and_file_locations(self) -> None:
        # D6/D11: repo default vs local override; this-run-only exemption.
        self.assertIn("write_back(", self.section)
        self.assertIn("preferences.yaml", self.section)
        self.assertIn("preferences.local.yaml", self.section)
        self.assertIn("automatically ensures", self.section)
        self.assertIn(".gitignore", self.section)
        self.assertIn("this_run_only=True", self.section)
        self.assertIn("not persisted", self.section)

    def test_invalid_layers_do_not_override_merged_asked_state(self) -> None:
        self.assertIn("Each `invalid_files` entry names one corrupt layer", self.section)
        self.assertIn("decide whether to ask from `asked`", self.section)

    def test_skip_list_and_limitation_recording(self) -> None:
        # D4: silent skips are illegal; absence of evidence is named.
        self.assertIn("skip list", self.section)
        self.assertIn("silent skips are illegal", self.section)
        self.assertIn("limitation statement", self.section)

    def test_skeleton_pointback_and_forgery_boundary(self) -> None:
        # D5/D12: skeleton keeps the chain honest, never a forgery channel.
        self.assertIn("skeleton_pointback(", self.section)
        self.assertIn("audited: false", self.section)
        self.assertIn("--strict", self.section)
        self.assertIn("not a forgery channel", self.section)

    def test_tier_obligation_waiver_recorded(self) -> None:
        # D8: explicit skip is the downgrade authorization, recorded.
        self.assertIn("Tier-obligation waiver", self.section)
        self.assertIn("ADR-0033 D8", self.section)
        self.assertIn("recorded in the skip list", self.section)

    def test_hard_floor_never_skippable(self) -> None:
        # D1: fill + preview confirmation are outside the selectable set.
        self.assertIn(
            "Fill and the preview confirmation (ADR-0008 floor) never are",
            self.section)

    def test_steps_carry_recognition_branches(self) -> None:
        # Steps 8/9/10 trim on the plan payload, not on agent judgment.
        self.assertIn("craft_guard.runs: false", self.text)
        self.assertIn("observe.runs: false", self.text)
        self.assertIn("ui_evaluator.runs: false", self.text)
        # The accept step keeps the skeleton branch next to the audited path.
        accept = _section(self.text, "### 10. Accept", "\n## Recirculate")
        self.assertIn("skeleton", accept)
        self.assertIn(
            "authoritative verdict completion criterion in `ui-evaluator`",
            accept)


class DualHostConsistencyTests(unittest.TestCase):
    def test_codex_bridge_points_at_the_same_authority(self) -> None:
        text = CODEX_AGENTS.read_text(encoding="utf-8")
        self.assertIn("Audit preferences (ADR-0033)", text)
        self.assertIn("skills/design-playbook/SKILL.md", text)
        self.assertIn("sole authority", text)
        # Bridge stays pointer-only; mechanism details belong to SKILL.md.
        self.assertNotIn("audit_preferences.py plan", text)
        self.assertNotIn("audited: false", text)


class ReleaseSurfaceLegendTests(unittest.TestCase):
    """Issue #71: the README pipeline legend marks the three audit stages
    user-selectable, identically in both languages (dual-host visible
    wording). The ``\u2020`` marker joins the existing ``?``/``*`` legend
    without reusing their semantics."""

    def _readme_pair(self) -> tuple[str, str]:
        return (
            README_EN.read_text(encoding="utf-8"),
            README_ZH.read_text(encoding="utf-8"),
        )

    def test_flow_line_marks_the_three_stages(self) -> None:
        en, zh = self._readme_pair()
        for text in (en, zh):
            self.assertIn("craft-guard\u2020", text)
            self.assertIn("ui-evaluator\u2020", text)

    def test_legend_explains_user_selectable_semantics(self) -> None:
        en, zh = self._readme_pair()
        self.assertIn("user-selectable", en)
        self.assertIn("\u7528\u6237\u53ef\u9009", zh)
        for text in (en, zh):
            self.assertIn("ADR-0033", text)

    def test_legend_states_memory_files_and_skeleton_honesty(self) -> None:
        en, zh = self._readme_pair()
        for text in (en, zh):
            self.assertIn(".design-playbook/preferences.yaml", text)
            self.assertIn("preferences.local.yaml", text)
            self.assertIn("audited: false", text)


if __name__ == "__main__":
    unittest.main()
