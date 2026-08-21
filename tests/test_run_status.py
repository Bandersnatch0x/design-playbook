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
# Single source is the packaged copy (ADR-0022); the root dev copy is gone.
RUN_STATUS = ROOT / "packages" / "design-playbook" / "scripts" / "run_status.py"


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
    def test_unreadable_point_back_is_an_operational_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-unreadable-point-back"
            run_root.mkdir()
            (run_root / "point-back.md").write_bytes(b"\xff")

            for args in ((str(run_root),), (str(run_root), "--json")):
                with self.subTest(args=args):
                    result = _run(*args)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertIn(
                        "RUN STATUS ERROR: cannot read point-back.md:",
                        result.stderr,
                    )

    def test_unreadable_plan_is_an_operational_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-unreadable-plan"
            run_root.mkdir()
            (run_root / "plan.md").write_bytes(b"\xff")
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("RUN STATUS ERROR: cannot read plan.md:", result.stderr)

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

    The state machine must reuse the Preview integrity snapshot so it cannot
    drift from G5 on current round or confirm validity. Aborted / floor-failed /
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
        # Preview integrity validity requires both; reuse must reject this record.
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

    def test_status_uses_canonical_confirm_filename_despite_json_round_mismatch(self) -> None:
        # G5 excludes this record via round cross-check, but run_status has
        # historically narrated the canonical current filename directly.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            _write_preview(run_root, {
                "round-2.html": "<html>2</html>",
                "confirm-round-2.json": json.dumps({
                    "round": 1, "confirmed": True, "floor_pass": True}),
            })

            result = _run(str(run_root), "--json")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("resume at fill", payload["next"].lower())

    def test_round_html_marks_preview_stage_without_log_or_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            _write_preview(run_root, {"round-2.html": "<html>open</html>"})

            result = _run(str(run_root), "--json")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            by_key = {stage["key"]: stage for stage in payload["stages"]}
            self.assertTrue(by_key["preview"]["present"])
            self.assertIn("finish preview", payload["next"].lower())

    def test_confirm_only_does_not_create_preview_occurrence(self) -> None:
        # G5 occurrence requires log, round HTML, or a binding-valid decision.
        # Align run status so a stray legacy confirm cannot invent a Preview run.
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
            by_key = {stage["key"]: stage for stage in payload["stages"]}
            self.assertFalse(by_key["preview"]["present"])
            self.assertNotIn("resume at fill", payload["next"].lower())


