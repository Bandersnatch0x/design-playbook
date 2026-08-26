"""Immutable facts loaded once from a Closed-loop run.

This module owns artifact loading and delegates syntax/integrity parsing to
their existing authorities.  Gate and status modules retain policy: they
project diagnostics and resume narration from one ``RunFacts`` snapshot.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from design_playbook.mcp.evidence.ledger_syntax import LedgerFacts, parse_ledger
from design_playbook.mcp.preview.integrity import PreviewSnapshot, inspect_preview
from design_playbook.scripts.dd_entries import DDEntry, parse_dd_entries
from design_playbook.scripts.run_profile import RunProfile, parse_run_profile
from design_playbook.scripts.shaping_log import (
    ShapingLogError,
    parse_shaping_log,
)
from design_playbook.scripts.verdict_syntax import VerdictFacts, parse_verdict


@dataclass(frozen=True)
class ArtifactReadFact:
    """Structured result for an artifact that could not be loaded."""

    artifact: str
    path: Path
    code: str
    message: str
    line_number: int | None = None


# Presence is one fact per artifact, not a per-artifact convention (ADR-0039).
# Consumers ask ``artifact_state`` instead of learning which artifacts keep a
# ``missing`` read error, which expose a boolean, and which must be re-stated
# by the caller.
STATE_COMPLETE = "complete"
STATE_MISSING = "missing"
STATE_UNREADABLE = "unreadable"
STATED_ARTIFACTS = (
    "spec",
    "point_back",
    "plan",
    "decision_report",
    "craft_guard",
    "manifest",
    "baseline",
    "shaping",
    "run_profile",
)


@dataclass(frozen=True)
class RunFacts:
    """One immutable view of the artifacts consumed by run policy."""

    run_root: Path | None
    spec_path: Path | None
    pointback_path: Path | None
    preview_dir: Path | None
    evidence_dir: Path | None
    spec_text: str
    pointback_text: str
    plan_text: str
    plan_fill_artifacts: tuple[str, ...]
    craft_guard_text: str
    ledger: LedgerFacts
    verdict: VerdictFacts
    preview: PreviewSnapshot | None
    _manifest_lines: tuple[str, ...]
    existing_paths: frozenset[str]
    _baseline_text: str | None
    baseline_state_error: str | None
    read_errors: tuple[ArtifactReadFact, ...]
    run_profile: RunProfile | None = None
    decision_report_text: str = ""
    decision_entries: tuple[DDEntry, ...] = ()
    shaping_events: tuple[dict[str, Any], ...] | None = None
    shaping_error: str | None = None
    _artifact_states: tuple[tuple[str, str], ...] = ()

    @property
    def manifest_entries(self) -> tuple[dict[str, Any], ...]:
        """Return detached manifest values backed by immutable captured text."""
        return tuple(json.loads(line) for line in self._manifest_lines)

    @property
    def baseline_state(self) -> object | None:
        """Return a detached baseline value backed by immutable captured text."""
        if self._baseline_text is None:
            return None
        return json.loads(self._baseline_text)

    def artifact_state(self, artifact: str) -> str:
        """``complete`` | ``missing`` | ``unreadable`` for one run artifact.

        The same three values for every artifact in ``STATED_ARTIFACTS``: the
        loader already established presence while reading, so no consumer has
        to re-stat the file or infer absence from an empty text field.
        """
        if artifact not in STATED_ARTIFACTS:
            raise KeyError(artifact)
        for name, state in self._artifact_states:
            if name == artifact:
                return state
        return STATE_MISSING

    @property
    def craft_guard_exists(self) -> bool:
        """Derived from the uniform craft_guard presence fact."""
        return self.artifact_state("craft_guard") != STATE_MISSING


@dataclass(frozen=True)
class _OptionalRunFacts:
    plan_text: str = ""
    run_profile: RunProfile | None = None
    decision_report_text: str = ""
    decision_entries: tuple[DDEntry, ...] = ()
    shaping_events: tuple[dict[str, Any], ...] | None = None
    shaping_error: str | None = None
    craft_guard_text: str = ""
    read_errors: tuple[ArtifactReadFact, ...] = ()


def _read_manifest(
    evidence_dir: Path | None,
) -> tuple[tuple[str, ...], tuple[ArtifactReadFact, ...], str]:
    if evidence_dir is None:
        return (), (), STATE_MISSING
    path = evidence_dir / "manifest.jsonl"
    if not path.is_file():
        return (), (), STATE_MISSING
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return (
            (),
            (ArtifactReadFact("manifest", path, "unreadable", str(exc)),),
            STATE_UNREADABLE,
        )
    entries: list[str] = []
    errors: list[ArtifactReadFact] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(
                ArtifactReadFact(
                    "manifest",
                    path,
                    "malformed_json",
                    f"manifest line {line_number} is not valid JSON: {exc.msg}",
                    line_number,
                )
            )
            continue
        if not isinstance(value, dict):
            errors.append(
                ArtifactReadFact(
                    "manifest",
                    path,
                    "invalid_entry",
                    f"manifest line {line_number} must be a JSON object",
                    line_number,
                )
            )
            continue
        entries.append(line)
    return tuple(entries), tuple(errors), STATE_COMPLETE


def _read_baseline(run_root: Path | None) -> tuple[str | None, str | None]:
    if run_root is None:
        return None, None
    path = run_root / "design-baseline" / "state.json"
    if not path.is_file():
        return None, None
    try:
        text = path.read_text(encoding="utf-8")
        json.loads(text)
        return text, None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, str(exc)


def _read_text(
    artifact: str,
    path: Path | None,
    *,
    fallback_encoding: str | None = None,
) -> tuple[str, ArtifactReadFact | None]:
    if path is None:
        return "", None
    if not path.is_file():
        error = FileNotFoundError(2, "No such file or directory", str(path))
        return "", ArtifactReadFact(artifact, path, "missing", str(error))
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError as exc:
        if fallback_encoding is not None:
            try:
                return path.read_text(encoding=fallback_encoding), None
            except (OSError, UnicodeError) as fallback_exc:
                return "", ArtifactReadFact(
                    artifact, path, "unreadable", str(fallback_exc))
        return "", ArtifactReadFact(artifact, path, "unreadable", str(exc))
    except OSError as exc:
        return "", ArtifactReadFact(artifact, path, "unreadable", str(exc))


def _existing_paths(run_root: Path | None) -> frozenset[str]:
    if run_root is None or not run_root.is_dir():
        return frozenset()
    paths: set[str] = set()
    for candidate in run_root.rglob("*"):
        try:
            paths.add(candidate.relative_to(run_root).as_posix())
        except (OSError, ValueError):
            continue
    return frozenset(paths)


def _plan_fill_artifacts(
    run_root: Path | None,
    plan_text: str,
) -> tuple[str, ...]:
    """Capture existing fill declarations while the run snapshot is loaded."""
    if run_root is None:
        return ()
    found: list[str] = []
    fenced = False
    for line in plan_text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or not line.startswith("fill:"):
            continue
        declared = line[5:].strip().split()[0].rstrip(",") if line[5:].strip() else ""
        if not declared:
            continue
        candidate = Path(declared)
        bases = (
            [candidate] if candidate.is_absolute()
            else [run_root / candidate, Path.cwd() / candidate]
        )
        if any(base.is_file() for base in bases) and declared not in found:
            found.append(declared)
    return tuple(found)


def _read_optional_run_facts(run_root: Path | None) -> _OptionalRunFacts:
    """Load optional vNext artifacts into one immutable snapshot."""
    if run_root is None:
        return _OptionalRunFacts()

    plan_text, plan_error = _read_text("plan", run_root / "plan.md")
    profile = parse_run_profile(plan_text) if plan_text else None

    entries: tuple[DDEntry, ...] = ()
    report_text = ""
    report = run_root / "decision-report.md"
    report_text, report_error = _read_text("decision_report", report)
    if report_text:
        entries = tuple(parse_dd_entries(report_text))

    shaping_events: tuple[dict[str, Any], ...] | None = None
    shaping_error: str | None = None
    shaping_log = run_root / "shaping" / "shaping-log.jsonl"
    try:
        if shaping_log.is_file():
            shaping_events = tuple(
                parse_shaping_log(shaping_log.read_text(encoding="utf-8"))
            )
    except (OSError, UnicodeError, ShapingLogError) as exc:
        shaping_events = None
        shaping_error = str(exc)
    craft_guard_text, craft_error = _read_text(
        "craft_guard", run_root / "craft-guard.md"
    )
    errors = tuple(error for error in (plan_error, report_error, craft_error) if error)
    return _OptionalRunFacts(
        plan_text=plan_text,
        run_profile=profile,
        decision_report_text=report_text,
        decision_entries=entries,
        shaping_events=shaping_events,
        shaping_error=shaping_error,
        craft_guard_text=craft_guard_text,
        read_errors=errors,
    )


def _error_state(error: ArtifactReadFact | None) -> str:
    if error is None:
        return STATE_COMPLETE
    if error.code == STATE_MISSING:
        return STATE_MISSING
    return STATE_UNREADABLE


def _artifact_states(
    run_root: Path | None,
    spec_path: Path | None,
    spec_error: ArtifactReadFact | None,
    pointback_path: Path | None,
    pointback_error: ArtifactReadFact | None,
    optional_errors: tuple[ArtifactReadFact, ...],
    *,
    manifest_state: str,
    baseline_text: str | None,
    baseline_error: str | None,
    shaping_events: tuple[dict[str, Any], ...] | None,
    shaping_error: str | None,
    run_profile: RunProfile | None,
) -> tuple[tuple[str, str], ...]:
    """One uniform presence fact per run artifact, captured while loading.

    ``spec``/``point_back`` record no read error when no path was selected,
    so their absence is derived from the path; the optional artifacts always
    produce an error object (missing or unreadable) or none (complete) once
    a run root is probed - without a root they were never read at all.
    """
    states: list[tuple[str, str]] = [
        (
            "spec",
            STATE_MISSING
            if spec_path is None and spec_error is None
            else _error_state(spec_error),
        ),
        (
            "point_back",
            STATE_MISSING
            if pointback_path is None and pointback_error is None
            else _error_state(pointback_error),
        ),
    ]
    by_artifact = {error.artifact: error for error in optional_errors}
    for artifact in ("plan", "decision_report", "craft_guard"):
        error = by_artifact.get(artifact)
        if error is None and run_root is None:
            states.append((artifact, STATE_MISSING))
        else:
            states.append((artifact, _error_state(error)))
    plan_state = next(state for name, state in states if name == "plan")
    if plan_state != STATE_COMPLETE:
        profile_state = plan_state
    elif run_profile is None:
        profile_state = STATE_MISSING
    else:
        profile_state = STATE_COMPLETE
    if run_root is None:
        shaping_state = STATE_MISSING
        baseline_state = STATE_MISSING
    else:
        if shaping_error:
            shaping_state = STATE_UNREADABLE
        elif shaping_events is None:
            shaping_state = STATE_MISSING
        else:
            shaping_state = STATE_COMPLETE
        if baseline_error:
            baseline_state = STATE_UNREADABLE
        elif baseline_text is None:
            baseline_state = STATE_MISSING
        else:
            baseline_state = STATE_COMPLETE
    states.extend(
        (
            ("manifest", manifest_state),
            ("baseline", baseline_state),
            ("shaping", shaping_state),
            ("run_profile", profile_state),
        )
    )
    return tuple(states)


def capture_run_facts(
    *,
    spec_path: Path | None = None,
    pointback_path: Path | None = None,
    preview_dir: Path | None = None,
    evidence_dir: Path | None = None,
    run_root: Path | None = None,
    pointback_fallback_encoding: str | None = None,
) -> RunFacts:
    """Load a run once and return syntax/integrity facts over that snapshot."""

    if run_root is not None:
        if spec_path is None:
            spec_path = next(
                (run_root / name for name in ("spec.md", "01-spec.md")
                 if (run_root / name).is_file()),
                None,
            )
        if pointback_path is None:
            pointback_path = run_root / "point-back.md"
        if preview_dir is None:
            preview_dir = run_root / "preview"
        if evidence_dir is None:
            evidence_dir = run_root / "evidence"

    spec_text, spec_error = _read_text("spec", spec_path)
    pointback_text, pointback_error = _read_text(
        "point_back",
        pointback_path,
        fallback_encoding=pointback_fallback_encoding,
    )
    baseline_text, baseline_error = _read_baseline(run_root)
    manifest_lines, manifest_errors, manifest_state = _read_manifest(evidence_dir)
    preview = inspect_preview(preview_dir) if preview_dir is not None else None
    optional = _read_optional_run_facts(run_root)
    return RunFacts(
        run_root=run_root,
        spec_path=spec_path,
        pointback_path=pointback_path,
        preview_dir=preview_dir,
        evidence_dir=evidence_dir,
        spec_text=spec_text,
        pointback_text=pointback_text,
        plan_text=optional.plan_text,
        plan_fill_artifacts=_plan_fill_artifacts(run_root, optional.plan_text),
        craft_guard_text=optional.craft_guard_text,
        ledger=parse_ledger(pointback_text),
        verdict=parse_verdict(pointback_text),
        preview=preview,
        _manifest_lines=manifest_lines,
        existing_paths=_existing_paths(run_root),
        _baseline_text=baseline_text,
        baseline_state_error=baseline_error,
        read_errors=tuple(
            error
            for error in (spec_error, pointback_error)
            if error is not None
        ) + manifest_errors + tuple(
            error for error in optional.read_errors if error.code != "missing"
        ),
        run_profile=optional.run_profile,
        decision_report_text=optional.decision_report_text,
        decision_entries=optional.decision_entries,
        shaping_events=optional.shaping_events,
        shaping_error=optional.shaping_error,
        _artifact_states=_artifact_states(
            run_root,
            spec_path,
            spec_error,
            pointback_path,
            pointback_error,
            optional.read_errors,
            manifest_state=manifest_state,
            baseline_text=baseline_text,
            baseline_error=baseline_error,
            shaping_events=optional.shaping_events,
            shaping_error=optional.shaping_error,
            run_profile=optional.run_profile,
        ),
    )
