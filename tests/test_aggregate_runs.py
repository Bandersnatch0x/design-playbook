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
        self.assertEqual(by_id["2026-01-01-001-pass"]["gate"]["status"], "ok")
        self.assertEqual(by_id["2026-01-01-001-pass"]["date"], "2026-01-01")
        self.assertEqual(by_id["2026-01-01-001-pass"]["effort"], "aggregate-test-effort")
        self.assertFalse(by_id["2026-01-03-003-block"]["artifacts"]["plan"])
        self.assertTrue(by_id["2026-01-01-001-pass"]["artifacts"]["spec"])

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


if __name__ == "__main__":
    unittest.main()