class RunStatusVnextTests(unittest.TestCase):
    """vNext S1 (issue #34, exit criterion 5): the recovery narration
    recognizes the run-profile block (plan.md) and the shaping session
    artifacts on the packaged P2 fixture run."""

    FIXTURE = ROOT / "packages" / "design-playbook" / "examples" / "export-entry" / "run"

    def test_run_profile_and_shaping_in_json(self) -> None:
        result = _run(str(self.FIXTURE), "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        profile = payload["run_profile"]
        self.assertIsNotNone(profile)
        self.assertEqual(profile["tier"], "P2")
        self.assertTrue(profile["confirmed_by"].casefold().startswith("user"))
        self.assertEqual(
            [(skip["step"], bool(skip["reason"])) for skip in profile["skipped"]],
            [("preview", True)],
        )
        self.assertEqual(profile["upgrades"], [])
        self.assertEqual(payload["shaping"], "archived")
        self.assertEqual(payload["verdict"], "Pass")

    def test_run_profile_and_shaping_in_text(self) -> None:
        result = _run(str(self.FIXTURE))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("run-profile: tier P2 (confirmed by user)", result.stdout)
        self.assertIn("shaping: session archived", result.stdout)
        self.assertIn(
            "point-back: six-block vNext report with invalidated evidence set",
            result.stdout)

    def test_run_without_vnext_artifacts_has_no_narration(self) -> None:
        # Backward compatibility: a plain run reports no run-profile/shaping.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-plain"
            run_root.mkdir()
            (run_root / "spec.md").write_text("# L1\n", encoding="utf-8")
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIsNone(payload["run_profile"])
            self.assertIsNone(payload["shaping"])


class RunStatusFillStageTests(unittest.TestCase):
    """Issue #44: fill surfaces outside the run root are judged on the
    ``fill:`` paths plan.md registers (stage-registry markers unchanged)."""

    def test_plan_declared_run_root_path_marks_fill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-fill"
            run_root.mkdir()
            (run_root / "spec.md").write_text("# L1\n", encoding="utf-8")
            (run_root / "plan.md").write_text(
                "# plan\n\nfill: surface.html\n", encoding="utf-8")

            # declared but absent: the fill stage stays unchecked
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            by_key = {s["key"]: s for s in payload["stages"]}
            self.assertFalse(by_key["fill"]["present"])

            (run_root / "surface.html").write_text(
                "<html></html>", encoding="utf-8")
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            by_key = {s["key"]: s for s in payload["stages"]}
            self.assertTrue(by_key["fill"]["present"])
            self.assertIn("surface.html", by_key["fill"]["evidence"])
            self.assertIn("craft-guard", payload["next"])

    def test_plan_declared_host_path_marks_fill(self) -> None:
        # Product-side fill: the surface lives in the host tree, not under
        # the run root; the declared path resolves against the run root
        # first, then the orchestrating cwd (the host project root).
        with tempfile.TemporaryDirectory() as tmp:
            host = Path(tmp) / "host"
            (host / "src").mkdir(parents=True)
            (host / "src" / "panel.html").write_text(
                "<html></html>", encoding="utf-8")
            run_root = host / ".scratch" / "run-fill"
            run_root.mkdir(parents=True)
            (run_root / "spec.md").write_text("# L1\n", encoding="utf-8")
            (run_root / "plan.md").write_text(
                "# plan\n\nfill: src/panel.html\n", encoding="utf-8")

            result = _run(str(run_root), "--json", cwd=host)

            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            by_key = {s["key"]: s for s in payload["stages"]}
            self.assertTrue(by_key["fill"]["present"])
            self.assertIn("src/panel.html", by_key["fill"]["evidence"])

    def test_fenced_fill_example_is_not_a_declaration(self) -> None:
        # Fenced blocks are prose/examples: a `fill:` line inside ``` is
        # never a declaration, even when the cited path exists (the fill
        # stage stays unchecked — fail-closed, no narrated example counts).
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-fill-fenced"
            run_root.mkdir()
            (run_root / "spec.md").write_text("# L1\n", encoding="utf-8")
            (run_root / "plan.md").write_text(
                "# plan\n\n"
                "```yaml\n"
                "fill: spec.md\n"
                "```\n",
                encoding="utf-8")

            result = _run(str(run_root), "--json")

            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            by_key = {s["key"]: s for s in payload["stages"]}
            self.assertFalse(by_key["fill"]["present"])

            # control: the same line, unfenced, is the declaration
            (run_root / "plan.md").write_text(
                "# plan\n\nfill: spec.md\n", encoding="utf-8")
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            by_key = {s["key"]: s for s in payload["stages"]}
            self.assertTrue(by_key["fill"]["present"])
            self.assertIn("spec.md", by_key["fill"]["evidence"])


class RunStatusAuditProjectionTests(unittest.TestCase):
    """ADR-0033: audit marker facts project into status — a verdict the audit
    never earned is never narrated (unaudited / ambiguous / legacy)."""

    def _write_run(self, tmp: str, name: str, pointback: str) -> Path:
        run_root = Path(tmp) / name
        run_root.mkdir()
        (run_root / "spec.md").write_text("# L1\n", encoding="utf-8")
        (run_root / "point-back.md").write_text(pointback, encoding="utf-8")
        return run_root

    def test_skeleton_marker_projects_not_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = self._write_run(
                tmp, "run-skeleton", "# Report\n\naudited: false\n\nBody.\n")
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIs(payload["audited"], False)
            self.assertEqual(payload["audit_marker_state"], "unaudited")
            self.assertIsNone(payload["verdict"])
            self.assertIn("unaudited skeleton", payload["next"])

            text = _run(str(run_root))
            self.assertEqual(text.returncode, 0, text.stdout + text.stderr)
            self.assertIn("audit: not audited (skeleton point-back)",
                          text.stdout)
            self.assertIn("unaudited skeleton", text.stdout)

    def test_ambiguous_marker_is_never_narrated_as_skeleton(self) -> None:
        # Regression: the ambiguous text branch used to sit behind
        # `audited is False` (unreachable — ambiguous projects False), so a
        # duplicate-marker run printed the clean-skeleton line while its
        # `next:` hint named the marker damage.
        with tempfile.TemporaryDirectory() as tmp:
            run_root = self._write_run(
                tmp, "run-ambiguous", "audited: false\n\naudited: false\n")
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIs(payload["audited"], False)
            self.assertEqual(payload["audit_marker_state"], "ambiguous")
            self.assertIsNone(payload["verdict"])
            self.assertIn("duplicate or malformed audited markers",
                          payload["next"])

            text = _run(str(run_root))
            self.assertEqual(text.returncode, 0, text.stdout + text.stderr)
            self.assertIn(
                "audit: invalid marker (duplicate or malformed audited line)",
                text.stdout)
            self.assertNotIn("skeleton point-back", text.stdout)

    def test_legacy_report_without_marker_retains_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = self._write_run(
                tmp, "run-legacy", "## Verdict\n\nPass\n")
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIsNone(payload["audited"])
            self.assertEqual(payload["audit_marker_state"], "legacy")
            self.assertEqual(payload["verdict"], "Pass")

            text = _run(str(run_root))
            self.assertEqual(text.returncode, 0, text.stdout + text.stderr)
            self.assertNotIn("audit:", text.stdout)


if __name__ == "__main__":
    unittest.main()
