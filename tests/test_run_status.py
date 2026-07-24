#!/usr/bin/env python3
"""Black-box tests for scripts/run_status.py."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_STATUS = ROOT / "scripts" / "run_status.py"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    # Force UTF-8 on the child's stdio: run_status.py emits JSON with
    # ensure_ascii=False, and Python's own DeprecationWarnings (routed to
    # stderr) contain smart quotes that the Windows default GBK codec
    # cannot decode. A UTF-8 round-trip keeps the black-box test robust
    # regardless of the host locale.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(RUN_STATUS), *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


class RunStatusTests(unittest.TestCase):
    def test_status_from_spec_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-a"
            run_root.mkdir()
            (run_root / "spec.md").write_text("# L1\n", encoding="utf-8")
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            by_key = {s["key"]: s for s in payload["stages"]}
            self.assertFalse(by_key["reference"]["present"])
            self.assertTrue(by_key["spec"]["present"])
            self.assertIn("Resume", payload["next"])

    def test_status_from_reference_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-ref"
            ref = run_root / "reference"
            ref.mkdir(parents=True)
            (ref / "contract.md").write_text("# ref\n", encoding="utf-8")
            (ref / "manifest.json").write_text("{\"schema\": \"x\"}\n", encoding="utf-8")
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            by_key = {s["key"]: s for s in payload["stages"]}
            self.assertFalse(by_key["baseline"]["present"])
            self.assertTrue(by_key["reference"]["present"])
            self.assertIn("ux-spec", payload["next"])

    def test_pending_design_baseline_blocks_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-baseline-pending"
            baseline = run_root / "design-baseline"
            baseline.mkdir(parents=True)
            (baseline / "state.json").write_text(
                json.dumps(
                    {
                        "schema": "design-baseline/v1",
                        "status": "needs_confirmation",
                        "baseline": None,
                        "draft": {
                            "path": "design-baseline/DESIGN.draft.md",
                            "sha256": "b" * 64,
                        },
                        "decision": None,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (baseline / "DESIGN.draft.md").write_text(
                "# proposed baseline\n", encoding="utf-8"
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("baseline", payload["next"].lower())
            self.assertIn("before fill", payload["next"].lower())

    def test_design_baseline_draft_without_state_does_not_mark_stage(self) -> None:
        # Sole gate artifact is state.json (ADR-0012). Orphan draft/evidence
        # must not flip baseline.present or invent a baseline resume hint.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-baseline-missing-state"
            baseline = run_root / "design-baseline"
            baseline.mkdir(parents=True)
            (baseline / "DESIGN.draft.md").write_text(
                "# proposed baseline\n", encoding="utf-8"
            )
            (baseline / "evidence.json").write_text("{}\n", encoding="utf-8")
            (run_root / "spec.md").write_text("# L1\n", encoding="utf-8")

            result = _run(str(run_root), "--json")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            by_key = {s["key"]: s for s in payload["stages"]}
            self.assertFalse(by_key["baseline"]["present"])
            self.assertTrue(by_key["spec"]["present"])
            self.assertNotIn("state.json", payload["next"])
            self.assertIn("ui-picker", payload["next"].lower())

    def test_accepted_design_baseline_routes_to_next_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-baseline-accepted"
            baseline = run_root / "design-baseline"
            baseline.mkdir(parents=True)
            (baseline / "state.json").write_text(
                json.dumps(
                    {
                        "schema": "design-baseline/v1",
                        "status": "ready",
                        "baseline": {
                            "path": "DESIGN.md",
                            "sha256": "a" * 64,
                            "origin": "generated",
                        },
                        "decision": {
                            "kind": "accepted",
                            "confirmed_at": "2026-07-24T00:00:00Z",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("ux-spec", payload["next"])

    def test_design_baseline_waiver_requires_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-baseline-empty-waiver"
            baseline = run_root / "design-baseline"
            baseline.mkdir(parents=True)
            (baseline / "state.json").write_text(
                json.dumps(
                    {
                        "schema": "design-baseline/v1",
                        "status": "waived",
                        "baseline": None,
                        "decision": {
                            "kind": "waived",
                            "reason": "",
                            "confirmed_at": "2026-07-24T00:00:00Z",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("waiver", payload["next"].lower())
            self.assertIn("before fill", payload["next"].lower())

    def test_explicit_design_baseline_waiver_routes_to_next_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-baseline-waived"
            baseline = run_root / "design-baseline"
            baseline.mkdir(parents=True)
            (baseline / "state.json").write_text(
                json.dumps(
                    {
                        "schema": "design-baseline/v1",
                        "status": "waived",
                        "baseline": None,
                        "decision": {
                            "kind": "waived",
                            "reason": "User accepted legacy visual drift",
                            "confirmed_at": "2026-07-24T00:00:00Z",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("ux-spec", payload["next"])

    def test_status_after_accept_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-b"
            run_root.mkdir()
            (run_root / "spec.md").write_text("spec\n", encoding="utf-8")
            (run_root / "point-back.md").write_text(
                "## Verdict\n\nPass\n", encoding="utf-8"
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "Pass")
            self.assertIn("complete", payload["next"].lower())


def _write_preview(run_root: Path, files: dict[str, str]) -> None:
    """Materialise a preview/ dir with the given relative-path -> contents."""
    preview = run_root / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    for rel, body in files.items():
        target = preview / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


class RunStatusPreviewRoundTests(unittest.TestCase):
    """Issue 03: numeric round sort + fail-closed next_action.

    The state machine must reuse the validator's judgment (latest_numeric_round
    + is_confirmed_valid) so it cannot drift from G5. Aborted / floor-failed /
    stale-confirm runs must fail closed — never direct the orchestrator to
    'resume at fill'.
    """

    def test_numeric_round_sort_picks_round_10_over_round_2(self) -> None:
        # round-2 confirm is OPEN; round-10 confirm is decided-positive.
        # Lexicographic filename sort would pick confirm-round-2.json last
        # and report 'open'; numeric sort must pick round-10 and resume.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            _write_preview(run_root, {
                "log.md": "preview log\n",
                "round-2.html": "<html>2</html>",
                "round-10.html": "<html>10</html>",
                "confirm-round-2.json": json.dumps({"confirmed": False}),
                "confirm-round-10.json": json.dumps({
                    "confirmed": True, "floor_pass": True, "round": 10}),
            })
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("resume at fill", payload["next"].lower(),
                          payload["next"])

    def test_stale_confirm_does_not_mask_undecided_round(self) -> None:
        # round-1 confirmed; round-2 has a prototype but no confirm yet.
        # Old lexicographic latest_confirm returned confirm-round-1.json and
        # said 'resume at fill', masking the undecided current round.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            _write_preview(run_root, {
                "log.md": "preview log\n",
                "round-1.html": "<html>1</html>",
                "round-2.html": "<html>2</html>",
                "confirm-round-1.json": json.dumps({
                    "confirmed": True, "floor_pass": True, "round": 1}),
            })
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            nxt = payload["next"].lower()
            self.assertNotIn("resume at fill", nxt, payload["next"])
            self.assertIn("preview", nxt, payload["next"])

    def test_aborted_confirm_fail_closed(self) -> None:
        # aborted=true must NOT direct to fill (old code: 'or aborted' was
        # fail-open). Fail closed with an explicit error.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            _write_preview(run_root, {
                "log.md": "preview log\n",
                "round-1.html": "<html>1</html>",
                "confirm-round-1.json": json.dumps(
                    {"aborted": True, "round": 1}),
            })
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            nxt = payload["next"].lower()
            self.assertNotIn("resume at fill", nxt, payload["next"])
            self.assertIn("abort", nxt, payload["next"])

    def test_confirmed_without_floor_pass_fail_closed(self) -> None:
        # confirmed=true but floor_pass=false must NOT direct to fill.
        # is_confirmed_valid requires both; reuse must reject this record.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            _write_preview(run_root, {
                "log.md": "preview log\n",
                "round-1.html": "<html>1</html>",
                "confirm-round-1.json": json.dumps({
                    "confirmed": True, "floor_pass": False,
                    "floor_failure": "feedback below floor", "round": 1}),
            })
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            nxt = payload["next"].lower()
            self.assertNotIn("resume at fill", nxt, payload["next"])
            self.assertIn("floor", nxt, payload["next"])

    def test_confirmed_with_floor_pass_resumes_at_fill(self) -> None:
        # Regression guard: the legitimate decided-positive path still resumes.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            _write_preview(run_root, {
                "log.md": "preview log\n",
                "round-1.html": "<html>1</html>",
                "confirm-round-1.json": json.dumps({
                    "confirmed": True, "floor_pass": True, "round": 1}),
            })
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("resume at fill", payload["next"].lower(),
                          payload["next"])

    def test_legacy_confirm_only_without_html_resumes_at_fill(self) -> None:
        # Pre-html-schema runs: confirm-round-N.json with no round-N.html
        # must still resolve via latest_numeric_round's combined scan.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            _write_preview(run_root, {
                "confirm-round-1.json": json.dumps({
                    "confirmed": True, "floor_pass": True}),
            })
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("resume at fill", payload["next"].lower(),
                          payload["next"])


if __name__ == "__main__":
    unittest.main()
