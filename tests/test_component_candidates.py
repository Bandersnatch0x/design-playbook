#!/usr/bin/env python3
"""T-067 unit tests: component backflow candidate derivation.

Threshold positive/negative, gap visibility for below-threshold signals,
``new`` never entering candidacy, ``extend`` counting as reuse, scene parsing,
and the report-only no-writeback guarantee. Black-box over the public
functions; report fixtures are built inline (no file paths under test).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts import component_candidates as cc  # noqa: E402


def _report(scene: str, components_lines: list[str]) -> str:
    body = "\n".join(
        [f"scene: {scene}", "density: console-tight", "components:"]
        + [f"  {line}" for line in components_lines])
    return f"# Decision report\n\n```text\n{body}\n```\n"


def _inline_report(scene: str, components_value: str) -> str:
    return ("# Decision report\n\n```text\n"
            f"scene: {scene}\ncomponents: {components_value}\n```\n")


class ParseTests(unittest.TestCase):
    def test_reuse_and_extend_yield_references_with_path(self):
        refs = cc.parse_component_references(
            _report("ops console", [
                "primary-action -> reuse src/ui/Button.tsx (matches primary)",
                "status -> extend src/ui/Badge.tsx (needs warning state)",
            ]), run="run-1")
        by_role = {ref.role: ref for ref in refs}
        self.assertEqual(by_role["primary-action"].path, "src/ui/Button.tsx")
        self.assertEqual(by_role["primary-action"].action, "reuse")
        self.assertEqual(by_role["status"].action, "extend")
        self.assertEqual(by_role["primary-action"].scene, "ops console")

    def test_new_records_no_candidate(self):
        refs = cc.parse_component_references(
            _report("settings", [
                "empty-state -> new (no declared candidate)",
                "primary-action -> reuse src/ui/Button.tsx (ok)",
            ]), run="run-1")
        self.assertEqual([r.path for r in refs], ["src/ui/Button.tsx"])

    def test_inline_comma_and_semicolon_forms_parse(self):
        text = _inline_report(
            "dashboard",
            "primary-action -> reuse src/ui/Button.tsx (ok); "
            "status -> extend src/ui/Badge.tsx (warn)")
        refs = cc.parse_component_references(text, run="run-1")
        self.assertEqual(
            {r.path for r in refs},
            {"src/ui/Button.tsx", "src/ui/Badge.tsx"})

    def test_unfenced_fill_face_is_parsed_before_dd_entries(self):
        text = ("# Decision report\n\nscene: list（dense operations table）\n"
                "components:\n"
                "  primary-action -> reuse src/ui/Button.tsx (ok)\n\n"
                "## DD-001\n\n```yaml\ncomponents: forged\n```\n")
        refs = cc.parse_component_references(text, run="run-1")
        self.assertEqual([ref.path for ref in refs], ["src/ui/Button.tsx"])

    def test_no_components_yields_no_references(self):
        self.assertEqual(
            cc.parse_component_references("no block here", run="run-1"), [])

    def test_prose_reuse_target_is_not_a_component_path(self):
        refs = cc.parse_component_references(
            _report("list", [
                "action-text -> reuse 无组件(纯文本单元格,category...)"
            ]), run="run-1")
        self.assertEqual(refs, [])

    def test_reference_without_path_is_dropped(self):
        refs = cc.parse_component_references(
            _report("list", ["primary-action -> reuse"]), run="run-1")
        self.assertEqual(refs, [])


class DeriveTests(unittest.TestCase):
    def _refs(self, path, runs, scenes):
        return [cc.ComponentReference(
            run=run, role="primary-action", action="reuse",
            path=path, scene=scene) for run, scene in zip(runs, scenes)]

    def test_qualifies_at_threshold(self):
        refs = self._refs("src/ui/Button.tsx",
                          ["r1", "r2", "r3"],
                          ["console", "list", "settings"])
        (cand,) = cc.derive_candidates(refs)
        self.assertTrue(cand.qualifies)
        self.assertEqual(cand.distinct_runs, 3)
        self.assertEqual(cand.distinct_scenes, 3)
        self.assertEqual(cand.recurrence, 3)
        self.assertEqual(cand.gaps, [])
        self.assertEqual(cand.kind, "component")

    def test_below_threshold_reports_run_gap(self):
        refs = self._refs("src/ui/Button.tsx", ["r1", "r2"],
                          ["console", "list"])
        (cand,) = cc.derive_candidates(refs)
        self.assertFalse(cand.qualifies)
        self.assertTrue(any("distinct_runs" in g for g in cand.gaps))

    def test_scene_explanations_do_not_inflate_distinct_scene_count(self):
        refs = self._refs("src/ui/Button.tsx", ["r1", "r2", "r3"],
                          ["list（table）", "list（cards）", "dashboard(chart)"])
        (cand,) = cc.derive_candidates(refs)
        self.assertEqual(cand.distinct_scenes, 2)

    def test_below_threshold_reports_scene_gap(self):
        refs = self._refs("src/ui/Button.tsx", ["r1", "r2", "r3"],
                          ["console", "console", "console"])
        (cand,) = cc.derive_candidates(refs)
        self.assertFalse(cand.qualifies)
        self.assertTrue(any("distinct_scenes" in g for g in cand.gaps))

    def test_unspecified_scene_counts_conservatively(self):
        refs = self._refs("src/ui/Button.tsx", ["r1", "r2", "r3"],
                          ["", "", ""])
        (cand,) = cc.derive_candidates(refs)
        self.assertFalse(cand.qualifies)
        self.assertTrue(any("distinct_scenes" in g for g in cand.gaps))

    def test_qualifying_sorted_first(self):
        refs = (self._refs("src/ui/A.tsx", ["r1", "r2"], ["a", "b"])
                + self._refs("src/ui/B.tsx", ["r1", "r2", "r3"], ["a", "b", "c"]))
        cands = cc.derive_candidates(refs)
        self.assertTrue(cands[0].qualifies)
        self.assertEqual(cands[0].component, "src/ui/B.tsx")
        self.assertFalse(cands[1].qualifies)


class ViewTests(unittest.TestCase):
    def test_view_shape_and_report_only_no_writeback(self):
        reports = {
            f"run-{i}": _report(scene, ["primary-action -> reuse src/ui/Button.tsx (ok)"])
            for i, scene in enumerate(
                ["console", "list", "settings", "dashboard"], 1)
        }
        before = dict(reports)
        view = cc.candidate_view(reports)
        self.assertEqual(reports, before)  # derivation mutates nothing
        self.assertEqual(view["threshold"]["distinct_runs"], 3)
        self.assertEqual(view["threshold"]["distinct_scenes"], 2)
        self.assertEqual(view["reference_coverage"]["runs_with_components"], 4)
        self.assertEqual(len(view["qualifying"]), 1)
        self.assertEqual(
            view["qualifying"][0]["component"], "src/ui/Button.tsx")
        self.assertTrue(view["qualifying"][0]["qualifies"])

    def test_empty_corpus_reports_coverage_not_silence(self):
        view = cc.candidate_view({})
        self.assertEqual(view["qualifying"], [])
        self.assertEqual(view["below_threshold"], [])
        self.assertEqual(view["reference_coverage"]["total_references"], 0)

    def test_below_threshold_kept_when_approaching(self):
        reports = {
            "r1": _report("console", ["primary-action -> reuse src/ui/Card.tsx (ok)"]),
            "r2": _report("list", ["primary-action -> reuse src/ui/Card.tsx (ok)"]),
        }
        view = cc.candidate_view(reports)
        self.assertEqual(view["qualifying"], [])
        self.assertEqual(len(view["below_threshold"]), 1)
        self.assertEqual(
            view["below_threshold"][0]["component"], "src/ui/Card.tsx")
        self.assertTrue(view["below_threshold"][0]["gaps"])

    def test_single_run_signal_reported_not_dropped(self):
        """P4: a 1-run signal appears in below_threshold with its gap, never
        silently filtered (spec D4 / US-20)."""
        reports = {
            "r1": _report("console", ["primary-action -> reuse src/ui/Chip.tsx (ok)"]),
        }
        view = cc.candidate_view(reports)
        self.assertEqual(view["qualifying"], [])
        self.assertEqual(len(view["below_threshold"]), 1)
        gaps = view["below_threshold"][0]["gaps"]
        self.assertTrue(any("distinct_runs 1 < 3" in g for g in gaps))

    def test_evidence_json_is_a_second_input_leg(self):
        """P1: a component observed in a run's evidence.json but absent from its
        decision report still counts as a reference toward candidacy."""
        # 2 reports reuse the component; a 3rd run only *observes* it in
        # evidence.json (no components: line). Without the evidence leg this
        # reaches 2 runs; with it, 3 -> qualifies.
        reports = {
            "r1": _report("console", ["primary-action -> reuse src/ui/Button.tsx (ok)"]),
            "r2": _report("list", ["primary-action -> reuse src/ui/Button.tsx (ok)"]),
            "r3": _report("settings", ["status -> new (no candidate)"]),
        }
        evidence = {
            "r3": {"sources": [{"path": "src/ui/Button.tsx", "sha256": "ab" * 32}],
                   "components": ["src/ui/Button.tsx"]},
        }
        no_leg = cc.candidate_view(reports)
        with_leg = cc.candidate_view(reports, evidence_by_run=evidence)
        self.assertEqual(len(no_leg["qualifying"]), 0)
        self.assertEqual(len(with_leg["qualifying"]), 1)
        self.assertEqual(with_leg["qualifying"][0]["distinct_runs"], 3)

    def test_evidence_prose_value_is_filtered(self):
        reports = {"r1": _report("console", ["status -> new (gap)"])}
        evidence = {"r1": {"components": [
            "无组件(纯文本单元格,category...)", "src/ui/Button.tsx"]}}
        view = cc.candidate_view(reports, evidence_by_run=evidence)
        self.assertEqual(
            [item["component"] for item in view["below_threshold"]],
            ["src/ui/Button.tsx"])

    def test_candidate_carries_source_sha256_provenance(self):
        """P2: with a project_root, a candidate resolves its on-disk source
        SHA-256 (provenance, US-2); without it, source_sha256 is None."""
        import hashlib
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src" / "ui" / "Button.tsx"
            src.parent.mkdir(parents=True)
            src.write_text("export function Button(){return null;}\n")
            expected = hashlib.sha256(src.read_bytes()).hexdigest()
            reports = {f"r{i}": _report(s, [
                "primary-action -> reuse src/ui/Button.tsx (ok)"])
                for i, s in enumerate(["console", "list", "settings"], 1)}
            view = cc.candidate_view(reports, project_root=tmp)
            self.assertEqual(view["qualifying"][0]["source_sha256"], expected)
            no_root = cc.candidate_view(reports)
            self.assertIsNone(no_root["qualifying"][0]["source_sha256"])


class RenderTests(unittest.TestCase):
    def test_proposal_header_and_decision_slot(self):
        reports = {
            f"run-{i}": _report(scene, ["primary-action -> reuse src/ui/Button.tsx (ok)"])
            for i, scene in enumerate(["console", "list", "settings"], 1)
        }
        view = cc.candidate_view(reports)
        text = cc.render_proposal(
            view, included=sorted(reports), skipped=[("run-x", "no report")])
        self.assertIn("component-distill/v1", text)
        self.assertIn("src/ui/Button.tsx", text)
        self.assertIn("[ ] promote", text)
        self.assertIn("run-x | skipped — no report", text)
        self.assertIn("never writes", text)

    def test_empty_proposal_is_visible_not_silent(self):
        view = cc.candidate_view({})
        text = cc.render_proposal(view, included=[], skipped=[])
        self.assertIn("_none_", text)
        self.assertIn("total_references: 0", text)


if __name__ == "__main__":
    unittest.main()
