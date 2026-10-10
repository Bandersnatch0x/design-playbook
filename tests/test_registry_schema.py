"""Registry schema checks run in-process on the shipped registry text.

Each case mutates one entry of the shipped ``rules.md`` and asserts the G8
product-level check names that entry, so a check that silently stops firing
fails here before it fails a release.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG / "scripts") not in sys.path:
    sys.path.insert(0, str(PKG / "scripts"))

import rules_registry  # noqa: E402  (standalone seam, same as validate.py)

REGISTRY_TEXT = (PKG / "skills" / "design-playbook" / "references"
                 / "rules.md").read_text(encoding="utf-8")


def _errors(text: str) -> list[str]:
    return rules_registry.validate_registry(rules_registry.parse_registry(text))


def _mutate(entry_id: str, key: str, value: str | None) -> str:
    """Rewrite (or with ``None`` delete) one field line of one entry."""
    start = REGISTRY_TEXT.index(f"\nid: {entry_id}\n")
    end = REGISTRY_TEXT.index("```", start)
    block = REGISTRY_TEXT[start:end]
    pattern = re.compile(rf"^{re.escape(key)}:.*\n", re.M)
    assert pattern.search(block), (entry_id, key)
    replacement = "" if value is None else f"{key}: {value}\n"
    return REGISTRY_TEXT[:start] + pattern.sub(replacement, block, count=1) + REGISTRY_TEXT[end:]


class ProtocolFaceTests(unittest.TestCase):
    def test_shipped_registry_is_clean(self) -> None:
        self.assertEqual(_errors(REGISTRY_TEXT), [])

    def test_missing_fix_fails(self) -> None:
        errors = _errors(_mutate("CRAFT-01", "fix", None))
        self.assertIn("CRAFT-01: missing required field fix", errors)

    def test_each_protocol_field_is_required(self) -> None:
        for key in ("statement", "exceptions", "false-positives", "evidence-method"):
            with self.subTest(key=key):
                errors = _errors(_mutate("A11Y-01", key, None))
                self.assertIn(f"A11Y-01: missing required field {key}", errors)

    def test_unknown_evidence_method_fails(self) -> None:
        errors = _errors(_mutate("CRAFT-01", "evidence-method", "vibes"))
        self.assertTrue(any(e.startswith("CRAFT-01: evidence-method 'vibes'") for e in errors), errors)

    def test_usability_heuristic_is_an_authority(self) -> None:
        self.assertIn("usability-heuristic", rules_registry.AUTHORITIES)



class AuthoritySeverityTests(unittest.TestCase):
    def test_hard_constraint_with_judgment_fails(self) -> None:
        errors = _errors(_mutate("A11Y-01", "severity-default", "S1 / judgment"))
        self.assertTrue(any(e.startswith("A11Y-01: authority hard-constraint") for e in errors), errors)

    def test_advisory_aesthetic_at_s3_fails(self) -> None:
        errors = _errors(_mutate("CRAFT-01", "severity-default", "S3 / judgment"))
        self.assertTrue(any(e.startswith("CRAFT-01: authority advisory-aesthetic") for e in errors), errors)

    def test_measured_threshold_needs_fact_class(self) -> None:
        errors = _errors(_mutate("A11Y-03", "severity-default", "S2 / judgment"))
        self.assertTrue(any(e.startswith("A11Y-03: authority measured-threshold") for e in errors), errors)


class ThresholdTests(unittest.TestCase):
    def test_measured_threshold_without_threshold_fails(self) -> None:
        errors = _errors(_mutate("PERF-01", "threshold", None))
        self.assertIn("PERF-01: measured-threshold entry has no threshold field", errors)

    def test_prose_threshold_fails(self) -> None:
        errors = _errors(_mutate("A11Y-03", "threshold", "text-contrast >= high"))
        self.assertTrue(any(e.startswith("A11Y-03: threshold unparseable clause") for e in errors), errors)

    def test_duplicate_term_fails(self) -> None:
        errors = _errors(_mutate("A11Y-04", "threshold", "hit-area-floor >= 24px; hit-area-floor >= 20px"))
        self.assertIn("A11Y-04: threshold duplicate term 'hit-area-floor'", errors)

    def test_threshold_reader_returns_the_registry_value(self) -> None:
        entries = rules_registry.parse_registry(REGISTRY_TEXT)
        floor = rules_registry.threshold(entries, "A11Y-04", "hit-area-floor")
        self.assertEqual((floor.op, floor.value, floor.unit), (">=", 24.0, "px"))
        with self.assertRaises(KeyError):
            rules_registry.threshold(entries, "A11Y-04", "missing-term")


if __name__ == "__main__":
    unittest.main()
