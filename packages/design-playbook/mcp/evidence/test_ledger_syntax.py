#!/usr/bin/env python3
"""Syntax-facts tests for the single Evidence ledger parser (ADR-0025).

The Evidence ledger is now parsed once in ``ledger_syntax.parse_ledger``; G2
and G6 project their existing policy from its result. These tests pin the
information-preserving facts the ADR requires: row order, field occurrence
order, duplicate values, raw observed text, and the derived leading artifact
token (with the currently accepted trailing punctuation). They also pin the
G6 ``ledger_observed`` projection so the migration off the old independent
parser stays behavior-compatible.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.ledger_syntax import (  # noqa: E402
    FieldOccurrence,
    LedgerRow,
    parse_ledger,
)
from design_playbook.scripts.g6_records import ledger_observed  # noqa: E402


def _row(text: str) -> LedgerRow:
    """Parse a single-block ledger and return its one row."""
    rows = parse_ledger(text).rows
    assert len(rows) == 1, f"expected one row, got {len(rows)}: {rows!r}"
    return rows[0]


class RowOrderTests(unittest.TestCase):
    def test_multiple_rows_preserve_input_order(self):
        text = (
            "criterion: L6.1\nobserved: evidence/a.png\nresult: pass\n\n"
            "criterion: L6.2\nobserved: evidence/b.png\nresult: pass\n\n"
            "criterion: L6.3\nobserved: evidence/c.png\nresult: pass\n"
        )
        rows = parse_ledger(text).rows
        self.assertEqual(
            [r.values("criterion")[0] for r in rows],
            ["L6.1", "L6.2", "L6.3"],
        )

    def test_blocks_without_evidence_fields_are_skipped(self):
        text = (
            "## Evidence ledger\n\n"
            "Some prose intro with no fields.\n\n"
            "criterion: L6.1\nobserved: evidence/a.png\nresult: pass\n"
        )
        rows = parse_ledger(text).rows
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].values("criterion")[0], "L6.1")


class FieldOccurrenceOrderTests(unittest.TestCase):
    def test_interleaved_fields_preserve_occurrence_order(self):
        # criterion, observed, criterion again, result - not in canonical order
        text = (
            "criterion: L6.1\n"
            "observed: evidence/a.png\n"
            "criterion: L6.1\n"
            "result: pass\n"
        )
        row = _row(text)
        self.assertEqual(
            [oc.name for oc in row.occurrences],
            ["criterion", "observed", "criterion", "result"],
        )

    def test_field_names_are_canonical_lowercase(self):
        text = "Criterion: L6.1\nObserved: evidence/a.png\nResult: Pass\n"
        row = _row(text)
        self.assertEqual(
            [oc.name for oc in row.occurrences],
            ["criterion", "observed", "result"],
        )


class DuplicateValuesTests(unittest.TestCase):
    def test_repeated_field_keeps_every_value_in_order(self):
        text = "criterion: L6.1\ncriterion: L6.2\nobserved: evidence/a.png\n"
        row = _row(text)
        self.assertEqual(row.values("criterion"), ("L6.1", "L6.2"))

    def test_repeated_observed_keeps_every_value(self):
        text = (
            "criterion: L6.1\n"
            "observed: evidence/a.png\n"
            "observed: evidence/b.png\n"
        )
        row = _row(text)
        self.assertEqual(row.values("observed"),
                         ("evidence/a.png", "evidence/b.png"))

    def test_missing_field_yields_empty_tuple(self):
        row = _row("criterion: L6.1\nobserved: evidence/a.png\n")
        self.assertEqual(row.values("required"), ())
        self.assertEqual(row.values("result"), ())


class RawObservedTextTests(unittest.TestCase):
    def test_raw_observed_keeps_trailing_commentary(self):
        text = "criterion: L6.1\nobserved: evidence/a.png viewer state shot\n"
        row = _row(text)
        self.assertEqual(row.raw_observed, "evidence/a.png viewer state shot")

    def test_raw_observed_is_first_occurrence_when_duplicated(self):
        text = (
            "criterion: L6.1\n"
            "observed: evidence/first.png\n"
            "observed: evidence/second.png\n"
        )
        row = _row(text)
        self.assertEqual(row.raw_observed, "evidence/first.png")

    def test_no_observed_yields_empty_raw(self):
        row = _row("criterion: L6.1\nresult: pass\n")
        self.assertEqual(row.raw_observed, "")

    def test_empty_observed_value_yields_empty_raw(self):
        row = _row("criterion: L6.1\nobserved:\nresult: pass\n")
        self.assertEqual(row.raw_observed, "")


class ArtifactTokenTests(unittest.TestCase):
    def test_token_equals_raw_when_no_separator(self):
        row = _row("criterion: L6.1\nobserved: evidence/a.png\n")
        self.assertEqual(row.artifact_token, "evidence/a.png")

    def test_token_stops_at_whitespace(self):
        row = _row("criterion: L6.1\nobserved: evidence/a.png viewer shot\n")
        self.assertEqual(row.artifact_token, "evidence/a.png")

    def test_token_stops_at_half_width_paren(self):
        row = _row("criterion: L6.1\nobserved: evidence/a.png (shot)\n")
        self.assertEqual(row.artifact_token, "evidence/a.png")

    def test_token_stops_at_full_width_paren(self):
        row = _row("criterion: L6.1\nobserved: evidence/a.png（截图）\n")
        self.assertEqual(row.artifact_token, "evidence/a.png")

    def test_token_stops_at_half_width_comma(self):
        row = _row("criterion: L6.1\nobserved: evidence/a.png, shot\n")
        self.assertEqual(row.artifact_token, "evidence/a.png")

    def test_token_stops_at_full_width_comma(self):
        row = _row("criterion: L6.1\nobserved: evidence/a.png，截图\n")
        self.assertEqual(row.artifact_token, "evidence/a.png")

    def test_token_stops_at_half_width_colon(self):
        row = _row("criterion: L6.1\nobserved: evidence/a.png: shot\n")
        self.assertEqual(row.artifact_token, "evidence/a.png")

    def test_token_stops_at_full_width_colon(self):
        row = _row("criterion: L6.1\nobserved: evidence/a.png：截图\n")
        self.assertEqual(row.artifact_token, "evidence/a.png")

    def test_token_empty_when_no_observed(self):
        row = _row("criterion: L6.1\nresult: pass\n")
        self.assertEqual(row.artifact_token, "")

    def test_token_empty_when_observed_empty(self):
        row = _row("criterion: L6.1\nobserved:\nresult: pass\n")
        self.assertEqual(row.artifact_token, "")

    def test_observed_starting_with_separator_keeps_raw_as_token(self):
        # Matches the historical G6 derivation: when the raw value starts with
        # a tolerated separator, the leading-token match fails and the whole
        # raw value is the token (which then fails the evidence/ prefix check
        # at the consumer, so it is treated as free text).
        row = _row("criterion: L6.1\nobserved: (free text comment)\n")
        self.assertEqual(row.artifact_token, "(free text comment)")


class LedgerFactsShapeTests(unittest.TestCase):
    def test_empty_text_yields_no_rows(self):
        self.assertEqual(parse_ledger("").rows, ())

    def test_result_is_immutable_tuple(self):
        rows = parse_ledger("criterion: L6.1\nobserved: evidence/a.png\n").rows
        self.assertIsInstance(rows, tuple)
        self.assertIsInstance(rows[0].occurrences, tuple)

    def test_field_occurrence_is_frozen(self):
        oc = FieldOccurrence("criterion", "L6.1")
        with self.assertRaises(Exception):
            oc.name = "result"  # type: ignore[misc]


class G6ProjectionTests(unittest.TestCase):
    """``ledger_observed`` is the G6 projection over the new module.

    Pins the (criterion, artifact_token) pairs G6 consumes so the migration
    off the independent parser stays behavior-compatible, including the
    tolerated trailing punctuation from the commentary fixture.
    """

    def test_pairs_preserve_row_order_and_tokens(self):
        text = (
            "criterion: L6.1\nobserved: evidence/a.png\nresult: pass\n\n"
            "criterion: L6.2\nobserved: evidence/b.png, shot\nresult: pass\n"
        )
        self.assertEqual(
            ledger_observed(text),
            [("L6.1", "evidence/a.png"), ("L6.2", "evidence/b.png")],
        )

    def test_commentary_separators_strip_to_token(self):
        text = (
            "criterion: L6.3\n"
            "observed: evidence/L6.3-error.png（截图：错误态）\n"
            "result: pass\n\n"
            "criterion: L6.4\n"
            "observed: evidence/L6.4-viewer.png: viewer state screenshot\n"
            "result: pass\n\n"
            "criterion: L6.5\n"
            "observed: evidence/L6.5-retry.png, retry state screenshot\n"
            "result: pass\n"
        )
        self.assertEqual(
            ledger_observed(text),
            [
                ("L6.3", "evidence/L6.3-error.png"),
                ("L6.4", "evidence/L6.4-viewer.png"),
                ("L6.5", "evidence/L6.5-retry.png"),
            ],
        )

    def test_row_without_observed_is_skipped(self):
        text = "criterion: L6.1\nresult: pass\n"
        self.assertEqual(ledger_observed(text), [])

    def test_row_with_empty_observed_is_skipped(self):
        text = "criterion: L6.1\nobserved:\nresult: pass\n"
        self.assertEqual(ledger_observed(text), [])

    def test_row_without_criterion_is_skipped(self):
        text = "observed: evidence/a.png\nresult: pass\n"
        self.assertEqual(ledger_observed(text), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
