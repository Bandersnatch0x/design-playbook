#!/usr/bin/env python3
"""RunFacts immutable optional artifact loading tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts.run_facts import capture_run_facts  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
