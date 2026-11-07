"""Immutable facts loaded once from a Closed-loop run.

This module owns artifact loading and delegates syntax/integrity parsing to
their existing authorities.  Gate and status modules retain policy: they
project diagnostics and resume narration from one ``RunFacts`` snapshot.
"""
from __future__ import annotations

import hashlib
import importlib.util
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
class BaselineCapture:
    """Explicit project/run authority for one complete-acceptance capture.

    ``state.project_root`` is an identity assertion, never read authority: the
    caller names both roots here and the baseline owner compares them.
    """

    project_root: Path
    run_root: Path


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
    # Reference contract (ADR-0011): None means the run has none — never an
    # operational read error, so absence cannot turn a run red.
    reference_contract_text: str | None = None
    reference_contract_error: str | None = None
    _artifact_states: tuple[tuple[str, str], ...] = ()
    # fill: lines inside fenced blocks are ignored by declaration parsing;
    # kept as a fact so run-status can name them instead of hiding the skip.
    fenced_fill_declarations: tuple[str, ...] = ()
    manifest_raw_text: str = ""
    # Complete-acceptance capture (T-158). ``_baseline_findings`` None means
    # no fresh capture was requested; it never means verified clean. The
    # project/run strings are the resolved identities actually captured, and
    # the digest is sha256 of the exact captured state text.
    _baseline_findings: str | None = None
    baseline_capture_project: str | None = None
    baseline_capture_run: str | None = None
    baseline_capture_state_sha256: str | None = None

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

    @property
    def baseline_state_text(self) -> str | None:
        """Exact captured state text; None when no capture was requested."""
        return self._baseline_text

    @property
    def baseline_findings(self) -> dict[str, Any] | None:
        """Detached baseline findings payload; None = never captured."""
        if self._baseline_findings is None:
            return None
        return json.loads(self._baseline_findings)

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

    @property
    def plan_fill_declarations(self) -> tuple[str, ...]:
        """All declared Fill tokens, including declarations whose files are missing."""
        return _plan_fill_declarations(self.plan_text)


@dataclass(frozen=True)
class _OptionalRunFacts:
    plan_text: str = ""
    run_profile: RunProfile | None = None
    decision_report_text: str = ""
    decision_entries: tuple[DDEntry, ...] = ()
    shaping_events: tuple[dict[str, Any], ...] | None = None
    shaping_error: str | None = None
    craft_guard_text: str = ""
    reference_contract_text: str | None = None
    reference_contract_error: str | None = None
    read_errors: tuple[ArtifactReadFact, ...] = ()
    plan_probed: bool = False


