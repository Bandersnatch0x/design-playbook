#!/usr/bin/env python3
"""Process-boundary tests for G7 contract-drift diagnostics."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import contract_v1 as cv  # noqa: E402
import g7_contract_drift as g7  # noqa: E402


def _seed(project: Path) -> None:
    cv.promote_fields(
        {
            "a.goal": {
                "value": "ship",
                "provenance": "inferred",
                "resolution": "assumed",
            }
        },
        project_dir=project,
        changelog_summary="seed",
        at="2026-08-08T00:00:00Z",
    )


class G7Tests(unittest.TestCase):
    def test_missing_binding_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p"
            run = Path(tmp) / "r"
            project.mkdir()
            run.mkdir()
            _seed(project)
            findings = g7.check_g7(project, run)
            self.assertTrue(any(item.rule_id == "G7.missing_binding" for item in findings))

    def test_unchanged_binding_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p"
            run = Path(tmp) / "r"
            _seed(project)
            bind = cv.bind_first(project, run, acknowledgements=["a.goal"])
            self.assertTrue(bind.ok)
            findings = g7.check_g7(project, run)
            self.assertEqual(findings, [])

    def test_unrecorded_field_change_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p"
            run = Path(tmp) / "r"
            _seed(project)
            cv.bind_first(project, run, acknowledgements=["a.goal"])
            # Mutate contract without a decision.
            contract = cv.load_contract(project / cv.CONTRACT_FILENAME)
            contract["fields"]["a.goal"]["value"] = "mutated"
            cv.dump_contract(project / cv.CONTRACT_FILENAME, contract)
            findings = g7.check_g7(project, run)
            self.assertTrue(
                any(item.rule_id == "G7.unrecorded_field_change" for item in findings)
            )

    def test_authorized_change_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p"
            run = Path(tmp) / "r"
            _seed(project)
            cv.bind_first(project, run, acknowledgements=["a.goal"])
            cv.append_decision(project / cv.DECISIONS_FILENAME, {
                "id": "d1",
                "field": "a.goal",
                "decision": "ship v2",
                "rationale": "user confirmed",
                "confirmed_at": "2026-08-08T02:00:00Z",
            })
            # Promote value through apply path by rewriting contract fields from decisions.
            applied = cv.apply_decisions(
                cv.load_contract(project / cv.CONTRACT_FILENAME),
                cv.load_decisions(project / cv.DECISIONS_FILENAME),
            )
            cv.dump_contract(project / cv.CONTRACT_FILENAME, applied)
            findings = g7.check_g7(project, run)
            self.assertEqual(findings, [], [item.message for item in findings])


if __name__ == "__main__":
    unittest.main()
