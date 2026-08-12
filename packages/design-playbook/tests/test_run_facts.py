#!/usr/bin/env python3
"""Interface tests for the immutable Closed-loop run facts module."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.run_facts import capture_run_facts  # noqa: E402
from design_playbook.scripts.run_status import inspect_run, next_action  # noqa: E402


class RunFactsTests(unittest.TestCase):
    def test_loads_owned_syntax_and_integrity_facts_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spec.md").write_text("# L1\n", encoding="utf-8")
            (root / "point-back.md").write_text(
                "## Verdict\n\n**Pass.**\n\n"
                "criterion: L6.1\nrequired: page\n"
                "observed: evidence/page.png\nresult: pass\n",
                encoding="utf-8",
            )
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "manifest.jsonl").write_text(
                json.dumps({"criterion": "L6.1", "artifact": "page.png"}),
                encoding="utf-8",
            )

            facts = capture_run_facts(run_root=root)

            self.assertEqual(facts.verdict.canonical, "pass")
            self.assertEqual(len(facts.ledger.rows), 1)
            self.assertEqual(len(facts.manifest_entries), 1)
            self.assertIn("point-back.md", facts.existing_paths)
            self.assertIsNotNone(facts.preview)

            # The snapshot remains stable if callers mutate the tree later.
            (root / "point-back.md").write_text("changed", encoding="utf-8")
            self.assertEqual(facts.verdict.canonical, "pass")

    def test_status_uses_captured_baseline_after_tree_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = root / "design-baseline"
            baseline.mkdir()
            state_path = baseline / "state.json"
            state_path.write_text(
                json.dumps({"status": "ready", "decision": {}}),
                encoding="utf-8",
            )
            facts = capture_run_facts(run_root=root)
            states = inspect_run(root, run_facts=facts)

            state_path.write_text("{", encoding="utf-8")

            self.assertEqual(
                next_action(states, root, run_facts=facts),
                "Design baseline bound — resume at reference-intake? "
                "(if needed) or ux-spec.",
            )

    def test_nested_confirm_values_cannot_mutate_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = root / "preview"
            preview.mkdir()
            (preview / "round-1.html").write_text("prototype", encoding="utf-8")
            (preview / "confirm-round-1.json").write_text(
                json.dumps(
                    {
                        "round": 1,
                        "confirmed": True,
                        "metadata": {"reviewers": [{"name": "original"}]},
                    }
                ),
                encoding="utf-8",
            )
            facts = capture_run_facts(run_root=root)
            assert facts.preview is not None
            record = facts.preview.current_confirms[0]

            first = record.data
            assert isinstance(first, dict)
            first["metadata"]["reviewers"][0]["name"] = "mutated"

            second = record.data
            assert isinstance(second, dict)
            self.assertEqual(
                second["metadata"]["reviewers"][0]["name"],
                "original",
            )

    def test_missing_explicit_files_are_structured_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = capture_run_facts(
                spec_path=root / "missing-spec.md",
                pointback_path=root / "missing-point-back.md",
            )

            self.assertEqual(facts.spec_text, "")
            self.assertEqual(facts.pointback_text, "")
            self.assertEqual(
                [(error.artifact, error.code) for error in facts.read_errors],
                [("spec", "missing"), ("point_back", "missing")],
            )

    def test_unreadable_manifest_is_a_structured_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            evidence.mkdir()
            (root / "point-back.md").write_text("", encoding="utf-8")
            (evidence / "manifest.jsonl").write_bytes(b"\xff\xfe")

            facts = capture_run_facts(run_root=root)

            self.assertEqual(facts.manifest_entries, ())
            self.assertEqual(
                [(error.artifact, error.code) for error in facts.read_errors],
                [("manifest", "unreadable")],
            )

    def test_nested_json_values_cannot_mutate_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "manifest.jsonl").write_text(
                json.dumps({"request": {"viewport": {"width": 390}}}),
                encoding="utf-8",
            )
            baseline = root / "design-baseline"
            baseline.mkdir()
            (baseline / "state.json").write_text(
                json.dumps({"decision": {"reason": "captured"}}),
                encoding="utf-8",
            )
            facts = capture_run_facts(run_root=root)

            facts.manifest_entries[0]["request"]["viewport"]["width"] = 1
            baseline_value = facts.baseline_state
            assert isinstance(baseline_value, dict)
            baseline_value["decision"]["reason"] = "mutated"

            self.assertEqual(
                facts.manifest_entries[0]["request"]["viewport"]["width"],
                390,
            )
            self.assertEqual(
                facts.baseline_state["decision"]["reason"],
                "captured",
            )


if __name__ == "__main__":
    unittest.main()
