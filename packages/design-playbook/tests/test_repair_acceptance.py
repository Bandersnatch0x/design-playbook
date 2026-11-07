#!/usr/bin/env python3
"""T-159 phase B: complete CLI acceptance for repaired-blocker evidence.

The executable fixture is a real project/run copied from the export-upgrade
example and bound through the baseline owner's prepare/confirm. Its closed
blocking finding is a visible-state repair: the spec declares a screenshot
criterion, the finding names it, the manifest binds two real decodable PNGs
with their real SHA-256 digests, and the closure carries the named pair.

The red cases mutate that one fixture so the old validator would wrongly pass:
a deleted annotation, an unknown criterion, a fabricated digest, a borrowed
pair, and so on. Every case runs the real subprocess CLI except the explicitly
in-process snapshot cases, which prove the projection never re-reads a file.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from tests.test_baseline_acceptance import _bind, _locate  # noqa: E402

from design_playbook.mcp.evidence import containment  # noqa: E402
from design_playbook.scripts import run_facts as run_facts_module  # noqa: E402
from design_playbook.scripts import g6_records  # noqa: E402
from design_playbook.scripts.g6_evidence import (  # noqa: E402
    EvidenceReference,
    validate_references,
)
from design_playbook.scripts.g6_records import EvidenceArtifactFact  # noqa: E402
from design_playbook.scripts.run_facts import (  # noqa: E402
    BaselineCapture,
    capture_run_facts,
)
from design_playbook.scripts.validate_run import (  # noqa: E402
    RunInputs,
    run as validate_run_policy,
)

VALIDATOR = PACKAGE / "scripts" / "validate_run.py"

# Two real, decodable 1x1 PNGs with different bytes (red / blue).
BEFORE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg==")
AFTER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwAD"
    "hgGAWjR9awAAAABJRU5ErkJggg==")

VIEWPORT = {
    "width": 1280, "height": 800,
    "devicePixelRatio": 1.0, "colorScheme": "light",
}
FREEZE = {"enabled": True, "waitFonts": True, "networkIdle": False}
CRITERION = "L6.2"
FINDING_ISSUE = "切页返回后全局状态区清空，导出结果不可获知"
BEFORE_TOKEN = "evidence/L6.2-empty-r1.png"
AFTER_TOKEN = "evidence/L6.2-empty-r2.png"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture(tmp: Path) -> tuple[Path, Path]:
    """Copy the example into owner containment and bind a real baseline."""
    project, run = _locate(tmp)
    _bind(project, run)
    return project, run


def _rewrite_spec(run: Path) -> None:
    spec = run / "spec.md"
    text = spec.read_text(encoding="utf-8")
    text = text.replace(
        "  - Required evidence: interaction_trace; viewport=1280x800",
        "  - Required evidence: screenshot; state=empty; viewport=1280x800",
    )
    spec.write_text(text, encoding="utf-8")


def _rewrite_pointback(run: Path) -> None:
    pointback = run / "point-back.md"
    text = pointback.read_text(encoding="utf-8")
    text = text.replace(
        "evidence:  evidence/L6.2-return-first.json（首轮返回后状态区为空）",
        f"evidence:  {BEFORE_TOKEN}（首轮返回后状态区为空）",
    )
    text = text.replace(
        "observed:  evidence/L6.2-return-trace.json 返回后条目恢复显示；"
        "完成态含结果入口（r2 重采）",
        f"observed:  {AFTER_TOKEN} 返回后条目恢复显示；完成态含结果入口（r2 重采）",
    )
    text = text.replace(
        "  repair-evidence: criterion=L6.2 "
        "before=evidence/L6.2-return-first.json "
        "after=evidence/L6.2-return-trace.json",
        f"  repair-evidence: criterion={CRITERION} before={BEFORE_TOKEN} "
        f"after={AFTER_TOKEN}",
    )
    pointback.write_text(text, encoding="utf-8")


def _capture_entry(artifact: str, state: str, data: bytes) -> dict:
    return {
        "criterion": CRITERION,
        "capture": {
            "type": "screenshot",
            "state": state,
            "artifact_path": f"evidence/{artifact}",
        },
        "artifact": artifact,
        "observed_state": state,
        "result": "captured",
        "ts": "2026-08-14T11:51:00Z" if state == "empty-failure"
              else "2026-08-14T11:52:00Z",
        "request": {
            "schemaVersion": 1,
            "viewport": dict(VIEWPORT),
            "freeze": dict(FREEZE),
        },
        "sha256": _digest(data),
    }


def _rewrite_manifest(run: Path, *, before_sha: str | None = None,
                      after_sha: str | None = None,
                      before_bytes: bytes = BEFORE_PNG,
                      after_bytes: bytes = AFTER_PNG) -> None:
    evidence = run / "evidence"
    (evidence / "L6.2-empty-r1.png").write_bytes(before_bytes)
    (evidence / "L6.2-empty-r2.png").write_bytes(after_bytes)
    lines = [
        json.loads(line) for line in
        (evidence / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lines = [entry for entry in lines
             if not (entry.get("criterion") == CRITERION
                     and entry.get("artifact") in (
                         "L6.2-return-first.json", "L6.2-return-trace.json"))]
    before = _capture_entry("L6.2-empty-r1.png", "empty-failure", before_bytes)
    after = _capture_entry("L6.2-empty-r2.png", "empty-repaired", after_bytes)
    if before_sha is not None:
        before["sha256"] = before_sha
    if after_sha is not None:
        after["sha256"] = after_sha
    lines.extend((before, after))
    (evidence / "manifest.jsonl").write_text(
        "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in lines),
        encoding="utf-8")


def _prepare(tmp: Path, **manifest_changes) -> tuple[Path, Path]:
    project, run = _fixture(tmp)
    _rewrite_spec(run)
    _rewrite_pointback(run)
    _rewrite_manifest(run, **manifest_changes)
    return project, run


def _validate(run: Path, *extra: str,
              project: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(VALIDATOR),
        str(run / "spec.md"),
        str(run / "point-back.md"),
        "--preview-dir", str(run / "preview"),
        "--decision-report", str(run / "decision-report.md"),
        "--evidence-dir", str(run / "evidence"),
        "--shaping-dir", str(run / "shaping"),
        "--run-root", str(run),
        "--contract-run", str(run),
    ]
    if project is not None:
        command.extend(["--contract-project", str(project)])
    command.extend(extra)
    return subprocess.run(
        command, capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    )


def _rules(result: subprocess.CompletedProcess[str]) -> set[str]:
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return set()
    return {
        item.get("rule_id") for item in payload
        if isinstance(item, dict) and item.get("rule_id")
    }


def _mutate(run: Path, *, pointback: str | None = None,
            spec: str | None = None) -> None:
    if pointback is not None:
        path = run / "point-back.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            f"  repair-evidence: criterion={CRITERION} before={BEFORE_TOKEN} "
            f"after={AFTER_TOKEN}\n", pointback),
            encoding="utf-8")
    if spec is not None:
        path = run / "spec.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "  - Required evidence: screenshot; state=empty; viewport=1280x800",
            spec), encoding="utf-8")


class CompleteAcceptanceCliTests(unittest.TestCase):
    def test_bare_and_strict_accept_the_visual_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _prepare(Path(tmp))

            bare = _validate(run, project=project)
            strict = _validate(run, "--strict", project=project)

            self.assertEqual(bare.returncode, 0, bare.stdout + bare.stderr)
            self.assertIn("RUN OK", bare.stdout)
            self.assertEqual(strict.returncode, 0, strict.stdout + strict.stderr)
            self.assertIn("RUN OK", strict.stdout)

    def test_deleting_the_whole_annotation_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            _mutate(run, pointback="")

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G4.repair_evidence_missing", _rules(result))
            self.assertNotIn("RUN OK", result.stdout)

    def test_only_the_repaired_half_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            _mutate(run, pointback=(
                f"  repair-evidence: criterion={CRITERION} "
                f"after={AFTER_TOKEN}\n"))

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G4.repair_evidence_unpaired", _rules(result))

    def test_an_unknown_criterion_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            path = run / "point-back.md"
            path.write_text(path.read_text(encoding="utf-8").replace(
                f"criteria: {CRITERION}", "criteria: L6.99"),
                encoding="utf-8")

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G4.repair_requirement_unavailable", _rules(result))

    def test_an_unknown_proof_type_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            _mutate(run, spec="  - Required evidence: screenshot-ish\n")

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G4.repair_requirement_unavailable", _rules(result))

    def test_a_fabricated_digest_is_blocked_even_when_the_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp), after_sha="f" * 64)

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G6.artifact_hash_mismatch", _rules(result))

    def test_a_pair_borrowed_from_another_criterion_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            # A real, bound L6.1 artifact that is not this finding's evidence.
            _mutate(run, pointback=(
                f"  repair-evidence: criterion={CRITERION} "
                "before=evidence/L6.1-status-trace.json "
                f"after={AFTER_TOKEN}\n"))

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G4.repair_evidence_before", _rules(result))

    def test_after_must_be_the_current_ledger_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            _mutate(run, pointback=(
                f"  repair-evidence: criterion={CRITERION} before={BEFORE_TOKEN} "
                f"after={BEFORE_TOKEN}\n"))

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G4.repair_evidence_after", _rules(result))

    def test_a_failing_retest_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            path = run / "point-back.md"
            text = path.read_text(encoding="utf-8")
            start = text.index("criterion: L6.2")
            end = text.index("\n\n", start)
            block = text[start:end]
            self.assertIn("result:    pass", block)
            path.write_text(
                text[:start]
                + block.replace("result:    pass", "result:    fail", 1)
                + text[end:],
                encoding="utf-8")

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G4.repair_evidence_result", _rules(result))

    def test_identical_visual_bytes_are_insufficient_not_a_functional_failure(
            self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _fixture(Path(tmp))
            _rewrite_spec(run)
            _rewrite_pointback(run)
            _rewrite_manifest(run, before_bytes=BEFORE_PNG, after_bytes=BEFORE_PNG)

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G4.repair_evidence_unchanged", _rules(result))
            message = next(
                item["message"] for item in json.loads(result.stdout)
                if item.get("rule_id") == "G4.repair_evidence_unchanged")
            self.assertIn("insufficient to demonstrate", message)
            self.assertNotIn("still fails", message)

    def test_a_path_escape_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            _mutate(run, pointback=(
                f"  repair-evidence: criterion={CRITERION} "
                f"before=evidence/../spec.md after={AFTER_TOKEN}\n"))

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G6.escape", _rules(result))

    def test_a_deleted_artifact_is_blocked_with_the_missing_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            (run / "evidence" / "L6.2-empty-r1.png").unlink()

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G6.artifact_missing", _rules(result))

    def test_a_leaf_only_reference_is_rejected_with_a_migration_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            _mutate(run, pointback=(
                f"  repair-evidence: criterion={CRITERION} "
                f"before=L6.2-empty-r1.png after={AFTER_TOKEN}\n"))

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G6.reference_prefix", _rules(result))

    def test_a_mixed_known_unknown_criterion_stays_named_json(self) -> None:
        # F1: an association loop must never index a criterion whose proof
        # requirement is unavailable; the run still returns the named
        # requirement diagnostic as structured JSON.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _prepare(Path(tmp))
            path = run / "point-back.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                f"criteria: {CRITERION}", f"criteria: {CRITERION}, L6.3", 1)
            text = text.replace("criterion=L6.2 ", "criterion=L6.3 ", 1)
            path.write_text(text, encoding="utf-8")

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            rules = _rules(result)
            self.assertIn("G4.repair_requirement_unavailable", rules)
            self.assertIn("G4.repair_evidence_missing", rules)

    def test_visual_before_must_carry_the_declared_capture_type(self) -> None:
        # F2: both visible-state halves carry the declared proof; a missing or
        # wrong before capture type cannot ride the after's valid binding.
        for label, mutate in (
            ("wrong type",
             lambda before: before["capture"].__setitem__(
                 "type", "interaction trace")),
            ("missing metadata", lambda before: before.pop("capture", None)),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                project, run = _prepare(Path(tmp))
                rows = _manifest_rows(run)
                before = next(
                    row for row in rows
                    if row.get("artifact") == "L6.2-empty-r1.png")
                mutate(before)
                _write_manifest_rows(run, rows)

                result = _validate(run, "--format", "json", project=project)

                self.assertEqual(
                    result.returncode, 1, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn("G6.proof_type", _rules(result))

    def test_nonvisual_retest_must_match_the_declared_viewport(self) -> None:
        # F3: a captured retest keeps the criterion's declared viewport even
        # when no screenshot pair is required.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _prepare(Path(tmp))
            spec = run / "spec.md"
            spec.write_text(spec.read_text(encoding="utf-8").replace(
                "  - Required evidence: screenshot; state=empty; "
                "viewport=1280x800",
                "  - Required evidence: interaction_trace; state=empty; "
                "viewport=1280x800"), encoding="utf-8")
            path = run / "point-back.md"
            path.write_text("\n".join(
                line for line in path.read_text(encoding="utf-8").splitlines()
                if not line.strip().startswith("repair-evidence:")) + "\n",
                encoding="utf-8")
            rows = _manifest_rows(run)
            after = next(
                row for row in rows
                if row.get("artifact") == "L6.2-empty-r2.png")
            after["capture"]["type"] = "interaction trace"
            after["request"]["viewport"]["width"] = 320
            after["request"]["viewport"]["height"] = 200
            _write_manifest_rows(run, rows)

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("G4.repair_evidence_mismatch", _rules(result))


def _manifest_rows(run: Path) -> list[dict]:
    path = run / "evidence" / "manifest.jsonl"
    return [
        json.loads(line) for line in path.read_text(
            encoding="utf-8").splitlines() if line.strip()
    ]


def _write_manifest_rows(run: Path, rows: list[dict]) -> None:
    (run / "evidence" / "manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8")


class ModeScopeTests(unittest.TestCase):
    def test_legacy_does_not_derive_the_new_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            _mutate(run, pointback="")

            result = _validate(run, "--legacy")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("RUN OK", result.stdout)

    def test_selective_require_flags_do_not_derive_the_new_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            _mutate(run, pointback="")

            result = _validate(
                run, "--require-evidence", "--require-coverage")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_three_explicit_require_flags_stay_structural(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            _mutate(run, pointback="")

            result = _validate(
                run, "--require-preview", "--require-evidence",
                "--require-coverage")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_still_rejects_a_fabricated_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp), after_sha="e" * 64)

            result = _validate(run, "--legacy", "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G6.artifact_hash_mismatch", _rules(result))

    def test_in_process_default_keeps_the_structural_reading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _prepare(Path(tmp))
            _mutate(run, pointback="")
            facts = capture_run_facts(
                spec_path=run / "spec.md",
                pointback_path=run / "point-back.md",
                preview_dir=run / "preview",
                evidence_dir=run / "evidence",
                run_root=run,
                baseline_capture=BaselineCapture(project, run),
            )

            errors, _warnings = validate_run_policy(RunInputs(
                spec_path=str(run / "spec.md"),
                point_back_path=str(run / "point-back.md"),
                preview_dir=str(run / "preview"),
                decision_report=str(run / "decision-report.md"),
                evidence_dir=str(run / "evidence"),
                run_root=str(run),
                contract_project=str(project),
                contract_run=str(run),
                shaping_dir=str(run / "shaping"),
                run_facts=facts,
                require_preview=True,
                require_evidence=True,
                require_coverage=True,
                require_run_profile=True,
                require_baseline_verification=True,
            ))

            rules = {error.rule_id for error in errors}
            self.assertNotIn("G4.repair_evidence_missing", rules)

    def test_in_process_complete_explicitly_enables_the_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _prepare(Path(tmp))
            _mutate(run, pointback="")
            facts = capture_run_facts(
                spec_path=run / "spec.md",
                pointback_path=run / "point-back.md",
                preview_dir=run / "preview",
                evidence_dir=run / "evidence",
                run_root=run,
                baseline_capture=BaselineCapture(project, run),
            )

            errors, _warnings = validate_run_policy(RunInputs(
                spec_path=str(run / "spec.md"),
                point_back_path=str(run / "point-back.md"),
                preview_dir=str(run / "preview"),
                decision_report=str(run / "decision-report.md"),
                evidence_dir=str(run / "evidence"),
                run_root=str(run),
                contract_project=str(project),
                contract_run=str(run),
                shaping_dir=str(run / "shaping"),
                run_facts=facts,
                require_preview=True,
                require_evidence=True,
                require_coverage=True,
                require_run_profile=True,
                require_baseline_verification=True,
                require_repair_evidence=True,
            ))

            rules = {error.rule_id for error in errors}
            self.assertIn("G4.repair_evidence_missing", rules)


class FrozenSnapshotTests(unittest.TestCase):
    def _capture(self, project: Path, run: Path):
        facts = capture_run_facts(
            spec_path=run / "spec.md",
            pointback_path=run / "point-back.md",
            preview_dir=run / "preview",
            evidence_dir=run / "evidence",
            run_root=run,
            baseline_capture=BaselineCapture(project, run),
        )
        inputs = RunInputs(
            spec_path=str(run / "spec.md"),
            point_back_path=str(run / "point-back.md"),
            preview_dir=str(run / "preview"),
            decision_report=str(run / "decision-report.md"),
            evidence_dir=str(run / "evidence"),
            run_root=str(run),
            contract_project=str(project),
            contract_run=str(run),
            shaping_dir=str(run / "shaping"),
            run_facts=facts,
            require_preview=True,
            require_evidence=True,
            require_coverage=True,
            require_run_profile=True,
            require_baseline_verification=True,
            require_repair_evidence=True,
        )
        return facts, inputs

    def test_supplied_snapshot_survives_artifact_mutation_without_rereading(
            self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _prepare(Path(tmp))
            facts, inputs = self._capture(project, run)
            errors, _warnings = validate_run_policy(inputs)
            self.assertEqual(errors, [])

            (run / "evidence" / "L6.2-empty-r2.png").write_bytes(b"changed")
            (run / "evidence" / "manifest.jsonl").unlink()

            def forbidden(*_args, **_kwargs):
                raise AssertionError("the projection reopened artifact bytes")

            with patch.object(g6_records, "_open_binary", forbidden), \
                    patch.object(containment, "read_artifact", forbidden), \
                    patch.object(run_facts_module, "_read_text", forbidden), \
                    patch.object(run_facts_module, "_read_manifest", forbidden):
                second_errors, second_warnings = validate_run_policy(inputs)

            self.assertEqual(second_errors, [])
            self.assertEqual(second_warnings, [])

    def test_a_new_cli_run_sees_the_changed_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _prepare(Path(tmp))
            (run / "evidence" / "L6.2-empty-r2.png").write_bytes(b"changed")

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("G6.artifact_hash_mismatch", _rules(result))

    def test_a_snapshot_without_artifact_facts_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _prepare(Path(tmp))
            facts, inputs = self._capture(project, run)
            stripped = dataclasses.replace(facts, evidence_artifacts=None)

            errors, _warnings = validate_run_policy(
                dataclasses.replace(inputs, run_facts=stripped))

            rules = {error.rule_id for error in errors}
            self.assertIn("G6.artifact_facts_unavailable", rules)
            self.assertTrue(errors)

    def test_a_frozen_read_failure_survives_the_file_reappearing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _prepare(Path(tmp))
            before = run / "evidence" / "L6.2-empty-r1.png"
            saved = before.read_bytes()
            before.unlink()
            facts, inputs = self._capture(project, run)

            errors, _warnings = validate_run_policy(inputs)
            self.assertIn(
                "G6.artifact_missing", {error.rule_id for error in errors})

            before.write_bytes(saved)
            second_errors, _warnings = validate_run_policy(inputs)
            self.assertIn(
                "G6.artifact_missing",
                {error.rule_id for error in second_errors})

            fresh = _validate(run, "--format", "json", project=project)
            self.assertEqual(fresh.returncode, 0, fresh.stdout + fresh.stderr)


def _fact(reference: str, artifact: str | None, *, sha: str | None = None,
          reason: str = "") -> EvidenceArtifactFact:
    return EvidenceArtifactFact(
        reference=reference, artifact=artifact, sha256=sha, size=1,
        reason=reason)


def _entry(artifact: str, *, criterion: str = CRITERION,
           sha: str | None = None, capture_type: str = "screenshot") -> dict:
    entry = {
        "criterion": criterion,
        "artifact": artifact,
        "ts": "2026-11-07T10:00:00Z",
        "request": {
            "schemaVersion": 1,
            "viewport": dict(VIEWPORT),
            "freeze": dict(FREEZE),
        },
        "capture": {"type": capture_type, "state": "empty",
                    "artifact_path": f"evidence/{artifact}"},
    }
    if sha is not None:
        entry["sha256"] = sha
    return entry


class PureReferenceTests(unittest.TestCase):
    """One G6 rule for observed and repair references, without any disk."""

    def _one(self, reference: EvidenceReference, entries, facts):
        return validate_references(
            [reference], entries, {"L6.1", "L6.2"}, facts)[0]

    def test_unknown_criterion_is_distinct_from_a_missing_file(self) -> None:
        sha = "a" * 64
        unknown = self._one(
            EvidenceReference("L6.2", "evidence/a.png"),
            [_entry("a.png", criterion="L6.99", sha=sha)],
            (_fact("evidence/a.png", "a.png", sha=sha),))
        missing = self._one(
            EvidenceReference("L6.2", "evidence/a.png"),
            [],
            (_fact("evidence/a.png", "a.png",
                   reason=containment.REASON_NOT_REGULAR_FILE),))
        self.assertEqual(unknown.diagnostics[0].code, "unknown_criterion")
        self.assertEqual(missing.diagnostics[0].code, "artifact_missing")

    def test_a_fabricated_digest_is_distinct_from_absent_bytes(self) -> None:
        fact = _fact("evidence/a.png", "a.png", sha="b" * 64)
        mismatch = self._one(
            EvidenceReference("L6.2", "evidence/a.png"),
            [_entry("a.png", sha="c" * 64)], (fact,))
        unavailable = self._one(
            EvidenceReference("L6.2", "evidence/a.png", require_hash=True),
            [_entry("a.png", sha=None)], (fact,))
        self.assertEqual(mismatch.diagnostics[0].code, "artifact_hash_mismatch")
        self.assertEqual(
            unavailable.diagnostics[0].code, "artifact_hash_unavailable")

    def test_uppercase_declared_digest_is_malformed(self) -> None:
        fact = _fact("evidence/a.png", "a.png", sha="a" * 64)
        binding = self._one(
            EvidenceReference("L6.2", "evidence/a.png"),
            [_entry("a.png", sha="A" * 64)], (fact,))
        self.assertEqual(binding.diagnostics[0].code, "artifact_hash_malformed")

    def test_an_observed_entry_without_a_declared_hash_is_not_tightened(
            self) -> None:
        fact = _fact("evidence/a.png", "a.png", sha="b" * 64)
        entry = _entry("a.png", sha="b" * 64)
        entry.pop("sha256")
        binding = self._one(
            EvidenceReference("L6.2", "evidence/a.png"), [entry], (fact,))
        self.assertTrue(binding.ok)
        self.assertEqual(binding.sha256, "b" * 64)

    def test_every_escape_class_keeps_an_escape_fact(self) -> None:
        for reason in (
                containment.REASON_ABSOLUTE_PATH,
                containment.REASON_DOTDOT_SEGMENT,
                containment.REASON_CANONICAL_ESCAPE,
                containment.REASON_SYMLINK_ESCAPE,
                containment.REASON_RESOLUTION_FAILURE):
            binding = self._one(
                EvidenceReference("L6.2", "evidence/a.png"),
                [],
                (_fact("evidence/a.png", "a.png", reason=reason),))
            self.assertEqual(
                binding.diagnostics[0].code, "escape", reason)
            self.assertEqual(binding.diagnostics[0].detail, reason)

    def test_a_leaf_only_or_absolute_token_is_a_prefix_failure(self) -> None:
        for token in ("a.png", "C:/abs/a.png", "/abs/a.png"):
            binding = self._one(
                EvidenceReference("L6.2", token), [], ())
            self.assertEqual(binding.diagnostics[0].code, "reference_prefix")

    def test_a_missing_captured_fact_never_falls_back_to_disk(self) -> None:
        binding = self._one(
            EvidenceReference("L6.2", "evidence/a.png"), [], ())
        self.assertEqual(
            binding.diagnostics[0].code, "artifact_facts_unavailable")

    def test_no_fact_tuple_means_collection_was_not_performed(self) -> None:
        binding = self._one(
            EvidenceReference("L6.2", "evidence/a.png"), [], None)
        self.assertEqual(
            binding.diagnostics[0].code, "artifact_facts_unavailable")

    def test_declared_proof_type_must_match_the_capture_type(self) -> None:
        sha = "a" * 64
        mismatch = self._one(
            EvidenceReference("L6.2", "evidence/a.png", proof="screenshot"),
            [_entry("a.png", sha=sha, capture_type="a11y tree")],
            (_fact("evidence/a.png", "a.png", sha=sha),))
        self.assertEqual(mismatch.diagnostics[0].code, "proof_type")
        matched = self._one(
            EvidenceReference("L6.2", "evidence/a.png",
                              proof="a11y_tree"),
            [_entry("a.png", sha=sha, capture_type="a11y tree")],
            (_fact("evidence/a.png", "a.png", sha=sha),))
        self.assertTrue(matched.ok)

    def test_read_failure_is_named_not_swallowed(self) -> None:
        binding = self._one(
            EvidenceReference("L6.2", "evidence/a.png"),
            [],
            (_fact("evidence/a.png", "a.png",
                   reason=g6_records.REASON_UNREADABLE),))
        self.assertEqual(binding.diagnostics[0].code, "artifact_unreadable")

    def test_validate_references_performs_no_file_access(self) -> None:
        def forbidden(*_args, **_kwargs):
            raise AssertionError("validate_references touched the filesystem")

        with patch.object(containment, "read_artifact", forbidden), \
                patch.object(g6_records, "_open_binary", forbidden):
            binding = self._one(
                EvidenceReference("L6.2", "evidence/a.png"),
                [_entry("a.png", sha="a" * 64)],
                (_fact("evidence/a.png", "a.png", sha="a" * 64),))
        self.assertTrue(binding.ok)


if __name__ == "__main__":
    unittest.main()