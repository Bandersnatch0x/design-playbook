#!/usr/bin/env python3
"""Syntax-facts tests for the single Verdict parser (ADR-0025).

The Verdict section is now parsed once in ``verdict_syntax.parse_verdict``;
G3 (g2_g4_pointback) and run status (run_status) project their existing
policy from its result. These tests pin the heading and value cardinality
facts the ADR requires and the rule that a canonical value is exposed only
when exactly one valid Verdict exists - which is what stops run status from
reporting ``Run complete (Pass)`` on missing, malformed, ambiguous, or
repeated Verdict text.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. Mirrors test_ledger_syntax.py at one
# level shallower (scripts/ vs mcp/evidence/).
_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.scripts.verdict_syntax import (  # noqa: E402
    VerdictFacts,
    parse_verdict,
)


def _facts(text: str) -> VerdictFacts:
    return parse_verdict(text)


class HeadingCardinalityTests(unittest.TestCase):
    def test_no_verdict_heading_yields_zero(self):
        facts = _facts("## Findings\n\nissue: x\nsource: y\nfix: z\nseverity: low\n")
        self.assertEqual(facts.heading_count, 0)
        self.assertIsNone(facts.canonical)

    def test_one_verdict_heading_yields_one(self):
        facts = _facts("## Verdict\n\nPass\n")
        self.assertEqual(facts.heading_count, 1)

    def test_repeated_verdict_headings_count_all(self):
        facts = _facts("## Verdict\n\nPass\n\n## Verdict\n\nPass\n")
        self.assertEqual(facts.heading_count, 2)
        self.assertIsNone(facts.canonical)

    def test_heading_levels_one_through_four_all_match(self):
        for marker in ("#", "##", "###", "####"):
            facts = _facts(f"{marker} Verdict\n\nPass\n")
            self.assertEqual(facts.heading_count, 1, marker)

    def test_heading_with_trailing_text_does_not_match(self):
        # `## Verdict notes` is NOT a Verdict section: the heading regex
        # requires the line to be exactly `#+ Verdict` (then end-of-line).
        # The old permissive run_status parser matched `startswith("## verdict")`
        # and would treat this as a verdict heading; the shared parser must not.
        facts = _facts("## Verdict notes\n\nPass\n")
        self.assertEqual(facts.heading_count, 0)
        self.assertIsNone(facts.canonical)

    def test_heading_match_is_case_insensitive(self):
        facts = _facts("## verdict\n\nPass\n")
        self.assertEqual(facts.heading_count, 1)

    def test_heading_allows_whitespace_padding(self):
        facts = _facts("##   Verdict   \n\nPass\n")
        self.assertEqual(facts.heading_count, 1)


class ValueCardinalityTests(unittest.TestCase):
    def test_one_pass_yields_one_value(self):
        facts = _facts("## Verdict\n\nPass\n")
        self.assertEqual(facts.value_count, 1)
        self.assertEqual(facts.values, ("pass",))

    def test_one_recirculate_yields_one_value(self):
        facts = _facts("## Verdict\n\nRecirculate\n")
        self.assertEqual(facts.value_count, 1)
        self.assertEqual(facts.values, ("recirculate",))

    def test_empty_verdict_section_yields_zero_values(self):
        facts = _facts("## Verdict\n\n## Evidence ledger\n")
        self.assertEqual(facts.value_count, 0)
        self.assertIsNone(facts.canonical)

    def test_two_pass_values_yield_two(self):
        facts = _facts("## Verdict\n\nPass\n\nPass\n")
        self.assertEqual(facts.value_count, 2)
        self.assertIsNone(facts.canonical)

    def test_pass_and_recirculate_yield_two(self):
        facts = _facts("## Verdict\n\nPass\nRecirculate\n")
        self.assertEqual(facts.value_count, 2)
        self.assertIsNone(facts.canonical)

    def test_values_outside_verdict_section_are_ignored(self):
        # A Pass appearing in a later section is NOT in the Verdict body.
        # The old run_status regex fallback searched the whole document tail
        # for `\bPass\b`; the shared parser bounds the body at the next heading.
        facts = _facts("## Verdict\n\n## Evidence ledger\n\nPass\n")
        self.assertEqual(facts.value_count, 0)
        self.assertIsNone(facts.canonical)

    def test_pass_inside_prose_is_not_counted(self):
        # "Pass" must be at the start of a line (after optional marker/bold),
        # not buried mid-prose. `\bPass\b` anywhere in the body is not enough.
        facts = _facts("## Verdict\n\nThe run did not Pass.\n")
        self.assertEqual(facts.value_count, 0)
        self.assertIsNone(facts.canonical)


class AcceptedValueFormsTests(unittest.TestCase):
    """Pin the punctuation G3 historically accepts so the migration off the
    independent parser stays behavior-compatible."""

    def test_bold_pass_with_period(self):
        facts = _facts("## Verdict\n\n**Pass.** Zero findings.\n")
        self.assertEqual(facts.values, ("pass",))
        self.assertEqual(facts.canonical, "pass")

    def test_bold_recirculate_with_period(self):
        facts = _facts(
            "## Verdict\n\n**Recirculate.** A Pass is not earned yet.\n")
        self.assertEqual(facts.values, ("recirculate",))
        self.assertEqual(facts.canonical, "recirculate")

    def test_bold_pass_without_period(self):
        facts = _facts("## Verdict\n\n**Pass**\n")
        self.assertEqual(facts.canonical, "pass")

    def test_plain_pass(self):
        facts = _facts("## Verdict\n\nPass\n")
        self.assertEqual(facts.canonical, "pass")

    def test_dash_list_marker_pass(self):
        facts = _facts("## Verdict\n\n- Pass\n")
        self.assertEqual(facts.canonical, "pass")

    def test_star_list_marker_pass(self):
        facts = _facts("## Verdict\n\n* Pass\n")
        self.assertEqual(facts.canonical, "pass")

    def test_dash_list_marker_bold_pass(self):
        facts = _facts("## Verdict\n\n- **Pass.**\n")
        self.assertEqual(facts.canonical, "pass")

    def test_value_match_is_case_insensitive(self):
        for form in ("pass", "PASS", "Pass"):
            facts = _facts(f"## Verdict\n\n{form}\n")
            self.assertEqual(facts.canonical, "pass", form)

    def test_passed_does_not_match(self):
        # `\b` after Pass prevents matching "Passed".
        facts = _facts("## Verdict\n\nPassed\n")
        self.assertEqual(facts.value_count, 0)
        self.assertIsNone(facts.canonical)

    def test_recirculated_does_not_match(self):
        facts = _facts("## Verdict\n\nRecirculated\n")
        self.assertEqual(facts.value_count, 0)
        self.assertIsNone(facts.canonical)


class CanonicalExposureTests(unittest.TestCase):
    def test_canonical_pass_when_one_heading_one_value(self):
        facts = _facts("## Verdict\n\n**Pass.**\n")
        self.assertEqual(facts.canonical, "pass")

    def test_canonical_recirculate_when_one_heading_one_value(self):
        facts = _facts("## Verdict\n\n**Recirculate.**\n")
        self.assertEqual(facts.canonical, "recirculate")

    def test_canonical_none_when_heading_missing(self):
        self.assertIsNone(_facts("## Findings\n\nPass\n").canonical)

    def test_canonical_none_when_heading_repeated(self):
        self.assertIsNone(
            _facts("## Verdict\n\nPass\n\n## Verdict\n\nPass\n").canonical)

    def test_canonical_none_when_value_count_zero(self):
        self.assertIsNone(_facts("## Verdict\n\n## Evidence\n").canonical)

    def test_canonical_none_when_value_count_two(self):
        self.assertIsNone(_facts("## Verdict\n\nPass\nRecirculate\n").canonical)

    def test_canonical_none_when_two_pass(self):
        self.assertIsNone(_facts("## Verdict\n\nPass\n\nPass\n").canonical)

    def test_canonical_is_casefolded(self):
        facts = _facts("## Verdict\n\nPASS\n")
        self.assertEqual(facts.canonical, "pass")


class FactsShapeTests(unittest.TestCase):
    def test_empty_text_yields_zero_facts(self):
        facts = _facts("")
        self.assertEqual(facts.heading_count, 0)
        self.assertEqual(facts.value_count, 0)
        self.assertEqual(facts.values, ())
        self.assertIsNone(facts.canonical)

    def test_values_is_immutable_tuple(self):
        facts = _facts("## Verdict\n\nPass\nRecirculate\n")
        self.assertIsInstance(facts.values, tuple)

    def test_facts_is_frozen(self):
        facts = _facts("## Verdict\n\nPass\n")
        with self.assertRaises(Exception):
            facts.canonical = "recirculate"  # type: ignore[misc]


class BodyBoundaryTests(unittest.TestCase):
    def test_body_ends_at_next_heading_regardless_of_level(self):
        # The Verdict body stops at the next `#+ ` heading. A Pass in the
        # following section is not counted.
        facts = _facts("## Verdict\n\n### Notes\n\nPass\n")
        self.assertEqual(facts.value_count, 0)
        self.assertIsNone(facts.canonical)

    def test_body_runs_to_end_when_no_following_heading(self):
        facts = _facts("## Verdict\n\n**Pass.** Zero findings.\n")
        self.assertEqual(facts.value_count, 1)
        self.assertEqual(facts.canonical, "pass")

    def test_recirculate_closure_trail_heading_is_not_a_verdict(self):
        # `## Recirculate closure trail` must not be mistaken for a Verdict
        # heading (the showcase point-back ships this section ordering).
        facts = _facts(
            "## Recirculate closure trail\n\n- closes: x -> 0 blocking\n\n"
            "## Verdict\n\n**Pass.**\n")
        self.assertEqual(facts.heading_count, 1)
        self.assertEqual(facts.canonical, "pass")


if __name__ == "__main__":
    unittest.main(verbosity=2)
