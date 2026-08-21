#!/usr/bin/env python3
"""Black-box tests for scripts/aggregate_runs.py (run aggregate, v0.9)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGGREGATE = ROOT / "scripts" / "aggregate_runs.py"
FIXTURE_PASS = ROOT / "packages" / "design-playbook" / "tests" / "fixtures" / "pass"

BLOCKED_OBSERVED = "Prototype has filter controls but no live filtering implemented"
BLOCKED_OBSERVED_VARIANT = "  prototype HAS filter controls but NO live filtering implemented  "
OTHER_BLOCKED = "empty class defined but no demo markup"


def run_aggregate(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(AGGREGATE), *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )


def make_run(run_dir: Path, *, blocked: list[str] | None = None,
             with_plan: bool = True) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE_PASS / "spec.md", run_dir / "spec.md")
    pb = (FIXTURE_PASS / "point-back.md").read_text(encoding="utf-8")
    if blocked:
        extra = []
        for i, text in enumerate(blocked, start=9):
            extra.append(
                f"criterion: L6.{i}\n"
                f"required: some requirement\n"
                f"observed: {text}\n"
                f"result: blocked\n"
            )
        pb = pb.rstrip() + "\n\n" + "\n\n".join(extra) + "\n"
    (run_dir / "point-back.md").write_text(pb, encoding="utf-8")
    if with_plan:
        (run_dir / "plan.md").write_text("# plan\n", encoding="utf-8")


def make_skeleton_run(run_dir: Path) -> None:
    """A run whose point-back is the unaudited skeleton (ADR-0033 D5)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE_PASS / "skeleton.spec.md", run_dir / "spec.md")
    shutil.copyfile(
        FIXTURE_PASS / "skeleton.point-back.md", run_dir / "point-back.md")


def build_scratch(root: Path) -> Path:
    scratch = root / ".scratch" / "aggregate-test-effort" / "dogfood"
    make_run(scratch / "2026-01-01-001-pass")                       # A: gate ok
    make_run(scratch / "2026-01-02-002-block", blocked=[BLOCKED_OBSERVED])   # B
    make_run(scratch / "2026-01-03-003-block", blocked=[BLOCKED_OBSERVED_VARIANT, OTHER_BLOCKED],
             with_plan=False)                                        # C: repeat + no plan
    return scratch


class AggregateRunsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        build_scratch(self.cwd)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _payload(self, *args: str) -> dict:
        proc = run_aggregate(*args, cwd=self.cwd)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_discovery_rollup_and_gate(self) -> None:
        payload = self._payload()
        self.assertEqual(payload["runs_total"], 3)
        by_id = {r["id"]: r for r in payload["runs"]}
        self.assertEqual(
            by_id["2026-01-01-001-pass"]["gate"],
            {"status": "ok", "detail": "RUN OK"},
        )
        self.assertEqual(
            by_id["2026-01-02-002-block"]["gate"],
            {
                "status": "fail",
                "detail": (
                    "FAIL  G3 evidence: Pass requires row 6 result pass, "
                    "got 'blocked'"
                ),
            },
        )
        self.assertEqual(by_id["2026-01-01-001-pass"]["date"], "2026-01-01")
        self.assertEqual(by_id["2026-01-01-001-pass"]["effort"], "aggregate-test-effort")
        self.assertFalse(by_id["2026-01-03-003-block"]["artifacts"]["plan"])
        self.assertTrue(by_id["2026-01-01-001-pass"]["artifacts"]["spec"])

    def test_validator_io_failure_keeps_historical_gate_projection(self) -> None:
        run_dir = self.cwd / "io-error-run"
        make_run(run_dir)
        (run_dir / "spec.md").write_bytes(b"\xff")

        payload = self._payload("--runs", str(run_dir))

        self.assertEqual(
            payload["runs"][0]["gate"],
            {"status": "fail", "detail": "violations"},
        )

    def test_repeat_blocker_detection(self) -> None:
        payload = self._payload()
        blockers = payload["repeat_blockers"]
        self.assertTrue(blockers)
        top = max(blockers, key=lambda b: b["count"])
        self.assertEqual(top["count"], 2)
        self.assertEqual(set(top["runs"]), {"2026-01-02-002-block", "2026-01-03-003-block"})

    def test_single_run_duplicate_observed_is_not_repeat(self) -> None:
        """A repeat blocker requires the same normalized observed ACROSS runs.

        OPP-21: count is the number of distinct runs carrying the blocker,
        not the number of non-pass ledger rows. Two identical non-pass rows
        inside one run must not satisfy count>=2.
        """
        run_dir = (
            self.cwd / ".scratch" / "aggregate-test-effort" / "dogfood"
            / "2026-01-01-001-pass"
        )
        make_run(run_dir, blocked=["single-run blocker", "single-run blocker"])
        payload = self._payload()
        self.assertNotIn(
            "single-run blocker",
            {b["text"] for b in payload["repeat_blockers"]},
        )

    def test_override_runs(self) -> None:
        run_a = self.cwd / ".scratch" / "aggregate-test-effort" / "dogfood" / "2026-01-01-001-pass"
        payload = self._payload("--runs", str(run_a))
        self.assertEqual(payload["runs_total"], 1)
        self.assertEqual(payload["runs"][0]["id"], "2026-01-01-001-pass")

    def test_markdown_view(self) -> None:
        proc = run_aggregate("--md", cwd=self.cwd)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("| run | date | effort |", proc.stdout)
        self.assertIn("## Repeat blockers", proc.stdout)

    def test_real_scan_smoke(self) -> None:
        proc = run_aggregate("--top", "3", cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertGreaterEqual(payload["runs_total"], 0)
        self.assertIn("runs", payload)


class AggregateUnauditedTest(unittest.TestCase):
    """Issue #68: skeleton runs surface as unaudited without polluting stats."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        scratch = self.cwd / ".scratch" / "aggregate-test-effort" / "dogfood"
        make_run(scratch / "2026-01-01-001-pass")
        make_skeleton_run(scratch / "2026-01-04-004-skeleton")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _payload(self, *args: str) -> dict:
        proc = run_aggregate(*args, cwd=self.cwd)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_skeleton_run_is_discovered_and_marked_unaudited(self) -> None:
        payload = self._payload()
        self.assertEqual(payload["runs_total"], 2)
        by_id = {r["id"]: r for r in payload["runs"]}
        self.assertIn("2026-01-04-004-skeleton", by_id)
        self.assertFalse(by_id["2026-01-04-004-skeleton"]["audited"])
        self.assertTrue(by_id["2026-01-01-001-pass"]["audited"])
        # Per-run detail keeps the ledger rows for presentation.
        self.assertTrue(by_id["2026-01-04-004-skeleton"]["ledger"])

    def test_verdict_statistics_exclude_skeleton_runs(self) -> None:
        payload = self._payload()
        by_result = payload["rollup"]["by_result"]
        self.assertNotIn("n/a", by_result)
        self.assertEqual(payload["rollup"].get("unaudited_runs"), 1)

    def test_skeleton_observed_never_becomes_repeat_blocker(self) -> None:
        """Two skeletons share identical placeholder observed text; it must
        not satisfy the cross-run count>=2 repeat-blocker statistic."""
        scratch = self.cwd / ".scratch" / "aggregate-test-effort" / "dogfood"
        make_skeleton_run(scratch / "2026-01-05-005-skeleton")
        payload = self._payload()
        self.assertEqual(payload["repeat_blockers"], [])

    def test_skeleton_pointbacks_excluded_from_learning_candidates(self) -> None:
        scratch = self.cwd / ".scratch" / "aggregate-test-effort" / "dogfood"
        # Second audited run shares findings with the first, so candidates
        # exist; the skeletons must stay out of that derivation.
        make_run(scratch / "2026-01-02-002-pass")
        make_skeleton_run(scratch / "2026-01-05-005-skeleton")
        payload = self._payload()
        view = payload["learning_candidates"]
        all_cands = view.get("qualifying", []) + view.get("below_threshold", [])
        self.assertTrue(all_cands, "mixed corpus should derive candidates")
        for cand in all_cands:
            runs = {occ["run"] for occ in cand.get("occurrences", [])}
            self.assertNotIn("2026-01-04-004-skeleton", runs)
            self.assertNotIn("2026-01-05-005-skeleton", runs)

    def test_ambiguous_marker_is_fail_closed_out_of_statistics(self) -> None:
        scratch = self.cwd / ".scratch" / "aggregate-test-effort" / "dogfood"
        run_dir = scratch / "2026-01-06-006-ambiguous"
        make_skeleton_run(run_dir)
        pointback = run_dir / "point-back.md"
        pointback.write_text(
            pointback.read_text(encoding="utf-8") + "\naudited: true\n",
            encoding="utf-8",
        )
        payload = self._payload()
        by_id = {r["id"]: r for r in payload["runs"]}
        self.assertFalse(by_id[run_dir.name]["audited"])
        self.assertEqual(payload["rollup"]["unaudited_runs"], 2)
        self.assertNotIn("n/a", payload["rollup"]["by_result"])

    def test_markdown_view_marks_unaudited_runs(self) -> None:
        proc = run_aggregate("--md", cwd=self.cwd)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("| run | date | effort |", proc.stdout)
        self.assertIn("not audited", proc.stdout)


if __name__ == "__main__":
    unittest.main()
