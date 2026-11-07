#!/usr/bin/env python3
"""T-158 phase B: complete acceptance consumes a fresh baseline capture.

The executable fixtures are real project/.scratch/run layouts bound through the
baseline owner's prepare/confirm. The static examples stay illustrative: their
state files are stale and their sibling layout violates owner containment.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
ROOT = PACKAGE.parent.parent
VALIDATOR = PACKAGE / "scripts" / "validate_run.py"
RUN_STATUS = PACKAGE / "scripts" / "run_status.py"
AGGREGATE = ROOT / "scripts" / "aggregate_runs.py"
OWNER_PATH = (
    PACKAGE / "skills" / "design-baseline" / "scripts" / "design_baseline.py"
)
BASE = PACKAGE / "examples" / "export-upgrade"

if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts import run_facts as run_facts_module  # noqa: E402
from design_playbook.scripts.run_facts import (  # noqa: E402
    BaselineCapture,
    capture_run_facts,
)
from design_playbook.scripts.validate_run import (  # noqa: E402
    RunInputs,
    run as validate_run_policy,
)

SPEC = importlib.util.spec_from_file_location("baseline_owner_phase_b", OWNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load baseline owner: {OWNER_PATH}")
design_baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(design_baseline)

THEME_CSS = """:root {
  --color-background: #ffffff;
  --color-surface: #f7f8fa;
  --color-text: #1a1a1a;
  --color-primary: #2457d6;
}
body { font-family: Inter, system-ui, sans-serif; }
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _locate(tmp: Path, *, name: str = "run") -> tuple[Path, Path]:
    """Copy the export-upgrade scenario into owner containment.

    The static example's ``project/`` and ``run/`` are siblings and its state
    binds a relative root; executable acceptance copies the scenario under
    ``<project>/.scratch/<name>`` and removes the stale state.
    """

    project = tmp / "project"
    run = project / ".scratch" / name
    shutil.copytree(BASE / "project", project)
    shutil.copytree(BASE / "run", run)
    shutil.rmtree(run / "design-baseline", ignore_errors=True)
    return project, run


def _bind(project: Path, run: Path, *, design_text: str | None = None) -> str:
    """Bind a real baseline through prepare/confirm; return its sha256."""

    _write(project / "src" / "theme.css", THEME_CSS)
    if design_text is not None:
        _write(project / "DESIGN.md", design_text)
    outcome = design_baseline.prepare(project, run)
    if outcome["status"] == "needs_confirmation":
        design_baseline.confirm(project, run, decision="accept")
    elif outcome["status"] != "ready":
        raise AssertionError(f"baseline did not bind: {outcome}")
    state = json.loads(
        (run / "design-baseline" / "state.json").read_text(encoding="utf-8"))
    sha = state["baseline"]["sha256"]
    _rebind_report(run, sha)
    return sha


def _rebind_report(run: Path, new_sha: str) -> None:
    """Point the report's current-binding references at the fresh baseline.

    Entry ``baseline:`` pins stay untouched so the stale-review scenario keeps
    its meaning; only the previously-current sha (top line + keep-review
    re-binds) is rewritten to the sha prepare/confirm actually produced.
    """

    report = run / "decision-report.md"
    text = report.read_text(encoding="utf-8")
    match = re.search(r"(?m)^design-baseline:.*?([0-9a-f]{64})", text)
    if match is None:
        raise AssertionError("fixture report has no design-baseline binding line")
    report.write_text(text.replace(match.group(1), new_sha), encoding="utf-8")


def _waive(project: Path, run: Path) -> None:
    _write(project / "src" / "theme.css", THEME_CSS)
    design_baseline.prepare(project, run)
    design_baseline.confirm(
        project, run, decision="waive",
        reason="User accepts legacy visual drift for this run")


def _rewrite_state(run: Path, mutate) -> None:
    state_path = run / "design-baseline" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mutate(state)
    state_path.write_text(json.dumps(state), encoding="utf-8")


def _state_as_directory(run: Path) -> Path:
    state_path = run / "design-baseline" / "state.json"
    state_path.unlink()
    state_path.mkdir()
    return state_path


