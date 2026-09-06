#!/usr/bin/env python3
"""RunFacts immutable optional artifact loading tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts.run_facts import (  # noqa: E402
    STATED_ARTIFACTS,
    capture_run_facts,
    resolve_declared_fill,
)


class RunFactsOptionalArtifactTests(unittest.TestCase):
    def test_vnext_artifacts_load_into_one_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plan.md").write_text(
                """# plan\n<!-- run-profile: v1 -->\n\n```yaml\ntier: P2\nconfirmed_by: user + now\n```\n""",
                encoding="utf-8",
            )
            (root / "decision-report.md").write_text(
                "## DD-0001 — choice\n\n```yaml\nid: DD-0001\ntier: record\nstatus: confirmed-agent\nquestion: choice\n```\n",
                encoding="utf-8",
            )
            shaping = root / "shaping"
            shaping.mkdir()
            (shaping / "shaping-log.jsonl").write_text(
                '{"event":"asked","question_id":"Q1"}\n',
                encoding="utf-8",
            )
            facts = capture_run_facts(run_root=root)
            self.assertEqual(facts.run_profile.version, 1)
            self.assertEqual(facts.run_profile.tier, "P2")
            self.assertEqual(facts.plan_text.splitlines()[0], "# plan")
            self.assertEqual(facts.plan_fill_artifacts, ())
            self.assertEqual(facts.craft_guard_text, "")
            self.assertEqual([entry.id for entry in facts.decision_entries], ["DD-0001"])
            self.assertEqual(facts.shaping_events[0]["event"], "asked")
            self.assertIsNone(facts.shaping_error)
            self.assertEqual(facts.artifact_state("run_profile"), "complete")
            self.assertEqual(facts.artifact_state("shaping"), "complete")

    def test_snapshot_does_not_change_when_run_files_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plan.md").write_text(
                "<!-- run-profile: v1 -->\n```yaml\ntier: P1\nconfirmed_by: user\n```\nfill: artifact.txt\n",
                encoding="utf-8",
            )
            (root / "artifact.txt").write_text("captured", encoding="utf-8")
            facts = capture_run_facts(run_root=root)
            (root / "plan.md").write_text("changed", encoding="utf-8")
            (root / "artifact.txt").unlink()
            self.assertIn("run-profile: v1", facts.plan_text)
            self.assertEqual(facts.run_profile.tier, "P1")
            self.assertEqual(facts.plan_fill_artifacts, ("artifact.txt",))

    def test_artifact_state_is_uniform_across_artifacts(self) -> None:
        """One presence vocabulary: no per-artifact conventions (ADR-0039)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spec.md").write_text("# spec\n", encoding="utf-8")
            (root / "plan.md").write_text("# plan\n", encoding="utf-8")
            # plan.md is unreadable bytes: the state is unreadable, not a
            # re-stat away from the caller.
            (root / "plan.md").write_bytes(b"\xff\xfe")
            facts = capture_run_facts(run_root=root)
            self.assertEqual(facts.artifact_state("spec"), "complete")
            self.assertEqual(facts.artifact_state("plan"), "unreadable")
            self.assertEqual(facts.artifact_state("point_back"), "missing")
            self.assertEqual(facts.artifact_state("decision_report"), "missing")
            self.assertEqual(facts.artifact_state("craft_guard"), "missing")
            self.assertEqual(facts.artifact_state("manifest"), "missing")
            self.assertEqual(facts.artifact_state("baseline"), "missing")
            self.assertEqual(facts.artifact_state("shaping"), "missing")
            self.assertEqual(facts.artifact_state("run_profile"), "unreadable")

    def test_artifact_state_without_a_run_root_is_missing(self) -> None:
        facts = capture_run_facts()
        for artifact in STATED_ARTIFACTS:
            self.assertEqual(facts.artifact_state(artifact), "missing")

    def test_artifact_state_rejects_unknown_artifacts(self) -> None:
        facts = capture_run_facts()
        with self.assertRaises(KeyError):
            facts.artifact_state("telemetry")

    def test_run_profile_missing_is_not_the_same_as_unreadable_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plan.md").write_text("# plan\n", encoding="utf-8")
            facts = capture_run_facts(run_root=root)
            self.assertEqual(facts.artifact_state("plan"), "complete")
            self.assertEqual(facts.artifact_state("run_profile"), "missing")
            self.assertIsNone(facts.run_profile)

    def test_empty_craft_guard_presence_is_captured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "craft-guard.md").write_text("", encoding="utf-8")
            facts = capture_run_facts(run_root=root)
            (root / "craft-guard.md").unlink()
            self.assertTrue(facts.craft_guard_exists)
            self.assertEqual(facts.craft_guard_text, "")

    def test_malformed_shaping_is_recorded_without_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            (root / "shaping").mkdir(parents=True)
            (root / "shaping" / "shaping-log.jsonl").write_text(
                '{"event":"not-valid"}\n', encoding="utf-8"
            )
            facts = capture_run_facts(run_root=root)
            self.assertIsNone(facts.shaping_events)
            self.assertTrue(facts.shaping_error)
            self.assertEqual(facts.artifact_state("shaping"), "unreadable")

    def test_unreadable_utf8_spec_keeps_decode_error_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spec.md").write_bytes(b"\xff\xfe")

            facts = capture_run_facts(run_root=root)

            errors = [error for error in facts.read_errors if error.artifact == "spec"]
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0].code, "unreadable")
            self.assertIn("utf-8", errors[0].message.lower())
            self.assertNotEqual(errors[0].message, "invalid UTF-8")


class DeclaredFillResolutionTests(unittest.TestCase):
    """The single fill-resolution invariant: absolute as-is, else run-root before cwd."""

    def test_run_root_precedes_cwd_for_relative_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_root = base / "run"
            run_root.mkdir()
            cwd_root = base / "cwd"
            cwd_root.mkdir()
            (run_root / "surface.html").write_text("run", encoding="utf-8")
            (cwd_root / "surface.html").write_text("cwd", encoding="utf-8")
            with patch.object(Path, "cwd", return_value=cwd_root):
                resolved = resolve_declared_fill(run_root, "surface.html")
            self.assertEqual(resolved, run_root / "surface.html")

    def test_cwd_is_the_fallback_when_run_root_lacks_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run_root = base / "run"
            run_root.mkdir()
            cwd_root = base / "cwd"
            cwd_root.mkdir()
            (cwd_root / "surface.html").write_text("cwd", encoding="utf-8")
            with patch.object(Path, "cwd", return_value=cwd_root):
                resolved = resolve_declared_fill(run_root, "surface.html")
            self.assertEqual(resolved, cwd_root / "surface.html")

    def test_absolute_declaration_resolves_as_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            absolute = run_root.parent / "elsewhere.html"
            absolute.write_text("absolute", encoding="utf-8")
            resolved = resolve_declared_fill(run_root, str(absolute))
            self.assertEqual(resolved, absolute)

    def test_missing_declaration_resolves_to_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            self.assertIsNone(resolve_declared_fill(run_root, "no-such-fill.html"))

    def test_plan_fill_artifacts_keeps_existing_declarations_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plan.md").write_text(
                "fill: exists.html\nfill: gone.html\n", encoding="utf-8"
            )
            (root / "exists.html").write_text("fill", encoding="utf-8")
            facts = capture_run_facts(run_root=root)
            self.assertEqual(facts.plan_fill_artifacts, ("exists.html",))
            self.assertEqual(facts.plan_fill_declarations, ("exists.html", "gone.html"))


if __name__ == "__main__":
    unittest.main()
