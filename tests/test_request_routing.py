#!/usr/bin/env python3
"""Public-interface tests for adaptive Design I/O entry routing (ADR-0032)."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
MAIN_SKILL = PKG / "skills" / "design-playbook" / "SKILL.md"
UI_PICKER_SKILL = PKG / "skills" / "ui-picker" / "SKILL.md"
BASELINE_SKILL = PKG / "skills" / "design-baseline" / "SKILL.md"
INTAKE_SKILL = PKG / "skills" / "reference-intake" / "SKILL.md"
CODEX_AGENTS = PKG / "codex" / "AGENTS.md"
FIRST_RUN = PKG / "skills" / "design-playbook" / "references" / "first-run.md"


def _heading_section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start:]
    next_heading = rest.find("\n### ", 1)
    return rest if next_heading < 0 else rest[:next_heading]


def _done_when(section: str) -> str:
    marker = "**Done when:**"
    return section[section.rindex(marker) :]

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts.run_profile import (  # noqa: E402
    RequestFacts,
    route_request,
)


DEFAULT_REQUEST_FACTS = RequestFacts(
    intent="build",
    durable_design_artifacts=False,
    consequence="feature",
    existing_product=False,
    has_references=False,
    spec_present=True,
    baseline_ready=False,
    reference_contract_ready=False,
    adds_decided_fields=False,
    revises_decided_fields=False,
    declaration_domains=1,
)


def request_facts(**overrides: object) -> RequestFacts:
    return replace(DEFAULT_REQUEST_FACTS, **overrides)


class RequestRoutingTests(unittest.TestCase):
    def test_read_only_review_has_no_run_requirements(self) -> None:
        decision = route_request(
            request_facts(
                intent="review",
                consequence="none",
                existing_product=True,
                has_references=True,
                spec_present=False,
                declaration_domains=0,
            )
        )

        self.assertEqual(decision.mode, "no-run")
        self.assertIsNone(decision.tier)
        self.assertFalse(decision.requires_baseline)
        self.assertFalse(decision.requires_reference_contract)
        self.assertFalse(decision.requires_spec)

    def test_other_read_only_intents_also_skip_the_run(self) -> None:
        for intent in ("answer", "diagnose", "plan"):
            with self.subTest(intent=intent):
                decision = route_request(
                    request_facts(
                        intent=intent,
                        consequence="none",
                        spec_present=False,
                        declaration_domains=0,
                    )
                )
                self.assertEqual(decision.mode, "no-run")
                self.assertIsNone(decision.tier)

    def test_local_fix_starts_a_p1_design_run(self) -> None:
        decision = route_request(
            request_facts(
                intent="fix",
                consequence="local",
            )
        )

        self.assertEqual(decision.mode, "design-run")
        self.assertEqual(decision.tier, "P1")
        self.assertEqual(
            decision.criteria,
            ("intent: fix", "consequence: local", "decided-fields: unchanged"),
        )

    def test_additive_build_starts_a_p2_design_run(self) -> None:
        decision = route_request(
            request_facts(
                adds_decided_fields=True,
            )
        )

        self.assertEqual(decision.mode, "design-run")
        self.assertEqual(decision.tier, "P2")

    def test_new_decided_field_promotes_a_local_fix_to_p2(self) -> None:
        decision = route_request(
            request_facts(
                intent="fix",
                consequence="local",
                adds_decided_fields=True,
            )
        )

        self.assertEqual(decision.mode, "design-run")
        self.assertEqual(decision.tier, "P2")

    def test_other_build_and_fix_requests_default_to_p2(self) -> None:
        for intent, consequence in (("build", "local"), ("fix", "feature")):
            with self.subTest(intent=intent, consequence=consequence):
                decision = route_request(
                    request_facts(
                        intent=intent,
                        consequence=consequence,
                    )
                )

                self.assertEqual(decision.mode, "design-run")
                self.assertEqual(decision.tier, "P2")

    def test_each_p3_trigger_overrides_lower_tiers(self) -> None:
        cases = (
            (
                request_facts(consequence="structural"),
                ("consequence: structural",),
            ),
            (
                request_facts(
                    intent="fix",
                    consequence="local",
                    revises_decided_fields=True,
                ),
                ("decided-fields: revise",),
            ),
            (
                request_facts(declaration_domains=2),
                ("declaration-domains: 2",),
            ),
        )

        for facts, expected_criteria in cases:
            with self.subTest(facts=facts):
                decision = route_request(facts)
                self.assertEqual(decision.mode, "design-run")
                self.assertEqual(decision.tier, "P3")
                self.assertEqual(decision.criteria, expected_criteria)

    def test_p3_conditions_apply_to_every_design_run_entry(self) -> None:
        cases = (
            request_facts(
                intent="prototype",
                consequence="structural",
            ),
            request_facts(
                intent="plan",
                durable_design_artifacts=True,
                revises_decided_fields=True,
            ),
        )

        for facts in cases:
            with self.subTest(facts=facts):
                self.assertEqual(route_request(facts).tier, "P3")

    def test_prototype_starts_a_design_run(self) -> None:
        decision = route_request(
            request_facts(
                intent="prototype",
                consequence="none",
                spec_present=False,
                declaration_domains=0,
            )
        )

        self.assertEqual(decision.mode, "design-run")
        self.assertEqual(decision.tier, "P2")

    def test_durable_design_artifact_starts_a_run_for_read_only_intent(self) -> None:
        decision = route_request(
            request_facts(
                intent="review",
                durable_design_artifacts=True,
                consequence="none",
                declaration_domains=0,
            )
        )

        self.assertEqual(decision.mode, "design-run")
        self.assertEqual(decision.tier, "P2")

    def test_run_requirements_are_derived_independently_of_tier(self) -> None:
        cases = (
            (
                request_facts(
                    intent="fix",
                    consequence="local",
                    existing_product=True,
                ),
                (True, False, False),
            ),
            (
                request_facts(
                    has_references=True,
                    adds_decided_fields=True,
                ),
                (False, True, False),
            ),
            (
                request_facts(
                    consequence="structural",
                    spec_present=False,
                ),
                (False, False, True),
            ),
            (
                request_facts(
                    intent="review",
                    durable_design_artifacts=True,
                    consequence="none",
                    existing_product=True,
                    declaration_domains=0,
                ),
                (True, False, False),
            ),
        )

        for facts, expected in cases:
            decision = route_request(facts)
            with self.subTest(tier=decision.tier):
                self.assertEqual(
                    (
                        decision.requires_baseline,
                        decision.requires_reference_contract,
                        decision.requires_spec,
                    ),
                    expected,
                )

    def test_contradictory_request_facts_fail_explicitly(self) -> None:
        cases = (
            request_facts(
                consequence="none",
                declaration_domains=0,
            ),
            request_facts(
                intent="review",
                consequence="structural",
                existing_product=True,
                baseline_ready=True,
            ),
        )

        for facts in cases:
            with self.subTest(facts=facts):
                with self.assertRaisesRegex(ValueError, "contradictory request facts"):
                    route_request(facts)

    def test_unknown_route_values_fail_explicitly(self) -> None:
        cases = (
            request_facts(intent="rewrite"),
            request_facts(consequence="global"),
        )

        for facts in cases:
            with self.subTest(facts=facts):
                with self.assertRaisesRegex(ValueError, "unknown"):
                    route_request(facts)

    def test_negative_declaration_domain_count_fails_explicitly(self) -> None:
        facts = request_facts(
            intent="review",
            consequence="none",
            declaration_domains=-1,
        )

        with self.assertRaisesRegex(ValueError, "declaration_domains"):
            route_request(facts)

    def test_route_cli_emits_the_shared_decision_as_json(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(PKG / "scripts" / "run_profile.py"),
                "route",
                "--intent",
                "fix",
                "--consequence",
                "local",
                "--existing-product",
                "--has-references",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        decision = json.loads(completed.stdout)
        self.assertEqual(decision["mode"], "design-run")
        self.assertEqual(decision["tier"], "P1")
        self.assertTrue(decision["requires_baseline"])
        self.assertTrue(decision["requires_reference_contract"])
        self.assertTrue(decision["requires_spec"])

    def test_route_cli_reports_contradictory_facts_without_a_traceback(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(PKG / "scripts" / "run_profile.py"),
                "route",
                "--intent",
                "build",
                "--consequence",
                "none",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("contradictory request facts", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertEqual(completed.stdout, "")


class AdaptiveRoutingSkillContractTests(unittest.TestCase):
    def test_main_skill_delegates_the_initial_decision_to_run_profile(self) -> None:
        text = MAIN_SKILL.read_text(encoding="utf-8")

        self.assertIn("Executable routing authority", text)
        self.assertIn("run_profile.py route", text)
        self.assertNotIn("SSOT for this decision is this skill only", text)
        self.assertNotIn("P3 wins for", text)
        self.assertNotIn("end with findings or a plan", text)
        self.assertNotIn("when reference materials present", text)
        for flag in (
            "requires_baseline",
            "requires_reference_contract",
            "requires_spec",
        ):
            with self.subTest(flag=flag):
                self.assertIn(f"`{flag}`", text)

    def test_no_run_image_handling_covers_both_host_capabilities(self) -> None:
        text = MAIN_SKILL.read_text(encoding="utf-8")

        self.assertIn("vision-capable host", text)
        self.assertIn("text-only host", text)
        self.assertIn("Neither path copies the temporary image", text)
        self.assertIn("Do not create `.scratch/<run>/`", text)

    def test_ui_picker_component_handoff_is_read_only_and_keeps_report_keys(self) -> None:
        text = UI_PICKER_SKILL.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        declared = normalized.index("`## Component Stylings`")
        discovered = normalized.index("`design-baseline/evidence.json`")

        self.assertLess(declared, discovered)
        for outcome in ("reuse <path>", "extend <path>", "new ("):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, text)
        self.assertIn("Do not edit, move, publish, extract, or commit", normalized)

        report = text.split("```text", maxsplit=1)[1].split("```", maxsplit=1)[0]
        keys = tuple(
            line.split(":", maxsplit=1)[0]
            for line in report.splitlines()
            if ":" in line
        )
        self.assertEqual(
            keys,
            (
                "design-baseline",
                "scene",
                "density",
                "template",
                "regions",
                "components",
                "baseline-changes",
                "risks",
            ),
        )

    def test_ui_picker_done_when_owns_reuse_extend_new(self) -> None:
        picker_done = _done_when(
            _heading_section(
                UI_PICKER_SKILL.read_text(encoding="utf-8"),
                "### 3. Components",
            )
        )
        orchestrator_done = _done_when(
            _heading_section(
                MAIN_SKILL.read_text(encoding="utf-8"),
                "### 5. Shell",
            )
        )

        for outcome in ("`reuse`", "`extend`", "`new`"):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, picker_done)
        self.assertIn("that skill is SSOT", orchestrator_done)
        self.assertNotIn("each material component role records", orchestrator_done)

    def test_entry_routing_has_done_when(self) -> None:
        section = _heading_section(
            MAIN_SKILL.read_text(encoding="utf-8"),
            "### 1. Entry routing",
        )

        self.assertIn("**Done when:**", section)
        self.assertIn("run_profile.py route", section)

    def test_codex_agents_intake_pointer_follows_router_flag(self) -> None:
        text = CODEX_AGENTS.read_text(encoding="utf-8")

        self.assertIn("requires_reference_contract", text)
        self.assertIn("requires_baseline", text)
        self.assertNotIn("when reference materials are present", text)
        baseline_at = text.index("requires_baseline")
        intake_at = text.index("requires_reference_contract")
        self.assertLess(baseline_at, intake_at)

    def test_first_run_guide_skips_follow_router_flags(self) -> None:
        text = FIRST_RUN.read_text(encoding="utf-8")

        self.assertIn("`requires_baseline`", text)
        self.assertIn("`requires_reference_contract`", text)
        self.assertNotIn("unless materials were provided", text)

    def test_reference_intake_heading_follows_router_flag(self) -> None:
        heading = _heading_section(
            MAIN_SKILL.read_text(encoding="utf-8"),
            "### 2. `reference-intake`",
        ).splitlines()[0]

        self.assertIn("`requires_reference_contract`", heading)

    def test_ui_picker_example_records_harvested_paths_in_components_value(self) -> None:
        report = UI_PICKER_SKILL.read_text(encoding="utf-8").split(
            "```text", maxsplit=1
        )[1].split("```", maxsplit=1)[0]

        self.assertIn("reuse src/ui/Button.tsx", report)
        self.assertIn("extend src/ui/Badge.tsx", report)
        self.assertIn("empty-state -> new", report)

    def test_ui_picker_harvests_evidence_without_verified_baseline(self) -> None:
        text = UI_PICKER_SKILL.read_text(encoding="utf-8")
        section = _heading_section(text, "### 1. Density + scene")

        self.assertNotIn("while reading the baseline", section)
        self.assertIn("`design-baseline/evidence.json`", section)
        self.assertIn("waived", section)
        self.assertIn("draft", section)

    def test_design_baseline_skip_follows_router_no_run(self) -> None:
        text = BASELINE_SKILL.read_text(encoding="utf-8")
        section = _heading_section(text, "### 1. Classify the project")

        self.assertNotIn("Skip for answer-only", section)
        self.assertNotIn("true greenfield", section)
        self.assertIn("`requires_baseline`", section)
        self.assertIn("`no-run`", section)
        self.assertIn("did not set `requires_baseline`", section)

    def test_reference_intake_assigns_screenshot_vs_other_without_restating_helper(self) -> None:
        text = INTAKE_SKILL.read_text(encoding="utf-8")
        section = _heading_section(text, "### 1. Inventory sources")

        self.assertIn("`kind: screenshot`", section)
        self.assertIn("`kind: other`", section)
        self.assertIn("media_type", section)
        self.assertNotIn("byte-for-byte", section)
        self.assertNotIn("digest prefix", section)


if __name__ == "__main__":
    unittest.main()