def _link_state_dir_outside(run: Path, outside: Path) -> Path:
    """Move the state directory outside the run and symlink it back."""

    state_dir = run / "design-baseline"
    target = outside / "design-baseline"
    shutil.move(str(state_dir), str(target))
    try:
        os.symlink(target, state_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        raise unittest.SkipTest("symlink creation unavailable")
    return target


def _sibling_fixture(tmp: Path) -> tuple[Path, Path]:
    """Static example layout: sibling project/ + run/, no baseline state."""

    project = tmp / "project"
    run = tmp / "run"
    shutil.copytree(BASE / "project", project)
    shutil.copytree(BASE / "run", run)
    shutil.rmtree(run / "design-baseline", ignore_errors=True)
    return project, run


def _validate(
    run: Path,
    *extra: str,
    project: Path | None = None,
    run_root: bool = True,
    contract_run: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(VALIDATOR),
        str(run / "spec.md"),
        str(run / "point-back.md"),
        "--preview-dir", str(run / "preview"),
        "--decision-report", str(run / "decision-report.md"),
        "--evidence-dir", str(run / "evidence"),
        "--shaping-dir", str(run / "shaping"),
        *extra,
    ]
    if run_root:
        command.extend(["--run-root", str(run)])
    command.extend(["--contract-run", str(contract_run or run)])
    if project is not None:
        command.extend(["--contract-project", str(project)])
    return subprocess.run(
        command, capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    )


def _validate_minimal(
    run: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    """Complete CLI with neither --run-root nor any contract/authority flag."""

    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            str(run / "spec.md"),
            str(run / "point-back.md"),
            "--preview-dir", str(run / "preview"),
            "--decision-report", str(run / "decision-report.md"),
            "--evidence-dir", str(run / "evidence"),
            "--shaping-dir", str(run / "shaping"),
            *extra,
        ],
        capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    )


def _json_findings(result: subprocess.CompletedProcess[str]) -> list[dict]:
    payload = json.loads(result.stdout)
    if not isinstance(payload, list):
        raise AssertionError(f"validator JSON is not a list: {result.stdout!r}")
    return payload


