"""Static handoff contract checks, not a claim about live agent behavior."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "packages/design-playbook/skills/design-playbook/SKILL.md"


class PlanHandoffPromptTests(unittest.TestCase):
    def setUp(self):
        text = SKILL.read_text(encoding="utf-8")
        self.profile = text.split("## Run profile (tier grading)", 1)[1].split(
            "## Audit preferences", 1
        )[0]
        self.plan = text.split("### 4. plan (pipeline step — pure orchestration)", 1)[1].split(
            "\n### ", 1
        )[0]

    def test_run_profile_delegates_body_omission_to_plan(self):
        self.assertIn("step **4. plan**", self.profile)
        self.assertNotIn("skipping the rest of the plan body is legal", self.profile)

    def test_omission_requires_recorded_inputs_and_resolved_mapping(self):
        omission = self.plan.split("**Body omission (all conditions required):**", 1)[1].split(
            "**Full handoff:**", 1
        )[0]
        for marker in (
            "current on-disk artifacts",
            "all three handoff inputs",
            "file and section pointers",
            "no unresolved structural conflict",
            "unmapped item",
            "presentation input left to record",
            "skip list",
            "one-line reason",
            "Tier alone does not authorize omission",
            "scope, spec, reference constraints, or tier changes",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, omission)

    def test_reference_constraints_apply_to_both_handoff_paths(self):
        reference = self.plan.split("**Reference handoff (both paths):**", 1)[1].split(
            "\n\n", 1
        )[0]
        for marker in (
            "reference/contract.md",
            "functional constraints",
            "visual cues/exclusions",
            "skip entry",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, reference)

    def test_completion_accepts_full_or_profile_only_handoff(self):
        done = self.plan.split("**Done when:**", 1)[1]
        for marker in (
            "run-profile",
            "**Full handoff:**",
            "three blocks",
            "**Profile-only handoff:**",
            "body-omission conditions above",
            "without re-deriving scope from chat",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, done)

    def test_handoff_keeps_existing_authority_boundaries(self):
        self.assertIn("**not** a machine gate", self.plan)
        self.assertIn("required on disk", self.plan)
        self.assertIn("must open with the `run-profile`", self.plan)
        for block in ("This run's scope", "User description → spec mapping", "ui-picker input pack"):
            with self.subTest(block=block):
                self.assertIn(f"**{block}**", self.plan)
        self.assertIn("→ stop; revise `ux-spec`", self.plan)


if __name__ == "__main__":
    unittest.main()
