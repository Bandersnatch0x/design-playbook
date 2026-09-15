#!/usr/bin/env python3
"""Evidence preflight tests (ADR-0043 narrow slice).

``mcp/evidence/evidence_preflight.py`` statically checks the capture-plan
entries the orchestrator is about to send to ``execute_capture_plan``. The
tests pin the slice's four boundaries:

- static only - no Provider call, no Manifest write, no verdict: the output
  is a fact list; error facts are things that would fail at the provider;
- contract reuse - capture-contract fields are delegated to
  ``capture_contract.py`` (a malformed viewport must produce the same
  recapture instruction, not a second dialect);
- artifact boundary - relative evidence/-subtree paths only, collisions
  reported, overwrite opt-in surfaced as an advisory;
- mirror surface - ``file://`` targets are advisory-only context, never an
  error and never a judgment.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence import evidence_preflight as ep  # noqa: E402

MODULE = _PKG_ROOT / "mcp" / "evidence" / "evidence_preflight.py"


def _entry(**overrides: object) -> dict:
    entry = {
        "url": "http://127.0.0.1:8000/settings",
        "type": "screenshot",
        "state": "ok",
        "actions": [{"do": "wait_for_state", "state": "ok"}],
        "artifact_path": "evidence/settings-ok.png",
        "overwrite": False,
        "schemaVersion": 1,
        "viewport": {"width": 1280, "height": 800,
                     "devicePixelRatio": 1, "colorScheme": "light"},
    }
    entry.update(overrides)
    return entry


def _codes(facts: list[ep.PreflightFact]) -> set[str]:
    return {fact.code for fact in facts}


def _errors(facts: list[ep.PreflightFact]) -> list[ep.PreflightFact]:
    return [fact for fact in facts if fact.severity == "error"]


class PreflightPlanTests(unittest.TestCase):
    def test_valid_plan_reports_nothing(self) -> None:
        self.assertEqual(ep.preflight_plan([_entry()]), [])

    def test_plan_must_be_a_non_empty_list(self) -> None:
        for bad in (None, {}, [], "plan", [_entry(), "junk"]):
            with self.subTest(plan=bad):
                self.assertTrue(_errors(ep.preflight_plan(bad)))

    def test_missing_required_fields_are_errors(self) -> None:
        entry = _entry()
        del entry["url"]
        entry["state"] = ""
        facts = ep.preflight_entry(entry, 1)
        self.assertEqual(_codes(facts), {"missing_field"})

    def test_bad_type_and_url_scheme(self) -> None:
        facts = ep.preflight_plan([
            _entry(type="pdf"), _entry(url="ftp://host/x")])
        self.assertIn("bad_type", _codes(facts))
        self.assertIn("bad_url_scheme", _codes(facts))

    def test_capture_contract_delegated_not_reinvented(self) -> None:
        entry = _entry()
        del entry["schemaVersion"]
        facts = ep.preflight_entry(entry, 1)
        self.assertEqual(_codes(facts), {"capture_contract"})
        self.assertIn("schemaVersion", facts[0].detail)

    def test_artifact_boundary_mirrors_provider_rules(self) -> None:
        for path in ("/abs/evidence/x.png", "C:\\run\\evidence\\x.png",
                     "evidence/../escape.png", "bare.png", "evidence/",
                     "evidence/sub/", "evidence/back\\slash.png"):
            with self.subTest(path=path):
                facts = ep.preflight_entry(_entry(artifact_path=path), 1)
                self.assertEqual(_codes(facts), {"bad_artifact_path"},
                                 f"expected rejection for {path}")

    def test_action_parameter_requirements(self) -> None:
        facts = ep.preflight_entry(_entry(actions=[
            {"do": "click"},
            {"do": "fill", "selector": "#a"},
            {"do": "select_option", "selector": "#s"},
            {"do": "press", "key": "Enter"},
            {"do": "wait", "ms": 0},
            {"do": "hover", "selector": "#x"},
        ]), 1)
        self.assertEqual(
            _codes(facts),
            {"bad_action_param", "bad_action_do"})
        details = " | ".join(fact.detail for fact in facts)
        self.assertIn("click", details)
        self.assertIn("value", details)
        self.assertIn("value|label", details)
        self.assertIn("ms", details)

    def test_storage_state_shape_errors(self) -> None:
        facts = ep.preflight_plan([
            _entry(storage_state="../x.json"),
            _entry(storage_state="evidence/session.txt"),
            _entry(storage_state="/tmp/session.json"),
            _entry(storage_state="C:/secrets/session.json"),
            _entry(storage_state="session\\state.json"),
        ])
        self.assertIn("bad_storage_state", _codes(facts))
        self.assertGreaterEqual(
            sum(1 for fact in facts if fact.code == "bad_storage_state"), 5
        )

    def test_storage_state_missing_file_is_not_a_preflight_error(self) -> None:
        facts = ep.preflight_plan([_entry(storage_state="session.json")])
        self.assertFalse(
            any(fact.code == "bad_storage_state" and fact.severity == "error"
                for fact in facts)
        )

    def test_file_url_is_advisory_mirror_surface_only(self) -> None:
        facts = ep.preflight_plan([_entry(url="file:///app/filled-ui.html")])
        self.assertEqual(_errors(facts), [])
        advisories = [f for f in facts if f.severity == "advisory"]
        self.assertEqual([f.code for f in advisories], ["mirror_surface"])

    def test_artifact_collision_and_overwrite_advisory(self) -> None:
        plan = [_entry(), _entry(state="loading",
                                 artifact_path="evidence/settings-ok.png")]
        facts = ep.preflight_plan(plan)
        self.assertEqual(_codes(facts), {"artifact_collision"})
        plan[1]["overwrite"] = True
        facts = ep.preflight_plan(plan)
        self.assertEqual(_errors(facts), [])
        self.assertEqual(
            [f.code for f in facts if f.severity == "advisory"],
            ["artifact_overwrite"])

    def test_no_io_no_verdict_surface(self) -> None:
        # The module owns no provider, manifest, or verdict vocabulary.
        source = MODULE.read_text(encoding="utf-8")
        for forbidden in ("execute_capture_plan(", "manifest.jsonl", "Pass",
                          "Recirculate"):
            self.assertNotIn(forbidden, source)


class PreflightCliTests(unittest.TestCase):
    def _run(self, plan: object) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(plan, fh)
            path = fh.name
        try:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            return subprocess.run(
                [sys.executable, str(MODULE), path],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=env, check=False)
        finally:
            os.unlink(path)

    def test_clean_plan_exits_zero(self) -> None:
        proc = self._run([_entry()])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["errors"], 0)
        self.assertEqual(payload["facts"], [])

    def test_error_plan_exits_one_with_facts(self) -> None:
        proc = self._run([_entry(artifact_path="bare.png")])
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["errors"], 1)
        self.assertEqual(payload["facts"][0]["code"], "bad_artifact_path")

    def test_malformed_input_exits_two(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(MODULE), "does-not-exist.json"],
            capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