def _rule_ids(findings: list[dict]) -> set[str]:
    return {item.get("rule_id") for item in findings}


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class CompleteAcceptanceCliTests(unittest.TestCase):
    def test_complete_acceptance_passes_a_freshly_bound_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)

            result = _validate(run, project=project)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("RUN OK", result.stdout)

    def test_baseline_run_falls_back_to_the_explicit_pointback_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)

            result = _validate(run, project=project, run_root=False)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_changed_bound_design_fails_with_the_owner_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            with (project / "DESIGN.md").open("a", encoding="utf-8") as handle:
                handle.write("\n")

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            findings = _json_findings(result)
            self.assertIn("baseline.binding-invalid", _rule_ids(findings))
            error = next(
                item for item in findings
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "DESIGN.md")
            self.assertEqual(error["severity"], "error")
            self.assertIn("baseline changed after binding", error["message"])

    def test_changed_source_fails_with_the_reference_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _write(project / "src" / "theme.css",
                   ":root { --color-primary: #000000; }\n")

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            findings = _json_findings(result)
            self.assertIn("baseline.reference-broken", _rule_ids(findings))
            broken = next(
                item for item in findings
                if item["rule_id"] == "baseline.reference-broken")
            self.assertEqual(broken["owner"], "src/theme.css")
            self.assertEqual(broken["severity"], "error")

    def test_missing_project_authorization_fails_with_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            findings = _json_findings(result)
            self.assertIn("baseline.binding-invalid", _rule_ids(findings))
            error = next(
                item for item in findings
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "--contract-project")
            self.assertIn("--contract-project", error["message"])
            self.assertIn("--contract-project", error["repair"])

    def test_old_findings_artifact_cannot_substitute_for_a_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            # A leftover pass report is not a verified result: complete
            # acceptance ignores it and re-checks the current bytes.
            _write(
                run / "design-baseline" / "findings.json",
                json.dumps({"gate": {"verdict": "pass"}, "findings": []}),
            )
            with (project / "DESIGN.md").open("a", encoding="utf-8") as handle:
                handle.write("\n")

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "baseline.binding-invalid", _rule_ids(_json_findings(result)))

    def test_pointback_parent_state_without_authorization_blocks(self) -> None:
        # State physically sits beside the point-back (the run authority), but
        # complete acceptance must never derive project authorization from
        # that parent: without --contract-project it reports a named block.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            with (project / "DESIGN.md").open("a", encoding="utf-8") as handle:
                handle.write("\n")

            result = _validate_minimal(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "--contract-project")
            self.assertIn("--contract-project", error["message"])

    def test_pointback_parent_malformed_state_without_authorization_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _write(run / "design-baseline" / "state.json", "{not json")

            result = _validate_minimal(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "design-baseline/state.json")
            self.assertIn("line 1", error["message"])

    def test_directory_state_without_authorization_blocks(self) -> None:
        # A present non-file state is not "absent": complete acceptance must
        # report it, with or without the explicit run root, and must never
        # authorize project reads to discover that.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _state_as_directory(run)

            for label, result in (
                ("pointback-parent",
                 _validate_minimal(run, "--format", "json")),
                ("run-root", _validate(run, "--format", "json")),
            ):
                self.assertEqual(
                    result.returncode, 1,
                    f"{label}: {result.stdout}{result.stderr}")
                error = next(
                    item for item in _json_findings(result)
                    if item["rule_id"] == "baseline.binding-invalid")
                self.assertEqual(error["owner"], "design-baseline/state.json")
                self.assertIn("not a regular file", error["message"])

    def test_directory_state_with_authorization_reports_nonfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _state_as_directory(run)

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertIn("not a regular file", error["message"])

    def test_dangling_symlink_state_without_authorization_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            state_path = run / "design-baseline" / "state.json"
            state_path.unlink()
            try:
                os.symlink(run / "missing-state.json", state_path)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")

            result = _validate_minimal(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "design-baseline/state.json")
            self.assertIn("must not be a symlink", error["message"])

    def test_escaping_state_dir_symlink_is_not_read_without_authorization(self) -> None:
        # The state directory itself is a symlink to a directory outside the
        # run. Complete presence must not follow it, let alone read the
        # external JSON, without project authorization.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            outside = Path(tmp) / "outside"
            outside.mkdir()
            _link_state_dir_outside(run, outside)

            text, error = run_facts_module._read_baseline_strict(run)

            self.assertIsNone(text)
            self.assertIn("must not be a symlink", error)

            result = _validate_minimal(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "design-baseline/state.json")
            self.assertIn("must not be a symlink", error["message"])

    def test_escaping_state_dir_symlink_blocks_authorized_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            outside = Path(tmp) / "outside"
            outside.mkdir()
            _link_state_dir_outside(run, outside)

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertIn("must not be a symlink", error["message"])

    def test_owner_verify_rejects_escaping_state_dir_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            outside = Path(tmp) / "outside"
            outside.mkdir()
            _link_state_dir_outside(run, outside)

            with self.assertRaises(design_baseline.BaselineError) as ctx:
                design_baseline.verify(project, run)
            self.assertIn("must not be a symlink", str(ctx.exception))

    def test_oversize_state_is_not_treated_as_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            state_path = run / "design-baseline" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["padding"] = "x" * (4 * 1024 * 1024)
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = _validate_minimal(run, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "design-baseline/state.json")
            self.assertIn("exceeds", error["message"])

    def test_owner_presence_entry_distinguishes_absent_and_valid(self) -> None:
        # One owner entry: valid run-local state returns text, true absence is
        # (None, None). run_facts and capture must delegate here, not restate
        # the presence/containment rule.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)

            text, error = design_baseline._state_presence(run)

            self.assertIsNone(error)
            self.assertIsNotNone(text)

            (run / "design-baseline" / "state.json").unlink()
            self.assertEqual(
                design_baseline._state_presence(run), (None, None))
            self.assertIsNone(
                design_baseline.capture_optional(project, run))
            # Public strict capture keeps its existing missing-state failure.
            with self.assertRaises(design_baseline.BaselineError) as ctx:
                design_baseline.capture(project, run)
            self.assertIn("baseline state does not exist", str(ctx.exception))

    def test_strict_presence_delegates_to_the_owner_entry(self) -> None:
        # Pins the single-source boundary: replacing the owner entry is
        # observable through the complete strict reader.
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _locate(Path(tmp))
            calls: list[Path] = []

            class Owner:
                @staticmethod
                def _state_presence(run_root: Path):
                    calls.append(run_root)
                    return None, "owner-entry error"

            with patch.object(
                run_facts_module, "_design_baseline_owner", return_value=Owner
            ):
                text, error = run_facts_module._read_baseline_strict(run)

            self.assertIsNone(text)
            self.assertEqual(error, "owner-entry error")
            self.assertEqual(calls, [run])

    def test_authorized_capture_reads_state_exactly_once(self) -> None:
        # Presence, identity, findings, and digest must come from one read:
        # a second read would be a change window. The patched second read
        # returns different content, so reaching it is observable.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            state_path = run / "design-baseline" / "state.json"
            first_text = state_path.read_text(encoding="utf-8")
            payload = json.loads(first_text)
            payload["status"] = "changed-between-reads"
            changed_text = json.dumps(payload)
            reads: list[Path] = []
            original_read_text = Path.read_text

            def counting_read_text(path: Path, *args, **kwargs):
                if path.name == "state.json" and path.parent.name == "design-baseline":
                    reads.append(path)
                    if len(reads) > 1:
                        return changed_text
                return original_read_text(path, *args, **kwargs)

            with patch.object(Path, "read_text", counting_read_text):
                captured = run_facts_module._capture_baseline(
                    BaselineCapture(project_root=project, run_root=run))

            state_text, error, findings_json, _, _, digest = captured
            self.assertIsNone(error)
            self.assertEqual(len(reads), 1, reads)
            self.assertEqual(state_text, first_text)
            self.assertNotEqual(state_text, changed_text)
            self.assertIsNotNone(findings_json)
            self.assertIsNotNone(digest)

    def test_absent_capture_performs_no_state_read(self) -> None:
        # True absence is decided from metadata: no full-file read is spent
        # to discover it.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            reads: list[Path] = []
            original_read_text = Path.read_text

            def counting_read_text(path: Path, *args, **kwargs):
                if path.name == "state.json" and path.parent.name == "design-baseline":
                    reads.append(path)
                return original_read_text(path, *args, **kwargs)

            with patch.object(Path, "read_text", counting_read_text):
                captured = run_facts_module._capture_baseline(
                    BaselineCapture(project_root=project, run_root=run))

            self.assertEqual(captured, (None, None, None, None, None, None))
            self.assertEqual(reads, [])

    def test_strict_presence_reads_state_exactly_once(self) -> None:
        # The no-project complete path keeps one capped read, never a probe
        # read followed by a second read.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            reads: list[Path] = []
            original_read_text = Path.read_text

            def counting_read_text(path: Path, *args, **kwargs):
                if path.name == "state.json" and path.parent.name == "design-baseline":
                    reads.append(path)
                return original_read_text(path, *args, **kwargs)

            with patch.object(Path, "read_text", counting_read_text):
                text, error = run_facts_module._read_baseline_strict(run)

            self.assertIsNone(error)
            self.assertIsNotNone(text)
            self.assertEqual(len(reads), 1, reads)

    def test_absent_sibling_baseline_with_g7_project_stays_legal(self) -> None:
        # Absent baseline adds no obligation, so it must not inherit the
        # present-baseline project containment rule: a legitimate G7 sibling
        # layout with no state stays green even with --contract-project.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _sibling_fixture(Path(tmp))

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(_json_findings(result), [])

    def test_absent_sibling_baseline_without_project_stays_legal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, run = _sibling_fixture(Path(tmp))

            result = _validate(run, "--format", "json")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_present_sibling_baseline_is_still_rejected(self) -> None:
        # Presence is detected from the run root first; only then does the
        # owner containment rule reject the sibling layout.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _sibling_fixture(Path(tmp))
            state = {
                "schema": "design-baseline/v1",
                "status": "ready",
                "project_root": str(project.resolve()),
                "baseline": {
                    "path": "DESIGN.md",
                    "sha256": "a" * 64,
                    "origin": "generated",
                },
                "sources": [],
                "decision": {
                    "kind": "accepted",
                    "confirmed_at": "2026-11-07T00:00:00Z",
                },
            }
            _write(run / "design-baseline" / "state.json", json.dumps(state))

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertIn("run root escapes project root", error["message"])

    def test_malformed_baseline_path_type_yields_named_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            state_path = run / "design-baseline" / "state.json"
            original_text = state_path.read_text(encoding="utf-8")
            _rewrite_state(run, lambda state: state["baseline"].__setitem__(
                "path", []))

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "design-baseline/state.json")
            self.assertIn("baseline path", error["message"])

            # Restoring the same state returns to the normal positive control.
            state_path.write_text(original_text, encoding="utf-8")
            restored = _validate(run, "--format", "json", project=project)
            self.assertEqual(
                restored.returncode, 0, restored.stdout + restored.stderr)

    def test_malformed_decision_kind_type_yields_named_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _rewrite_state(run, lambda state: state["decision"].__setitem__(
                "kind", []))

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "design-baseline/state.json")
            self.assertIn("decision kind", error["message"])

    def test_malformed_baseline_origin_type_yields_named_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _rewrite_state(run, lambda state: state["baseline"].__setitem__(
                "origin", {}))

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "design-baseline/state.json")
            self.assertIn("baseline origin", error["message"])

    def test_malformed_promotions_type_yields_named_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _rewrite_state(run, lambda state: state.__setitem__(
                "promotions", None))

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "design-baseline/state.json")
            self.assertIn("promotions", error["message"])

    def test_ready_state_without_binding_preserves_the_owner_failure(self) -> None:
        # The owner genuinely rejects a ready state with no binding; the
        # projection must keep that row (path/message), not replace it with a
        # snapshot-mismatch accusation that recapture could never fix.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _rewrite_state(run, lambda state: state.__setitem__(
                "baseline", None))

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "DESIGN.md")
            self.assertIn(
                "bound baseline path is not a supported candidate",
                error["message"])

    def test_default_snapshot_does_not_tighten_state_presence(self) -> None:
        # Status/aggregate keep the historical reader: only the complete
        # acceptance boundary distinguishes non-file from absent.
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _state_as_directory(run)

            facts = capture_run_facts(run_root=run)

            self.assertEqual(facts.artifact_state("baseline"), "missing")
            self.assertIsNone(facts.baseline_findings)

    def test_pointback_parent_without_state_or_authorization_stays_legal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            self.assertFalse((run / "design-baseline").exists())

            result = _validate_minimal(run)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("RUN OK", result.stdout)

    def test_absent_baseline_adds_no_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            self.assertFalse((run / "design-baseline").exists())

            result = _validate(run, project=project)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("RUN OK", result.stdout)

    def test_legitimate_waiver_passes_complete_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _waive(project, run)

            result = _validate(run, project=project)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(
                (run / "design-baseline" / "state.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(state["status"], "waived")

    def test_forged_waiver_fails_complete_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _waive(project, run)
            state_path = run / "design-baseline" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["decision"] = None
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "design-baseline/state.json")
            self.assertIn("invalid baseline waiver decision", error["message"])

    def test_pending_baseline_fails_complete_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _write(project / "src" / "theme.css", THEME_CSS)
            outcome = design_baseline.prepare(project, run)
            self.assertEqual(outcome["status"], "needs_confirmation")

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "baseline.binding-invalid", _rule_ids(_json_findings(result)))

    def test_malformed_state_fails_complete_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _write(run / "design-baseline" / "state.json", "{not json")

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertEqual(error["owner"], "design-baseline/state.json")
            self.assertIn("cannot read baseline state", error["message"])

    def test_foreign_state_root_fails_complete_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            state_path = run / "design-baseline" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["project_root"] = str((Path(tmp) / "other-project").resolve())
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            error = next(
                item for item in _json_findings(result)
                if item["rule_id"] == "baseline.binding-invalid")
            self.assertIn("bound to a different project root", error["message"])

    def test_contract_run_disagreement_blocks_complete_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            other_run = Path(tmp) / "elsewhere"

            result = _validate(
                run, "--format", "json", project=project,
                contract_run=other_run)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            findings = _json_findings(result)
            errors = [item for item in findings
                      if item["rule_id"] == "baseline.binding-invalid"]
            self.assertTrue(errors)
            self.assertTrue(
                any(item["owner"] == "--contract-run" for item in errors))

    def test_warning_and_advisory_stay_visible_and_nonblocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            source = project / "src" / "theme.css"
            _write(source, THEME_CSS)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            design = (
                "---\n"
                'name: "product"\n'
                "colors:\n"
                '  background: "#ffffff"\n'
                '  text: "#1a1a1a"\n'
                '  primary: "#2457d6"\n'
                "---\n\n"
                "# Design System: product\n\n"
                "## Color Palette & Roles\n\n"
                "- [observed] `--color-legacy: #112233`\n\n"
                "## Source Evidence & Confidence\n\n"
                "- [observed] path: `src/theme.css`\n"
                f"  sha256: `{digest}`\n"
                "  confidence: high\n"
            )
            _bind(project, run, design_text=design)

            result = _validate(run, "--format", "json", project=project)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            findings = _json_findings(result)
            warnings = [item for item in findings if item["severity"] == "warning"]
            advisories = [
                item for item in findings if item["severity"] == "advisory"]
            self.assertIn("baseline.token-orphaned", _rule_ids(warnings))
            self.assertIn("baseline.check-unavailable", _rule_ids(advisories))

    def test_legacy_and_selective_modes_do_not_verify_the_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            with (project / "DESIGN.md").open("a", encoding="utf-8") as handle:
                handle.write("\n")

            legacy = _validate(run, "--legacy", "--format", "json", project=project)
            selective = _validate(
                run, "--require-evidence", "--require-coverage",
                "--format", "json", project=project)

            self.assertEqual(legacy.returncode, 0, legacy.stdout + legacy.stderr)
            self.assertEqual(
                selective.returncode, 0, selective.stdout + selective.stderr)
            for result in (legacy, selective):
                self.assertNotIn(
                    "baseline.binding-invalid", _rule_ids(_json_findings(result)))


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
        )
        return facts, inputs

    def test_capture_exposes_text_digest_and_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)

            facts, _inputs = self._capture(project, run)

            state_text = (run / "design-baseline" / "state.json").read_text(
                encoding="utf-8")
            self.assertEqual(
                facts.baseline_capture_state_sha256,
                hashlib.sha256(state_text.encode("utf-8")).hexdigest(),
            )
            self.assertEqual(
                facts.baseline_capture_project, str(project.resolve()))
            self.assertEqual(facts.baseline_capture_run, str(run.resolve()))
            self.assertEqual(
                facts.baseline_findings["schema"],
                "design-baseline-findings/v1",
            )
            self.assertEqual(facts.artifact_state("baseline"), "complete")

    def test_supplied_snapshot_is_pure_after_disk_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _facts, inputs = self._capture(project, run)
            errors, warnings = validate_run_policy(inputs)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

            with (project / "DESIGN.md").open("a", encoding="utf-8") as handle:
                handle.write("\n")
            _write(project / "src" / "theme.css", THEME_CSS + "/* drift */\n")
            _write(run / "design-baseline" / "state.json", "{}")

            def _forbidden(*_args, **_kwargs):
                raise AssertionError("run() reopened the baseline snapshot")

            with patch.object(run_facts_module, "_read_baseline", _forbidden), \
                    patch.object(run_facts_module, "_read_text", _forbidden), \
                    patch.object(run_facts_module, "_read_manifest", _forbidden), \
                    patch.object(run_facts_module, "_read_optional_run_facts", _forbidden), \
                    patch.object(run_facts_module, "_design_baseline_owner", _forbidden):
                second_errors, second_warnings = validate_run_policy(inputs)

            self.assertEqual(second_errors, [])
            self.assertEqual(second_warnings, [])

    def test_uncaptured_snapshot_with_present_state_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            facts = capture_run_facts(
                spec_path=run / "spec.md",
                pointback_path=run / "point-back.md",
                preview_dir=run / "preview",
                evidence_dir=run / "evidence",
                run_root=run,
            )
            self.assertIsNone(facts.baseline_findings)

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
            self.assertIn("baseline.binding-invalid", rules)
            self.assertTrue(
                any("no fresh captured result" in error.message
                    for error in errors))

    def test_tampered_frozen_state_text_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            facts, inputs = self._capture(project, run)
            self.assertEqual(validate_run_policy(inputs)[0], [])

            state = json.loads(
                (run / "design-baseline" / "state.json").read_text(
                    encoding="utf-8"))
            state["decision"] = None
            tampered = dataclasses.replace(
                facts, _baseline_text=json.dumps(state))

            errors, _warnings = validate_run_policy(
                dataclasses.replace(inputs, run_facts=tampered))

            rules = {error.rule_id for error in errors}
            self.assertIn("baseline.binding-invalid", rules)
            self.assertTrue(
                any("recorded digest" in error.message for error in errors))

    def test_tampered_state_with_stale_findings_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            facts, inputs = self._capture(project, run)

            state = json.loads(
                (run / "design-baseline" / "state.json").read_text(
                    encoding="utf-8"))
            state["baseline"]["sha256"] = "0" * 64
            text = json.dumps(state, sort_keys=True)
            tampered = dataclasses.replace(
                facts,
                _baseline_text=text,
                baseline_capture_state_sha256=hashlib.sha256(
                    text.encode("utf-8")).hexdigest(),
            )

            errors, _warnings = validate_run_policy(
                dataclasses.replace(inputs, run_facts=tampered))

            rules = {error.rule_id for error in errors}
            self.assertIn("baseline.binding-invalid", rules)
            self.assertTrue(
                any("does not match the frozen state" in error.message
                    for error in errors))

    def test_tampered_waiver_state_with_stale_findings_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            facts, inputs = self._capture(project, run)

            state = json.loads(
                (run / "design-baseline" / "state.json").read_text(
                    encoding="utf-8"))
            state["status"] = "waived"
            state["baseline"] = None
            state["decision"] = {
                "kind": "waived",
                "reason": "User accepts legacy visual drift for this run",
                "confirmed_at": "2026-11-07T00:00:00Z",
            }
            text = json.dumps(state, sort_keys=True)
            tampered = dataclasses.replace(
                facts,
                _baseline_text=text,
                baseline_capture_state_sha256=hashlib.sha256(
                    text.encode("utf-8")).hexdigest(),
            )

            errors, _warnings = validate_run_policy(
                dataclasses.replace(inputs, run_facts=tampered))

            rules = {error.rule_id for error in errors}
            self.assertIn("baseline.binding-invalid", rules)
            self.assertTrue(
                any("disagree on the waiver" in error.message
                    for error in errors))

    def test_foreign_capture_identity_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _facts, inputs = self._capture(project, run)
            foreign = str(Path(tmp) / "other-project")

            errors, _warnings = validate_run_policy(RunInputs(
                spec_path=inputs.spec_path,
                point_back_path=inputs.point_back_path,
                preview_dir=inputs.preview_dir,
                decision_report=inputs.decision_report,
                evidence_dir=inputs.evidence_dir,
                run_root=inputs.run_root,
                contract_project=foreign,
                contract_run=inputs.contract_run,
                shaping_dir=inputs.shaping_dir,
                run_facts=inputs.run_facts,
                require_preview=True,
                require_evidence=True,
                require_coverage=True,
                require_run_profile=True,
                require_baseline_verification=True,
            ))

            rules = {error.rule_id for error in errors}
            self.assertIn("baseline.binding-invalid", rules)
            self.assertTrue(
                any("does not match --contract-project" in error.message
                    for error in errors))

    def test_requirement_defaults_off_for_in_process_callers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp))
            _bind(project, run)
            _facts, inputs = self._capture(project, run)
            with (project / "DESIGN.md").open("a", encoding="utf-8") as handle:
                handle.write("\n")

            errors, _warnings = validate_run_policy(RunInputs(
                spec_path=inputs.spec_path,
                point_back_path=inputs.point_back_path,
                preview_dir=inputs.preview_dir,
                evidence_dir=inputs.evidence_dir,
                run_root=inputs.run_root,
                contract_project=inputs.contract_project,
                contract_run=inputs.contract_run,
                shaping_dir=inputs.shaping_dir,
                run_facts=inputs.run_facts,
                require_preview=True,
                require_evidence=True,
                require_coverage=True,
                require_run_profile=True,
            ))

            self.assertNotIn(
                "baseline.binding-invalid", {error.rule_id for error in errors})


class ReadOnlyProjectionTests(unittest.TestCase):
    def test_status_and_aggregate_leave_the_tree_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, run = _locate(Path(tmp), name="dogfood/run")
            _bind(project, run)
            before = _tree_hashes(project)

            status = subprocess.run(
                [sys.executable, str(RUN_STATUS), str(run), "--json"],
                capture_output=True, text=True, check=False,
                encoding="utf-8", errors="replace",
            )
            aggregate = subprocess.run(
                [sys.executable, str(AGGREGATE), "--root", str(project),
                 "--runs", str(run)],
                capture_output=True, text=True, check=False,
                encoding="utf-8", errors="replace",
            )

            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertEqual(
                aggregate.returncode, 0, aggregate.stdout + aggregate.stderr)
            self.assertEqual(_tree_hashes(project), before)


if __name__ == "__main__":
    unittest.main()