def _read_manifest(
    evidence_dir: Path | None,
) -> tuple[tuple[str, ...], tuple[ArtifactReadFact, ...], str, str]:
    """(entries, errors, state, raw captured text) for evidence/manifest.jsonl.

    The raw text rides the owner capture (T-042): consumers hash what the
    owner read instead of re-reading the file through a second parser.
    """
    if evidence_dir is None:
        return (), (), STATE_MISSING, ""
    path = evidence_dir / "manifest.jsonl"
    if not path.is_file():
        return (), (), STATE_MISSING, ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return (
            (),
            (ArtifactReadFact("manifest", path, "unreadable", str(exc)),),
            STATE_UNREADABLE,
            "",
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
    return tuple(entries), tuple(errors), STATE_COMPLETE, text


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


def _read_baseline_strict(
    run_root: Path | None,
) -> tuple[str | None, str | None]:
    """Complete-acceptance presence read, delegated to the owner entry.

    Kept separate from ``_read_baseline`` so status/aggregate retain the
    historical reader and its bounded behavior. The owner's ``_state_presence``
    is the single presence/type/containment/capped-read rule; a read failure
    or an oversized state is an error, never "absent".
    """
    if run_root is None:
        return None, None
    try:
        return _design_baseline_owner()._state_presence(run_root)
    except RuntimeError as error:
        return None, str(error)


_BASELINE_OWNER: Any | None = None


def _design_baseline_owner() -> Any:
    """Load the design-baseline skill payload once (skill payload is SSOT).

    The owner ships beside ``scripts/`` in the package root, so it is resolved
    relative to this file: never from state content, the caller's cwd, or an
    ancestor search.
    """
    global _BASELINE_OWNER
    if _BASELINE_OWNER is None:
        path = (
            Path(__file__).resolve().parents[1]
            / "skills" / "design-baseline" / "scripts" / "design_baseline.py"
        )
        spec = importlib.util.spec_from_file_location(
            "design_baseline_owner", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"design-baseline owner is not loadable: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _BASELINE_OWNER = module
    return _BASELINE_OWNER


def _capture_baseline(
    capture: BaselineCapture,
) -> tuple[
    str | None, str | None, str | None, str | None, str | None, str | None
]:
    """Capture one verified baseline result through the skill-payload owner.

    Returns ``(state_text, state_error, findings_json, project, run, digest)``.
    The owner's optional capture reads ``state.json`` exactly once and reports
    absence as an explicit ``None`` payload; text, findings, identity, and
    digest therefore come from the same read. Absent state is all-``None`` (no
    baseline, no obligation). Any collection, identity, or payload failure
    becomes ``state_error`` so complete acceptance fails closed instead of
    reading as verified clean.
    """
    try:
        captured = _design_baseline_owner().capture_optional(
            capture.project_root, capture.run_root)
    except RuntimeError as error:
        # BaselineError subclasses RuntimeError; a broken install raises the
        # same way. Both must block, never disappear.
        return None, str(error), None, None, None, None
    if captured is None:
        # True absence: no baseline, no obligation.
        return None, None, None, None, None, None
    findings = captured.get("findings") if isinstance(captured, dict) else None
    state_text = captured.get("state_text") if isinstance(captured, dict) else None
    if not isinstance(findings, dict) or not isinstance(state_text, str):
        return None, "baseline capture returned no findings payload", None, None, None, None
    return (
        state_text,
        None,
        json.dumps(findings, ensure_ascii=False, sort_keys=True),
        str(capture.project_root.resolve()),
        str(capture.run_root.resolve()),
        hashlib.sha256(state_text.encode("utf-8")).hexdigest(),
    )


def _read_reference_contract(
    run_root: Path | None,
) -> tuple[str | None, str | None]:
    """Read ``reference/contract.md`` (ADR-0011); absence is ``None, None``.

    Mirrors ``_read_baseline``: a missing or unreadable contract is a fact
    about the run, not an operational read error — a run without reference
    material must stay green.
    """
    if run_root is None:
        return None, None
    path = run_root / "reference" / "contract.md"
    if not path.is_file():
        return None, None
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeError) as exc:
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


def _scan_fill_declarations(
    plan_text: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split column-0 ``fill:`` lines into (declared, ignored-inside-fences).

    Declarations inside fenced blocks are a misdeclaration the plan author
    must fix, not a silent skip: the second tuple feeds the run-status
    diagnostic that names them and states the column-0 unfenced rule.
    """
    found: list[str] = []
    ignored: list[str] = []
    fenced = False
    for line in plan_text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not line.startswith("fill:"):
            continue
        declared = line[5:].strip().split()[0].rstrip(",") if line[5:].strip() else ""
        if not declared:
            continue
        target = ignored if fenced else found
        if declared not in target:
            target.append(declared)
    return tuple(found), tuple(ignored)


def _plan_fill_declarations(plan_text: str) -> tuple[str, ...]:
    """Capture every unfenced plan Fill token without checking filesystem state."""
    return _scan_fill_declarations(plan_text)[0]


def resolve_declared_fill(run_root: Path, declared: str) -> Path | None:
    """Resolve one declared Fill token: absolute as-is, else run-root first, then cwd."""
    candidate = Path(declared)
    bases = (
        [candidate] if candidate.is_absolute()
        else [run_root / candidate, Path.cwd() / candidate]
    )
    for base in bases:
        if base.is_file():
            return base
    return None


def _plan_fill_artifacts(
    run_root: Path | None,
    declared: tuple[str, ...],
) -> tuple[str, ...]:
    """Capture existing fill declarations while the run snapshot is loaded."""
    if run_root is None:
        return ()
    return tuple(
        token
        for token in declared
        if resolve_declared_fill(run_root, token) is not None
    )


def _read_optional_run_facts(
    run_root: Path | None, plan_path: Path | None = None
) -> _OptionalRunFacts:
    """Load optional vNext artifacts into one immutable snapshot."""
    if plan_path is not None:
        plan_file: Path | None = plan_path
    elif run_root is not None:
        plan_file = run_root / "plan.md"
    else:
        plan_file = None
    plan_text, plan_error = _read_text("plan", plan_file)
    profile = parse_run_profile(plan_text) if plan_text else None
    if run_root is None:
        return _OptionalRunFacts(
            plan_text=plan_text,
            run_profile=profile,
            read_errors=tuple(
                error for error in (plan_error,) if error is not None
            ),
            plan_probed=plan_file is not None,
        )

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
    reference_text, reference_error = _read_reference_contract(run_root)
    errors = tuple(error for error in (plan_error, report_error, craft_error) if error)
    return _OptionalRunFacts(
        plan_text=plan_text,
        run_profile=profile,
        decision_report_text=report_text,
        decision_entries=entries,
        shaping_events=shaping_events,
        shaping_error=shaping_error,
        craft_guard_text=craft_guard_text,
        reference_contract_text=reference_text,
        reference_contract_error=reference_error,
        read_errors=errors,
        plan_probed=plan_file is not None,
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
    plan_probed: bool,
) -> tuple[tuple[str, str], ...]:
    """One uniform presence fact per run artifact, captured while loading.

    ``spec``/``point_back`` record no read error when no path was selected,
    so their absence is derived from the path; the optional artifacts always
    produce an error object (missing or unreadable) or none (complete) once
    probed.
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
    states.append(
        (
            "plan",
            _error_state(by_artifact.get("plan"))
            if plan_probed
            else STATE_MISSING,
        )
    )
    for artifact in ("decision_report", "craft_guard"):
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
    else:
        if shaping_error:
            shaping_state = STATE_UNREADABLE
        elif shaping_events is None:
            shaping_state = STATE_MISSING
        else:
            shaping_state = STATE_COMPLETE
    # Baseline presence follows the baseline read itself: it may come from an
    # explicit baseline_run_root when complete acceptance omits --run-root.
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
    plan_path: Path | None = None,
    pointback_fallback_encoding: str | None = None,
    baseline_capture: BaselineCapture | None = None,
    baseline_run_root: Path | None = None,
) -> RunFacts:
    """Load a run once and return syntax/integrity facts over that snapshot.

    ``plan_path`` selects the plan read location without widening run-root
    discovery: it never changes ``run_root`` and never probes preview,
    evidence, craft, shaping, or decision artifacts on its own.

    ``baseline_capture`` is the explicit complete-acceptance request: the
    baseline owner reads and verifies the present state once, and its exact
    text plus findings payload are frozen here. Without it the default stays
    the state-only read (status, aggregate, legacy, selective callers).

    ``baseline_run_root`` is a deliberately narrow exception for complete
    acceptance without ``--run-root``: it names where the state file may be
    *probed for presence*, without widening any other optional artifact
    discovery or authorizing the project. It never reads DESIGN.md or
    provenance sources.
    """

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
    baseline_findings_text: str | None = None
    baseline_capture_project: str | None = None
    baseline_capture_run: str | None = None
    baseline_capture_state_sha256: str | None = None
    if baseline_capture is None:
        if baseline_run_root is not None:
            # Complete acceptance: absent is the only silent presence state;
            # non-files, dangling links, and read failures are present-invalid.
            baseline_text, baseline_error = _read_baseline_strict(
                baseline_run_root)
        else:
            baseline_text, baseline_error = _read_baseline(run_root)
    else:
        (
            baseline_text,
            baseline_error,
            baseline_findings_text,
            baseline_capture_project,
            baseline_capture_run,
            baseline_capture_state_sha256,
        ) = _capture_baseline(baseline_capture)
    manifest_lines, manifest_errors, manifest_state, manifest_raw = _read_manifest(evidence_dir)
    preview = inspect_preview(preview_dir) if preview_dir is not None else None
    optional = _read_optional_run_facts(run_root, plan_path)
    plan_declared, plan_fenced = _scan_fill_declarations(optional.plan_text)
    return RunFacts(
        run_root=run_root,
        spec_path=spec_path,
        pointback_path=pointback_path,
        preview_dir=preview_dir,
        evidence_dir=evidence_dir,
        spec_text=spec_text,
        pointback_text=pointback_text,
        plan_text=optional.plan_text,
        plan_fill_artifacts=_plan_fill_artifacts(run_root, plan_declared),
        fenced_fill_declarations=plan_fenced,
        manifest_raw_text=manifest_raw,
        craft_guard_text=optional.craft_guard_text,
        ledger=parse_ledger(pointback_text),
        verdict=parse_verdict(pointback_text),
        preview=preview,
        _manifest_lines=manifest_lines,
        existing_paths=_existing_paths(run_root),
        _baseline_text=baseline_text,
        baseline_state_error=baseline_error,
        _baseline_findings=baseline_findings_text,
        baseline_capture_project=baseline_capture_project,
        baseline_capture_run=baseline_capture_run,
        baseline_capture_state_sha256=baseline_capture_state_sha256,
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
        reference_contract_text=optional.reference_contract_text,
        reference_contract_error=optional.reference_contract_error,
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
            plan_probed=optional.plan_probed,
        ),
    )
