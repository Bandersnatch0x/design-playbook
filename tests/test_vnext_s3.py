#!/usr/bin/env python3
"""vNext S3 unit tests: method-semantics keys (five optional manifest keys +
ethics enforcement), interaction-track seven dimensions (objective /
subjective split), five-state x page sampling-matrix enumeration, and the
G8 run-level registry coverage gate.

Issue #38 exit criteria: these hang off the existing CI unit-test step
(same wiring as test_vnext_s1.py / test_vnext_s2.py). Black-box where a
CLI exists (validate_run.py / g8_run_registry.py); in-process for the
parsers and gate functions.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts.g11_coverage import (  # noqa: E402
    check_sampling_matrix,
    spec_matrix_cells,
)
from design_playbook.scripts.g2_g4_pointback import _findings  # noqa: E402
from design_playbook.scripts.g8_run_registry import (  # noqa: E402
    check_g8_run,
    load_registry,
)
from design_playbook.scripts.interaction_dimensions import (  # noqa: E402
    DIMENSIONS,
    JUDGMENT_CLASSES,
    check_dimensions,
    dimension_keys,
)
from design_playbook.scripts.method_semantics import (  # noqa: E402
    HUMAN_SUBJECT_METHODS,
    METHODS,
    check_method_semantics,
    entry_errors,
    parse_method_semantics,
)

P2_RUN = PKG / "examples" / "export-entry" / "run"
P2_POINTBACK = (P2_RUN / "point-back.md").read_text(encoding="utf-8")
P2_SPEC = (P2_RUN / "spec.md").read_text(encoding="utf-8")
P2_CRAFT = (P2_RUN / "craft-guard.md").read_text(encoding="utf-8")
MANIFEST_LINES = [
    json.loads(line)
    for line in (P2_RUN / "evidence" / "manifest.jsonl")
    .read_text(encoding="utf-8").splitlines()
    if line.strip()
]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rules(findings) -> set[str]:
    return {f.rule_id for f in findings}


class MethodSemanticsParseTests(unittest.TestCase):
    def test_nine_value_method_enum(self) -> None:
        self.assertEqual(METHODS, {
            "static-inspection", "runtime-observation", "expert-review",
            "user-test", "interview", "survey", "field-observation",
            "telemetry", "controlled-comparison",
        })
        self.assertEqual(HUMAN_SUBJECT_METHODS, {
            "user-test", "interview", "survey", "field-observation",
        })

    def test_fixture_positive_entries_carry_keys(self) -> None:
        runtime = [
            entry for entry in MANIFEST_LINES
            if entry.get("method") == "runtime-observation"
        ]
        self.assertGreaterEqual(len(runtime), 6)
        for entry in runtime:
            self.assertEqual(entry_errors(entry), [], entry["artifact"])
            semantics = parse_method_semantics(entry)
            self.assertTrue(semantics.observation)
            self.assertTrue(semantics.scope)
            self.assertTrue(semantics.usable)

    def test_fixture_human_subject_negative_is_unusable(self) -> None:
        usertest = [
            entry for entry in MANIFEST_LINES
            if entry.get("method") == "user-test"
        ]
        self.assertEqual(len(usertest), 1)
        semantics = parse_method_semantics(usertest[0])
        # usability is not a structural break: the entry parses clean and
        # is quarantined as blocked evidence instead
        self.assertEqual(entry_errors(usertest[0]), [])
        self.assertFalse(semantics.usable)
        self.assertIn("ethics", semantics.unusable_reason)

    def test_enum_and_key_errors(self) -> None:
        base = {
            "criterion": "L6.1", "artifact": "a.png",
            "method": "runtime-observation",
            "observation": "observed", "interpretation": "reading",
            "scope": "single run",
        }
        self.assertEqual(entry_errors(base), [])
        self.assertTrue(
            any("nine-value enum" in e for e in entry_errors(
                {**base, "method": "vibes"})))
        self.assertTrue(
            any("observation required" in e for e in entry_errors(
                {k: v for k, v in base.items() if k != "observation"})))
        self.assertTrue(
            any("separation" in e for e in entry_errors({
                **base, "observation": "", "interpretation": "reading",
            })))
        self.assertTrue(
            any("method key required" in e for e in entry_errors(
                {k: v for k, v in base.items() if k != "method"})))

    def test_scope_requiredness_follows_the_method(self) -> None:
        runtime = {
            "criterion": "L6.1", "artifact": "a.png",
            "method": "runtime-observation", "observation": "seen",
        }
        self.assertTrue(
            any("scope required" in e for e in entry_errors(runtime)))
        static = {
            "criterion": "L6.1", "artifact": "a.tsx",
            "method": "static-inspection", "observation": "seen",
        }
        self.assertEqual(entry_errors(static), [])

    def test_legacy_entries_without_keys_stay_silent(self) -> None:
        self.assertEqual(
            entry_errors({"criterion": "L6.1", "artifact": "a.png"}), [])


class MethodSemanticsGateTests(unittest.TestCase):
    USERTEST = {
        "criterion": "L6.1", "artifact": "notes.md",
        "method": "user-test", "observation": "2 of 3 looked elsewhere",
        "scope": "one session", "population": "3 operators",
        "ts": "2026-08-14T10:00:00Z",
    }

    def test_pass_resting_on_unusable_evidence_fails(self) -> None:
        entries = [self.USERTEST]
        rows = [("L6.1", "pass", "evidence/notes.md")]
        errs, _warns = check_method_semantics(entries, rows)
        self.assertIn("G6.method_unusable_pass", _rules(errs))

    def test_supplementary_unusable_entry_is_quarantined(self) -> None:
        entries = [self.USERTEST, {
            "criterion": "L6.1", "artifact": "trace.json",
            "method": "runtime-observation", "observation": "done",
            "scope": "single run", "ts": "2026-08-14T11:00:00Z",
        }]
        rows = [("L6.1", "pass", "evidence/trace.json")]
        errs, warns = check_method_semantics(entries, rows)
        self.assertEqual(errs, [])
        self.assertIn("G6.method_unusable_quarantined", _rules(warns))

    def test_structural_errors_surface_through_the_gate(self) -> None:
        entries = [{
            "criterion": "L6.2", "artifact": "b.png", "method": "guessing",
            "observation": "x",
        }]
        errs, _warns = check_method_semantics(entries, [])
        self.assertIn("G6.method_invalid", _rules(errs))

    def test_old_manifest_and_ledger_stay_silent(self) -> None:
        entries = [{"criterion": "L6.1", "artifact": "a.png"}]
        rows = [("L6.1", "pass", "evidence/a.png")]
        self.assertEqual(check_method_semantics(entries, rows), ([], []))


class InteractionDimensionTests(unittest.TestCase):
    def test_seven_dimensions_enumerated_with_both_faces(self) -> None:
        self.assertEqual(dimension_keys(), (
            "discoverability", "system-response", "error-recovery",
            "task-organization", "cross-view-closure",
            "five-state-completeness", "path-closure",
        ))
        for spec in DIMENSIONS.values():
            self.assertTrue(spec.objective)
            self.assertTrue(spec.subjective)

    def test_five_judgment_classes(self) -> None:
        self.assertEqual(set(JUDGMENT_CLASSES), {
            "cognitive-load", "satisfaction", "aesthetics",
            "terminology-fit", "mental-model",
        })

    def test_fixture_annotates_two_dimensions_two_faces(self) -> None:
        annotated = [
            f for f in _findings(P2_POINTBACK)
            if f.get("dimension")
        ]
        self.assertEqual(len(annotated), 2)
        faces = {f["face"][0] for f in annotated}
        self.assertEqual(faces, {"objective", "subjective"})
        by_face = {f["face"][0]: f for f in annotated}
        self.assertEqual(
            by_face["objective"]["dimension"], ["system-response"])
        self.assertEqual(
            by_face["subjective"]["dimension"], ["task-organization"])
        self.assertEqual(
            by_face["subjective"]["basis"], ["agent-judgment"])
        self.assertEqual(_rules(check_dimensions(P2_POINTBACK)), set())

    def _probe(self, **extra: str) -> set[str]:
        block = (
            "issue:    probe\n"
            "source:   spec\n"
            "fix:      fix\n"
            "severity: S2\n"
            + "".join(f"{key}: {value}\n" for key, value in extra.items())
        )
        text = ("# pb\n\n## Findings\n\n```text\n" + block
                + "```\n\n## Verdict\n\n**Recirculate.**\n")
        return _rules(check_dimensions(text))

    def test_unknown_dimension_rejected(self) -> None:
        self.assertIn(
            "G2.dim_unknown",
            self._probe(track="interaction", dimension="pacing"))

    def test_subjective_face_never_blocks(self) -> None:
        self.assertIn("G2.dim_subjective_blocking", self._probe(
            track="interaction", dimension="task-organization",
            face="subjective", basis="agent-judgment",
            confidence="low", disposition="blocking"))

    def test_subjective_face_requires_a_judgment_source(self) -> None:
        self.assertIn("G2.dim_basis_missing", self._probe(
            track="interaction", dimension="aesthetics-face",
            face="subjective", disposition="advisory"))

    def test_agent_judgment_derives_low_confidence(self) -> None:
        self.assertIn("G2.dim_basis_confidence", self._probe(
            track="interaction", dimension="task-organization",
            face="subjective", basis="agent-judgment",
            confidence="high", disposition="advisory"))

    def test_dimension_belongs_to_the_interaction_track(self) -> None:
        self.assertIn("G2.dim_track_mismatch", self._probe(
            track="cross-cutting", dimension="system-response",
            face="objective"))

    def test_face_and_basis_enums(self) -> None:
        self.assertIn("G2.dim_face_invalid", self._probe(
            track="interaction", dimension="system-response",
            face="both-sides"))
        self.assertIn("G2.dim_face_orphan", self._probe(
            track="interaction", face="objective"))
        self.assertIn("G2.dim_basis_invalid", self._probe(
            track="interaction", dimension="system-response",
            face="objective", basis="gut-feeling"))

    def test_unannotated_findings_untouched(self) -> None:
        text = ("# pb\n\n## Findings\n\n```text\nissue: a\nsource: s\n"
                "fix: f\nseverity: S1\n```\n\n## Verdict\n\n"
                "**Recirculate.**\n")
        self.assertEqual(check_dimensions(text), [])


class SamplingMatrixTests(unittest.TestCase):
    def test_spec_cells_enumerated(self) -> None:
        self.assertEqual(spec_matrix_cells(P2_SPEC), [
            ("main-list", "initial"), ("main-list", "loading"),
            ("main-list", "success"), ("main-list", "failure"),
            ("main-list", "empty"), ("export-dialog", "initial"),
            ("export-dialog", "loading"), ("export-dialog", "success"),
            ("export-dialog", "failure"), ("export-dialog", "empty"),
        ])

    def test_fixture_matrix_is_complete(self) -> None:
        self.assertEqual(
            check_sampling_matrix(
                P2_POINTBACK, P2_SPEC, P2_RUN / "evidence"),
            [])

    def test_gap_is_machine_enumerable(self) -> None:
        broken = P2_POINTBACK.replace(
            "- main-list/loading: 未审（骨架态未单独采集——高频低风险，R2 待补采样）\n",
            "")
        rules = _rules(check_sampling_matrix(broken, P2_SPEC))
        self.assertIn("G11.matrix_gap", rules)

    def test_unknown_cell_rejected(self) -> None:
        broken = P2_POINTBACK.replace(
            "- main-list/loading: 未审（骨架态未单独采集——高频低风险，R2 待补采样）",
            "- main-list/loaded: 未审（typo state）")
        self.assertIn(
            "G11.matrix_unknown_cell",
            _rules(check_sampling_matrix(broken, P2_SPEC)))

    def test_unreviewed_cell_needs_a_reason(self) -> None:
        broken = P2_POINTBACK.replace(
            "- main-list/loading: 未审（骨架态未单独采集——高频低风险，R2 待补采样）",
            "- main-list/loading: 未审")
        self.assertIn(
            "G11.matrix_unreviewed_reason",
            _rules(check_sampling_matrix(broken, P2_SPEC)))

    def test_blank_and_missing_values_rejected(self) -> None:
        blank = P2_POINTBACK.replace(
            "- main-list/success: evidence/L6.1-export-trace.json（行选择 + 导出入口可用）",
            "- main-list/success:")
        self.assertIn(
            "G11.matrix_blank", _rules(check_sampling_matrix(blank, P2_SPEC)))
        missing = P2_POINTBACK.replace(
            "- main-list/failure: evidence/edge-timeout.png（超时中断采样通过）",
            "- main-list/failure: evidence/gone.png（missing artifact）")
        self.assertIn(
            "G11.matrix_artifact_missing",
            _rules(check_sampling_matrix(
                missing, P2_SPEC, P2_RUN / "evidence")))

    def test_duplicate_cell_rejected(self) -> None:
        duplicated = P2_POINTBACK.replace(
            "未审: 移动端视口",
            "- main-list/initial: evidence/L6.1-export-trace.json（dup）\n"
            "未审: 移动端视口")
        self.assertIn(
            "G11.matrix_duplicate",
            _rules(check_sampling_matrix(duplicated, P2_SPEC)))

    def test_matrix_less_reports_do_not_trigger(self) -> None:
        legacy = "# pb\n\n## Coverage statement\n\n必审: done\n未审: none\n"
        self.assertEqual(check_sampling_matrix(legacy, P2_SPEC), [])

    def test_matrix_without_spec_declaration_fails(self) -> None:
        legacy_spec = ("# spec\n\n## L1\n- a\n\n## L2\n- b\n\n## L3\n- c\n"
                       "\n## L4\n- d\n\n## L5\n- e\n\n## L6\n"
                       "- Given a When b Then c\n")
        self.assertIn(
            "G11.matrix_no_spec",
            _rules(check_sampling_matrix(P2_POINTBACK, legacy_spec)))


class G8RunRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entries, _ = load_registry()

    def test_fixture_full_evaluation_passes(self) -> None:
        self.assertEqual(check_g8_run(P2_CRAFT, self.entries, "P2"), [])
        self.assertEqual(check_g8_run(P2_CRAFT, self.entries, "P3"), [])

    def test_missing_row_detected_under_full_tiers(self) -> None:
        broken = P2_CRAFT.replace(
            "| I18N-01@1 | not-applicable | 单语控制台，无 i18n 声明（无 i18n.* 契约字段，L1 未声明多语言用户群） | - | - | - | 单语声明成立 | - |",
            "")
        for tier in ("P2", "P3"):
            self.assertIn(
                "G8.run_missing_row",
                _rules(check_g8_run(broken, self.entries, tier)))

    def test_p1_subset_and_legacy_runs_stay_free(self) -> None:
        broken = P2_CRAFT.replace(
            "| I18N-01@1 | not-applicable | 单语控制台，无 i18n 声明（无 i18n.* 契约字段，L1 未声明多语言用户群） | - | - | - | 单语声明成立 | - |",
            "")
        self.assertEqual(_rules(check_g8_run(broken, self.entries, "P1")), set())
        self.assertEqual(
            _rules(check_g8_run(broken, self.entries, None)), set())

    def test_duplicate_row_detected(self) -> None:
        line = next(
            line for line in P2_CRAFT.splitlines()
            if line.startswith("| SEC-01@1 |"))
        self.assertIn(
            "G8.run_duplicate_row",
            _rules(check_g8_run(P2_CRAFT + line + "\n", self.entries, "P2")))

    def test_row_level_registry_drift_detected(self) -> None:
        broken = P2_CRAFT.replace("| CRAFT-01@1 |", "| CRAFT-01@9 |")
        self.assertIn(
            "G8.run_row", _rules(check_g8_run(broken, self.entries, "P2")))

    def test_cli_on_fixture_run(self) -> None:
        import os

        env = dict(os.environ)
        env["PYTHONPATH"] = str(PKG) + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable,
             str(PKG / "scripts" / "g8_run_registry.py"),
             str(P2_RUN / "craft-guard.md")],
            capture_output=True, text=True, check=False, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("G8 OK", result.stdout)


class FixtureWalkthroughTests(unittest.TestCase):
    """Issue #38: the extended fixture run demonstrates every S3 face."""

    def _validate(self, run_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(PKG / "scripts" / "validate_run.py"),
                str(run_dir / "spec.md"),
                str(run_dir / "point-back.md"),
                "--evidence-dir", str(run_dir / "evidence"),
                "--run-root", str(run_dir),
                "--contract-project", str(run_dir.parent / "project"),
                "--contract-run", str(run_dir),
                "--shaping-dir", str(run_dir / "shaping"),
                *extra,
            ],
            capture_output=True, text=True, check=False,
        )

    def test_full_chain_still_reaches_pass(self) -> None:
        result = self._validate(P2_RUN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)
        # the human-subject negative is quarantined, not failing the run
        self.assertIn("quarantined", result.stdout)

    def test_unusable_pass_basis_breaks_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            shutil.copytree(P2_RUN, run)
            pb = (run / "point-back.md").read_text(encoding="utf-8")
            pb = pb.replace(
                "observed:  evidence/L6.1-export-trace.json 14.2s 完成，214/214 行；单次触发（R4 修复后 busy 态防重复）",
                "observed:  evidence/L6.1-usertest-notes.md（涉人证据 ethics 缺失）")
            _write(run / "point-back.md", pb)
            result = self._validate(run)
            self.assertEqual(result.returncode, 1)
            self.assertIn("G6 method", result.stdout)
            self.assertIn("unusable", result.stdout)

    def test_matrix_gap_breaks_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            shutil.copytree(P2_RUN, run)
            pb = (run / "point-back.md").read_text(encoding="utf-8")
            pb = pb.replace(
                "- export-dialog/empty: 未审（无选择时入口禁用、面板不打开——无采集面）\n",
                "")
            _write(run / "point-back.md", pb)
            result = self._validate(run)
            self.assertEqual(result.returncode, 1)
            self.assertIn("sampling-matrix gap", result.stdout)
            self.assertIn("export-dialog/empty", result.stdout)

    def test_g8_missing_row_breaks_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            shutil.copytree(P2_RUN, run)
            craft = (run / "craft-guard.md").read_text(encoding="utf-8")
            craft = "\n".join(
                line for line in craft.splitlines()
                if not line.startswith("| RESP-01@1 |")) + "\n"
            _write(run / "craft-guard.md", craft)
            result = self._validate(run)
            self.assertEqual(result.returncode, 1)
            self.assertIn("G8 run", result.stdout)
            self.assertIn("RESP-01", result.stdout)

    def test_subjective_blocking_annotation_breaks_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            shutil.copytree(P2_RUN, run)
            pb = (run / "point-back.md").read_text(encoding="utf-8")
            pb = pb.replace(
                "severity: S2\ntrack:    interaction\ndimension: task-organization",
                "severity: S3\ntrack:    interaction\ndimension: task-organization")
            pb = pb.replace(
                "basis:    agent-judgment\nconfidence: low\ndisposition: advisory\nevidence:  rendered 走查",
                "basis:    agent-judgment\nconfidence: low\ndisposition: blocking\nevidence:  rendered 走查")
            _write(run / "point-back.md", pb)
            result = self._validate(run)
            self.assertEqual(result.returncode, 1)
            self.assertIn("subjective-face", result.stdout)


if __name__ == "__main__":
    unittest.main()
