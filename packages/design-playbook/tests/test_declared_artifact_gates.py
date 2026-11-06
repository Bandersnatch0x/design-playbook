#!/usr/bin/env python3
"""T-153: the two declared-but-unread artifacts now have machine faces.

``reference/contract.md`` is checked by G13 (declared axes) and the decision
report's verbatim top block by G10. Every rule set gets a positive (compliant
artifact -> zero findings), a negative (artifact present but incomplete ->
the new code), and the absence case: an artifact that does not exist is a
legal run and must never produce the same red as an incomplete one.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "scripts"
EXAMPLES = PACKAGE / "examples"
PASS = Path(__file__).resolve().parent / "fixtures" / "pass"
VALIDATOR = SCRIPTS / "validate_run.py"

if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.g10_design_decisions import check_g10  # noqa: E402
from design_playbook.scripts.g13_reference_contract import check_g13  # noqa: E402

_COMPLIANT_REPORT = """# Decision report

```text
scene: ops console data export
density: console-tight
template: toolbar + table + global status region
regions: toolbar -> batch actions; table -> last-week data; status -> task feed
components: batch export -> Button (primary); task entry -> status item
baseline-changes: none
risks: none
```
"""

_CONTRACT = EXAMPLES / "reference-intake" / "screenshot" / "contract.md"


def _codes(findings: list) -> list[str]:
    return [item.rule_id for item in findings]


def _run(spec: Path, pointback: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(spec), str(pointback), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _run_codes(
    spec: Path, pointback: Path, *extra: str
) -> tuple[int, set[str]]:
    """Rule ids from the JSON projection (the text face omits codes)."""
    result = _run(spec, pointback, "--format", "json", *extra)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.returncode, set()
    return result.returncode, {
        item.get("rule_id") for item in payload if isinstance(item, dict)
    }


class TopBlockGateTests(unittest.TestCase):
    """G10 reads the top block whenever a decision report exists."""

    def test_compliant_top_block_has_no_finding(self) -> None:
        self.assertEqual(check_g10(_COMPLIANT_REPORT), [])

    def test_heading_declared_axes_are_accepted(self) -> None:
        # Older reports declare the list-shaped axes as headings instead of
        # "key: value" lines; the axis is declared either way.
        report = (
            "# Decision Report\n\n"
            "Scene: multi-step form wizard\n"
            "Density: console-tight\n"
            "Template: single-card wizard\n\n"
            "## Regions\n- main\n\n## Components\n- StepIndicator\n"
        )
        self.assertEqual(check_g10(report), [])

    def test_missing_axes_are_reported(self) -> None:
        findings = check_g10("# decision report\n")
        self.assertEqual(_codes(findings), ["G10.top_block"])
        for axis in ("scene", "density", "template", "regions", "components"):
            self.assertIn(axis, findings[0].message)

    def test_single_missing_axis_is_named(self) -> None:
        report = _COMPLIANT_REPORT.replace(
            "regions: toolbar -> batch actions; table -> last-week data; "
            "status -> task feed",
            "layout: toolbar -> batch actions",
        )
        findings = check_g10(report)
        self.assertEqual(_codes(findings), ["G10.top_block"])
        self.assertIn("regions", findings[0].message)
        self.assertNotIn("components", findings[0].actual)

    def test_declared_but_empty_scalar_is_reported(self) -> None:
        report = _COMPLIANT_REPORT.replace(
            "density: console-tight", "density:"
        )
        findings = check_g10(report)
        self.assertEqual(_codes(findings), ["G10.top_block"])
        self.assertIn("no value", findings[0].message)
        self.assertIn("density", findings[0].actual)

    def test_blank_report_reports_every_axis(self) -> None:
        # The caller decides presence; a handed-in empty text is a report
        # that declares nothing.
        findings = check_g10("")
        self.assertEqual(_codes(findings), ["G10.top_block"])
        self.assertIn("components", findings[0].actual)

    def test_fence_inside_a_dd_entry_is_not_the_top_block(self) -> None:
        report = (
            "# Decision report\n\n"
            "## DD-0001 — question\n\n"
            "```text\n"
            "scene: x\ndensity: y\ntemplate: z\n"
            "regions: r\ncomponents: c\n"
            "```\n"
        )
        self.assertIn("G10.top_block", _codes(check_g10(report)))


class ReferenceContractGateTests(unittest.TestCase):
    """G13 reads the contract's declared axes when the artifact exists."""

    def test_shipped_example_contract_has_no_finding(self) -> None:
        self.assertTrue(_CONTRACT.is_file(), _CONTRACT)
        self.assertEqual(
            check_g13(_CONTRACT.read_text(encoding="utf-8")), []
        )

    def test_missing_heading_is_reported(self) -> None:
        text = _CONTRACT.read_text(encoding="utf-8").replace(
            "## Keep", "## Keepsakes"
        )
        findings = check_g13(text)
        self.assertEqual(_codes(findings), ["G13.contract_axes"])
        self.assertIn("Keep", findings[0].actual)
        self.assertNotIn("Unresolved questions", findings[0].actual)

    def test_missing_constraint_marker_is_reported(self) -> None:
        text = _CONTRACT.read_text(encoding="utf-8").replace(
            "always / ask / never hints:", "boundaries:"
        )
        findings = check_g13(text)
        self.assertEqual(_codes(findings), ["G13.contract_axes"])
        self.assertIn("always / ask / never hints:", findings[0].actual)

    def test_blank_contract_reports_every_axis(self) -> None:
        findings = check_g13("")
        self.assertEqual(_codes(findings), ["G13.contract_axes"])
        self.assertIn("Source summary", findings[0].actual)


