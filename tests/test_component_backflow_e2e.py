#!/usr/bin/env python3
"""T-071 end-to-end: one component candidate walks distill -> adjudicate ->
promote -> DESIGN.md, and the closed loop is observable.

Drives the real arc over multi-run decision-report fixtures: the distiller
(T-067) surfaces a qualifying candidate, the proposal (T-069) renders it for
adjudication, a user promote event is recorded (T-068), and
``design_baseline.promote`` (T-070) merges it into DESIGN.md — after which the
promoted path is present as a ``## Component Stylings`` entry that ui-picker's
existing read path picks up (no ui-picker change), with backup + verify green.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
MODULE_PATH = (PKG / "skills" / "design-baseline" / "scripts"
               / "design_baseline.py")

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

SPEC = importlib.util.spec_from_file_location("design_baseline", MODULE_PATH)
design_baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(design_baseline)

from design_playbook.scripts import component_candidates as cc  # noqa: E402
from design_playbook.scripts import promotion_governance as pg  # noqa: E402

TS = "2026-09-22T00:00:00Z"
COMPONENT = "src/components/Button.tsx"


def _report(scene: str) -> str:
    return ("# Decision report\n\n```text\n"
            f"scene: {scene}\n"
            "components:\n"
            f"  primary-action -> reuse {COMPONENT} (matches primary)\n"
            "  status -> new (no declared candidate)\n"
            "```\n")


def _baseline_project(tmp: str):
    """A project whose first-party source includes the promoted component."""
    project = Path(tmp) / "product"
    run = project / ".scratch" / "run-1"
    theme = project / "src" / "styles" / "theme.css"
    theme.parent.mkdir(parents=True, exist_ok=True)
    theme.write_text(":root { --color-primary: #2457d6; }\n", encoding="utf-8")
    comp = project / COMPONENT
    comp.parent.mkdir(parents=True, exist_ok=True)
    comp.write_text("export function Button() { return null; }\n",
                    encoding="utf-8")
    page = project / "src" / "pages" / "Settings.tsx"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("export default function Settings() { return null; }\n",
                    encoding="utf-8")
    design_baseline.prepare(project, run)
    binding = design_baseline.confirm(project, run, decision="accept")
    assert binding["status"] == "ready", binding
    return project, run


class ClosedLoopTests(unittest.TestCase):
    def test_distill_to_promote_to_baseline_closed_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _baseline_project(tmp)

            # 1. Distill (T-067): 4 runs / 4 scenes reuse the same component.
            runs = {f"run-{i}": _report(scene) for i, scene in enumerate(
                ["console", "list", "settings", "dashboard"], 1)}
            for run_id, report in runs.items():
                run_dir = project / ".scratch" / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "decision-report.md").write_text(
                    report, encoding="utf-8")
            view = cc.candidate_view(runs)
            self.assertEqual(len(view["qualifying"]), 1)
            cand = view["qualifying"][0]
            self.assertEqual(cand["component"], COMPONENT)
            self.assertTrue(cand["qualifies"])

            # 2. Proposal (T-069) renders it for adjudication, with a slot.
            proposal = cc.render_proposal(
                view, included=sorted(runs), skipped=[])
            self.assertIn("component-distill/v1", proposal)
            self.assertIn(COMPONENT, proposal)
            self.assertIn("[ ] promote", proposal)

            # 3. User adjudicates (T-068): record the promote decision.
            pg.append_event(project / "promotion-governance.jsonl", {
                "id": "evt-dogfood-1", "event": "promotion_decided",
                "decided_by": "user", "confirmed_at": TS, "kind": "component",
                "target": COMPONENT, "decision": "promote",
                "rationale": "recurs across 4 runs / 4 scenes; stable",
            })

            # 4. Promote (T-070): durable incremental merge into DESIGN.md.
            before = (project / "DESIGN.md").read_text(encoding="utf-8")
            result = design_baseline.promote(
                project, run, COMPONENT,
                f"primary-action: {COMPONENT} (promoted from backflow)")
            self.assertEqual(result["status"], "ready")
            after = (project / "DESIGN.md").read_text(encoding="utf-8")

            # Merged incrementally: pre-section content byte-identical.
            self.assertEqual(before.split("## Component Stylings")[0],
                             after.split("## Component Stylings")[0])
            # 5. Closed loop: the promoted path now sits in Component Stylings,
            #    which ui-picker's existing read path collects (no change).
            section = after.split("## Component Stylings")[1]
            self.assertIn(COMPONENT, section)
            # Backup of the prior authority exists (reversible).
            self.assertTrue(
                (run / "design-baseline" / "previous-DESIGN.md").is_file())
            # Verify passes against the promoted baseline (provenance intact).
            verified = design_baseline.verify(project, run)
            self.assertEqual(verified["status"], "ready")
            self.assertEqual(verified["baseline"]["sha256"],
                             design_baseline._sha256(project / "DESIGN.md"))

    def test_no_writeback_without_user_decision(self):
        """The distill/proposal side never touches DESIGN.md on its own."""
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _baseline_project(tmp)
            runs = {f"run-{i}": _report(s) for i, s in enumerate(
                ["a", "b", "c"], 1)}
            view = cc.candidate_view(runs)
            cc.render_proposal(view, included=sorted(runs), skipped=[])
            # No governance event -> promote refuses; DESIGN.md untouched.
            before = (project / "DESIGN.md").read_bytes()
            with self.assertRaises(design_baseline.BaselineError):
                design_baseline.promote(project, run, COMPONENT, "x")
            self.assertEqual((project / "DESIGN.md").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
