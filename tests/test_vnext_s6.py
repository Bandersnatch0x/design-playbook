#!/usr/bin/env python3
"""vNext S6 unit tests: P3 full-profile obligations + dogfood fixture.

Issue #41 exit criteria:
- P3 tier-matrix positives and negatives (a P3 run without the sampling
  matrix block fails G11; a complete P3 run walks the whole chain),
- the S6 dogfood fixture (this repo's own showcase queue surface) passes
  validate_run --strict end to end,
- the cross-document link self-check script stays green (CI wiring).

Black-box through validate_run.py where possible (same wiring as the
S1-S5 suites); in-process for the pure gate functions.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts.g11_coverage import check_sampling_matrix  # noqa: E402

P3_BASE = PKG / "examples" / "export-upgrade"
P3_RUN = P3_BASE / "run"
DOG_BASE = PKG / "examples" / "dogfood"
DOG_RUN = DOG_BASE / "run"
P2_POINTBACK = (PKG / "examples" / "export-entry" / "run" / "point-back.md"
                ).read_text(encoding="utf-8")
P2_SPEC = (PKG / "examples" / "export-entry" / "run" / "spec.md"
           ).read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _validate(run: Path, project: Path, *extra: str) -> subprocess.CompletedProcess[str]:  # noqa: E501
    return subprocess.run(
        [
            sys.executable,
            str(PKG / "scripts" / "validate_run.py"),
            str(run / "spec.md"),
            str(run / "point-back.md"),
            "--preview-dir", str(run / "preview"),
            "--decision-report", str(run / "decision-report.md"),
            "--evidence-dir", str(run / "evidence"),
            "--run-root", str(run),
            "--contract-project", str(project),
            "--contract-run", str(run),
            "--shaping-dir", str(run / "shaping"),
            *extra,
        ],
        capture_output=True, text=True, check=False,
    )


def _copy_fixture(base: Path, tmp: Path) -> tuple[Path, Path]:
    """Copy <base>/project + <base>/run into tmp; return (run, project)."""
    run = Path(tmp) / "run"
    project = Path(tmp) / "project"
    shutil.copytree(base / "run", run)
    shutil.copytree(base / "project", project)
    return run, project


def _rules(findings: list) -> set[str]:
    return {finding.rule_id for finding in findings}


MATRIX_MARKER_LINE = "采样矩阵:"


def _strip_matrix(text: str) -> str:
    """Remove the sampling-matrix block (marker line + its list lines)."""
    lines = text.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == MATRIX_MARKER_LINE:
            skipping = True
            continue
        if skipping:
            stripped = line.strip()
            if stripped.startswith("- "):
                continue
            skipping = False
        out.append(line)
    return "\n".join(out)


class P3MatrixObligationTests(unittest.TestCase):
    """S6 machine face: the effective tier P3 makes the matrix block
    mandatory (loop-prototype 1.2 'sampling matrix fully executed')."""

    def test_p3_without_matrix_fails(self) -> None:
        findings = check_sampling_matrix(
            P2_POINTBACK.replace(MATRIX_MARKER_LINE + "\n", "")
            if MATRIX_MARKER_LINE in P2_POINTBACK else P2_POINTBACK,
            P2_SPEC, tier="P3")
        self.assertIn("G11.matrix_required", _rules(findings))

    def test_p3_with_matrix_passes(self) -> None:
        self.assertEqual(
            check_sampling_matrix(P2_POINTBACK, P2_SPEC, tier="P3"), [])

    def test_matrix_less_reports_stay_legal_below_p3(self) -> None:
        stripped = _strip_matrix(P2_POINTBACK)
        self.assertEqual(check_sampling_matrix(stripped, P2_SPEC), [])
        self.assertEqual(
            check_sampling_matrix(stripped, P2_SPEC, tier="P2"), [])
        self.assertEqual(
            check_sampling_matrix(stripped, P2_SPEC, tier="P1"), [])

    def test_p3_without_coverage_statement_reports_the_gap(self) -> None:
        findings = check_sampling_matrix("# bare report\n", P2_SPEC, tier="P3")
        self.assertIn("G11.matrix_required", _rules(findings))
        self.assertIn("no Coverage statement",
                      findings[0].actual if findings else "")


class P3ChainWalkthroughTests(unittest.TestCase):
    """The P3 fixtures walk the full chain; obligations bind on the
    declared (and effective) tier only."""

    def test_export_upgrade_full_p3_chain_strict(self) -> None:
        result = _validate(P3_RUN, P3_BASE / "project", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)

    def test_export_upgrade_missing_matrix_breaks_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run, project = _copy_fixture(P3_BASE, tmp)
            _write(run / "point-back.md", _strip_matrix(
                (run / "point-back.md").read_text(encoding="utf-8")))
            result = _validate(run, project)
            self.assertEqual(result.returncode, 1)
            self.assertIn("G11 coverage: P3 (full profile)", result.stdout)
            self.assertIn("sampling matrix", result.stdout)

    def test_effective_tier_after_recorded_upgrade_demands_matrix(self) -> None:
        # Declared P2 with a recorded E3 upgrade -> P3: the run walks the
        # new tier's obligations (escalate-and-rewalk), matrix included.
        with tempfile.TemporaryDirectory() as tmp:
            run, project = _copy_fixture(P3_BASE, tmp)
            plan = (run / "plan.md").read_text(encoding="utf-8")
            plan = plan.replace(
                "tier: P3",
                "tier: P2"
            ).replace(
                "upgrades: []",
                "upgrades:\n  - 2026-08-14T11:00:00Z E3 (R3 challenge -> "
                "explore re-entry) -> P3"
            )
            _write(run / "plan.md", plan)
            _write(run / "point-back.md", _strip_matrix(
                (run / "point-back.md").read_text(encoding="utf-8")))
            result = _validate(run, project)
            self.assertEqual(result.returncode, 1)
            self.assertIn("G11 coverage: P3 (full profile)", result.stdout)

    def test_legacy_run_without_profile_is_not_rechecked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run, project = _copy_fixture(P3_BASE, tmp)
            (run / "plan.md").unlink()
            _write(run / "point-back.md", _strip_matrix(
                (run / "point-back.md").read_text(encoding="utf-8")))
            result = _validate(run, project)
            self.assertEqual(result.returncode, 0, result.stdout)


class DogfoodFixtureTests(unittest.TestCase):
    """Issue #41: the dogfood run over this repo's own showcase queue
    surface passes the full P3 chain (static synthesized artifacts)."""

    def test_dogfood_full_p3_chain_strict(self) -> None:
        result = _validate(DOG_RUN, DOG_BASE / "project", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)

    def test_dogfood_missing_matrix_breaks_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run, project = _copy_fixture(DOG_BASE, tmp)
            _write(run / "point-back.md", _strip_matrix(
                (run / "point-back.md").read_text(encoding="utf-8")))
            result = _validate(run, project)
            self.assertEqual(result.returncode, 1)
            self.assertIn("G11 coverage: P3 (full profile)", result.stdout)

    def test_dogfood_g8_full_evaluation_enforced(self) -> None:
        # P3 demands one audit row per reviewable advisory entry: drop one
        # row and the run-level registry gate fires (no silent predicate
        # skip on the full profile).
        with tempfile.TemporaryDirectory() as tmp:
            run, project = _copy_fixture(DOG_BASE, tmp)
            craft = (run / "craft-guard.md").read_text(encoding="utf-8")
            lines = [line for line in craft.splitlines()
                     if not line.startswith("| PERF-01@1 ")]
            _write(run / "craft-guard.md", "\n".join(lines) + "\n")
            result = _validate(run, project)
            self.assertEqual(result.returncode, 1)
            self.assertIn("G8 run: P3 demands full predicate evaluation",
                          result.stdout)
            self.assertIn("PERF-01", result.stdout)

    def test_dogfood_run_status_narration(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PKG / "scripts" / "run_status.py"),
             str(DOG_RUN)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for needle in ("tier P3", "E3", "R3 x1, R4 x1", "verdict: Pass"):
            self.assertIn(needle, result.stdout)


class DocLinkSelfCheckTests(unittest.TestCase):
    """The S6 cross-document link checker runs green and is wired in CI."""

    def test_no_broken_relative_links(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_doc_links.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DOC LINKS OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