class ValidateRunWiringTests(unittest.TestCase):
    """The two gates reach a real validate_run sweep through the run root."""

    def _run_root(self, tmp: str) -> Path:
        root = Path(tmp)
        (root / "spec.md").write_bytes(
            (PASS / "zero-findings.spec.md").read_bytes()
        )
        (root / "point-back.md").write_bytes(
            (PASS / "zero-findings.point-back.md").read_bytes()
        )
        return root

    def test_run_without_either_artifact_stays_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._run_root(tmp)
            code, rules = _run_codes(
                root / "spec.md", root / "point-back.md",
                "--run-root", str(root), "--legacy",
            )
            self.assertEqual(code, 0, rules)
            self.assertFalse(
                {"G10.top_block", "G13.contract_axes"} & rules
            )

    def test_present_top_less_report_turns_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._run_root(tmp)
            (root / "decision-report.md").write_text(
                "# decision report\n", encoding="utf-8"
            )
            code, rules = _run_codes(
                root / "spec.md", root / "point-back.md",
                "--run-root", str(root), "--legacy",
            )
            self.assertEqual(code, 1, rules)
            self.assertIn("G10.top_block", rules)

    def test_present_incomplete_contract_turns_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._run_root(tmp)
            reference = root / "reference"
            reference.mkdir()
            (reference / "contract.md").write_text(
                "# Reference contract\n\n## Keep\n- hero\n", encoding="utf-8"
            )
            code, rules = _run_codes(
                root / "spec.md", root / "point-back.md",
                "--run-root", str(root), "--legacy",
            )
            self.assertEqual(code, 1, rules)
            self.assertIn("G13.contract_axes", rules)

    def test_blank_artifacts_turn_red(self) -> None:
        # Present-but-empty is the non-compliant side of the line, never the
        # absent side: both files exist and declare nothing.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._run_root(tmp)
            (root / "decision-report.md").write_text("", encoding="utf-8")
            reference = root / "reference"
            reference.mkdir()
            (reference / "contract.md").write_text("", encoding="utf-8")
            code, rules = _run_codes(
                root / "spec.md", root / "point-back.md",
                "--run-root", str(root), "--legacy",
            )
            self.assertEqual(code, 1, rules)
            self.assertIn("G10.top_block", rules)
            self.assertIn("G13.contract_axes", rules)

    def test_compliant_artifacts_stay_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._run_root(tmp)
            (root / "decision-report.md").write_text(
                _COMPLIANT_REPORT, encoding="utf-8"
            )
            reference = root / "reference"
            reference.mkdir()
            (reference / "contract.md").write_bytes(_CONTRACT.read_bytes())
            code, rules = _run_codes(
                root / "spec.md", root / "point-back.md",
                "--run-root", str(root), "--legacy",
            )
            self.assertEqual(code, 0, rules)

    def test_unreadable_contract_is_a_finding_not_an_io_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._run_root(tmp)
            reference = root / "reference"
            reference.mkdir()
            (reference / "contract.md").write_bytes(b"\xff\xfe\x00bad")
            code, rules = _run_codes(
                root / "spec.md", root / "point-back.md",
                "--run-root", str(root), "--legacy",
            )
            self.assertEqual(code, 1, rules)
            self.assertIn("G13.contract_unreadable", rules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
