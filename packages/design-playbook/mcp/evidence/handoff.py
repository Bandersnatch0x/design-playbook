"""Static handoff builder: the Evidence-owned Stage 9 delivery projection.

ADR-0034 fixed three boundaries the first Stage 9 implementation crossed:

- **Ownership/lifecycle** - the handoff is owned here, in the Evidence runtime,
  and is built *after* the review from durable run artifacts. It shares no
  process, port, or shutdown path with ``collect_review``; the "confirm kills
  the browser mid-export" race is gone by construction.
- **Confirmation authority** - ``confirmed`` is read from the durable
  ``confirm-round-*.json`` that ``transaction.py`` persists (ADR-0013), never
  re-derived. The ADR-0008 floor lives inside that record; re-deriving it here
  would be a second confirmation authority, which CONTEXT.md forbids.
- **Capture target** - the five-viewport matrix and the layout probe run
  against the deliverable itself, not against any review chrome.

Artifacts land under the run tree (``<run_root>/evidence/static-handoff/``,
ADR-0026 containment posture), never the process working directory. The
result is regenerable from the run directory alone, which the previous
in-session construction could not do.

Until the conditions above held, ADR-0034 marked ``gatesPassed``/``verdict``
as untrustworthy; this module is what makes them earn back meaning, with one
explicit correction: a conditional gate whose precondition never occurred is
reported ``not-applicable`` and is never counted as a pass.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from design_playbook.mcp.evidence.disclosure import (
    VIEWPORT_ORDER,
    ViewportMetrics,
    build_disclosure,
    build_handoff_zip,
    disclosure_json,
)

# Conditional gates (validate_run.py header; CONTEXT.md G5/G6/G7): a gate whose
# precondition never occurred produces no finding - "not triggered" must not be
# read as "passed". G7 additionally needs contract paths the handoff does not
# wire, so it stays not-applicable until they are.
CONDITIONAL_GATES: tuple[int, ...] = (5, 6, 7, 8)

_GATE_RULE = re.compile(r"^G([1-8])(?:\.|$)")


@dataclass(frozen=True)
class StaticHandoffResult:
    """What ``build_static_handoff`` produced, where."""

    out_dir: Path
    payload: dict[str, Any]
    json_path: Path
    zip_path: Path
    index_html: Path


def _iso_now() -> str:
    """Current timestamp as ``YYYY-MM-DD HH:MM +HH:MM`` (spec §4.2 shape)."""
    return _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def _page_template() -> str:
    """Load the bundled delivery page template (ADR-0009 location rule)."""
    return (Path(__file__).resolve().parent / "static_handoff_page.html").read_text(
        encoding="utf-8"
    )


def _declared_run_tier(run_root: Path) -> str:
    """Return the run's declared tier, or ``""`` when none was declared.

    CONTEXT.md "Tiered run profile": the tier lives in a mandatory run-profile
    block at the top of ``plan.md``. An undeclared tier is reported as unknown
    rather than guessed - the credential may omit a fact, but it may not
    invent one.
    """
    try:
        text = (run_root / "plan.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    try:
        from design_playbook.scripts.run_profile import parse_run_profile
    except ImportError:  # pragma: no cover - packaged runtime always has it
        return ""
    profile = parse_run_profile(text)
    return profile.tier if profile is not None else ""


def _confirmation_from_record(
    run_root: Path, round_n: int
) -> tuple[bool, str]:
    """Report what the durable confirm record says; never derive confirmation.

    Fail-closed: an absent, unreadable, round-mismatched, or invalid record is
    never treated as a confirm.
    """
    from design_playbook.mcp.preview.integrity import inspect_preview

    snapshot = inspect_preview(run_root / "preview")
    record = snapshot.canonical_current_confirm
    if record is None:
        return False, f"no confirm record under {run_root / 'preview'}"
    if record.round != round_n:
        return False, (
            f"confirm record is round {record.round}, handoff round is {round_n}"
        )
    if not record.valid:
        detail = record.prototype_status or "record failed integrity checks"
        return False, f"confirm record not valid: {detail}"
    return True, ""


def _run_gate_validation(run_root: Path) -> dict[str, Any]:
    """Run the canonical validator over one run directory."""
    spec = run_root / "spec.md"
    point_back = run_root / "point-back.md"
    if not spec.is_file() or not point_back.is_file():
        return {
            "available": False,
            "gates_passed": 0,
            "errors": [],
            "warnings": [],
            "error": "spec.md/point-back.md gate input is missing",
        }
    try:
        from design_playbook.scripts import validate_run

        errors, warnings = validate_run.run(
            str(spec),
            str(point_back),
            preview_dir=str(run_root / "preview")
            if (run_root / "preview").is_dir()
            else None,
            decision_report=str(run_root / "decision-report.md")
            if (run_root / "decision-report.md").is_file()
            else None,
            evidence_dir=str(run_root / "evidence")
            if (run_root / "evidence").is_dir()
            else None,
            run_root=str(run_root),
        )
    except (OSError, UnicodeError, ValueError) as exc:
        return {
            "available": False,
            "gates_passed": 0,
            "errors": [],
            "warnings": [],
            "error": f"gate validation failed: {exc}",
        }
    return {
        "available": True,
        "gates_passed": _count_passing_gates(errors),
        "gate_statuses": _gate_statuses_from_findings(errors),
        "errors": list(errors),
        "warnings": warnings,
        "error": "",
    }


def _rule_id(finding: Any) -> str:
    if isinstance(finding, dict):
        return str(finding.get("rule_id", finding.get("ruleId", "")))
    return str(getattr(finding, "rule_id", ""))


def _gate_statuses_from_findings(errors: list[Any]) -> list[str]:
    statuses = ["pass"] * 8
    for finding in errors:
        match = _GATE_RULE.match(_rule_id(finding))
        if match:
            statuses[int(match.group(1)) - 1] = "fail"
    return statuses


def _count_passing_gates(errors: list[Any]) -> int:
    statuses = _gate_statuses_from_findings(errors)
    return sum(1 for state in statuses if state == "pass")


def _normalise_gate_result(raw: Any) -> dict[str, Any]:
    """Normalize canonical/fake gate runner output into one session shape."""

    def _statuses(
        *,
        explicit: Any,
        available: bool,
        passed: int,
        errors: list[Any],
    ) -> list[str]:
        # An unavailable validator cannot prove either a pass or a failure;
        # keep every gate pending even if a malformed runner supplied stale
        # status data alongside ``available=False``.
        if not available:
            return ["pending"] * 8
        if isinstance(explicit, (list, tuple)):
            normalized = [
                str(value).lower()
                if str(value).lower() in {"pass", "fail", "pending"}
                else "pending"
                for value in explicit[:8]
            ]
            statuses = (normalized + ["pending"] * 8)[:8]
        else:
            statuses = ["pending"] * 8
        unknown_error = False
        for finding in errors:
            match = _GATE_RULE.match(_rule_id(finding))
            if match:
                statuses[int(match.group(1)) - 1] = "fail"
            else:
                unknown_error = True
        # A non-canonical error means the validator did not establish a clean
        # eight-gate result. Explicit passes remain useful evidence only when
        # no such unscoped error is present.
        if unknown_error:
            statuses = [state if state == "fail" else "pending" for state in statuses]
        if explicit is not None:
            return statuses
        if (
            available
            and passed == 8
            and not unknown_error
            and not any(state == "fail" for state in statuses)
        ):
            statuses = ["pass"] * 8
        return statuses

    if isinstance(raw, dict):
        invalid = False
        errors_raw = raw.get("errors", [])
        warnings_raw = raw.get("warnings", [])
        if not isinstance(errors_raw, (list, tuple)):
            invalid = True
            errors_raw = []
        if not isinstance(warnings_raw, (list, tuple)):
            invalid = True
            warnings_raw = []
        passed = raw.get("gates_passed", raw.get("gatesPassed", 0))
        if isinstance(passed, bool):
            invalid = True
            passed_int = 0
        else:
            try:
                passed_int = max(0, min(8, int(passed)))
            except (TypeError, ValueError):
                invalid = True
                passed_int = 0
        available = raw.get("available")
        if available is not None and not isinstance(available, bool):
            invalid = True
            available = False
        try:
            explicit = raw.get("gate_statuses", raw.get("gateStatuses"))
            explicit_present = "gate_statuses" in raw or "gateStatuses" in raw
            if explicit_present and not isinstance(explicit, (list, tuple)):
                invalid = True
                explicit = None
            if isinstance(explicit, (list, tuple)):
                valid_values = {"pass", "fail", "pending"}
                if any(str(value).lower() not in valid_values for value in explicit):
                    invalid = True
        except Exception:  # pragma: no cover - defensive against hostile mappings
            invalid = True
            explicit = None
        if available is None:
            available = any(
                key in raw
                for key in ("gates_passed", "gatesPassed", "gate_statuses", "gateStatuses")
            )
        error_text = str(raw.get("error") or "")
        if error_text:
            invalid = True
        error_list = list(errors_raw)
        available_bool = bool(available) and not invalid
        if not available_bool:
            passed_int = 0
        return {
            "available": available_bool,
            "gates_passed": passed_int,
            "gate_statuses": _statuses(
                explicit=explicit,
                available=available_bool,
                passed=passed_int,
                errors=error_list,
            ),
            "errors": error_list,
            "warnings": list(warnings_raw),
            "error": error_text or ("invalid gate runner result" if invalid else ""),
        }
    if isinstance(raw, tuple) and len(raw) == 2:
        errors, warnings = raw
        if not isinstance(errors, (list, tuple)) or not isinstance(warnings, (list, tuple)):
            return {
                "available": False,
                "gates_passed": 0,
                "gate_statuses": ["pending"] * 8,
                "errors": [],
                "warnings": [],
                "error": "invalid gate runner result",
            }
        error_list = list(errors)
        return {
            "available": True,
            "gates_passed": 8 if not error_list else 0,
            "gate_statuses": _statuses(
                explicit=None,
                available=True,
                passed=8 if not error_list else 0,
                errors=error_list,
            ),
            "errors": error_list,
            "warnings": list(warnings),
            "error": "",
        }
    if isinstance(raw, int) and not isinstance(raw, bool):
        return {
            "available": True,
            "gates_passed": max(0, min(8, raw)),
            "gate_statuses": _statuses(
                explicit=None,
                available=True,
                passed=max(0, min(8, raw)),
                errors=[],
            ),
            "errors": [],
            "warnings": [],
            "error": "",
        }
    return {
        "available": False,
        "gates_passed": 0,
        "gate_statuses": ["pending"] * 8,
        "errors": [],
        "warnings": [],
        "error": "gate runner returned an invalid result",
    }


def _gate_preconditions(run_root: Path) -> dict[int, bool]:
    """Which conditional gates had their preconditions at validation time.

    Mirrors validate_run's own conditionality (its header block): G5 fires only
    when preview occurred, G6 only when an evidence ledger binds artifacts, G8
    only when a craft-guard report exists. G7 additionally requires contract
    paths the handoff does not wire.

    G6 keys off ``evidence/manifest.jsonl``, not the bare ``evidence/``
    directory: this builder writes its own output under ``evidence/``, so a
    directory test would let the handoff manufacture its own precondition and
    report an unevaluated G6 as passed. Must be sampled before any artifact is
    written regardless - see the call site.
    """
    from design_playbook.mcp.preview.integrity import inspect_preview

    return {
        5: inspect_preview(run_root / "preview").occurred,
        6: (run_root / "evidence" / "manifest.jsonl").is_file(),
        7: False,
        8: (run_root / "craft-guard.md").is_file(),
    }


def _metric_from_capture(raw: Any, name: str) -> Any:
    """Convert one capture metric to a disclosure value object.

    Capture results cross a trust boundary: an injected runner or a malformed
    adapter must not be able to turn missing fields into reference viewport
    values while retaining ``measurementStatus=measured``. Invalid values are
    therefore represented as zeroed, blocked metrics; the caller can still
    include the diagnostic in the disclosure payload, but it cannot pass the
    capture-complete gate.
    """

    def blocked(error: str) -> ViewportMetrics:
        return ViewportMetrics(
            sw=0,
            innerH=0,
            hOverflow=0,
            inFold=False,
            measurement_status="blocked",
            measurement_error=error,
        )

    def measured_dimension_errors(
        sw: int, inner_h: int, status: str
    ) -> list[str]:
        if status != "measured":
            return []
        errors: list[str] = []
        if sw == 0:
            errors.append("sw is zero for measured metric")
        if inner_h == 0:
            errors.append("innerH is zero for measured metric")
        return errors

    metric = raw.get("metrics") if isinstance(raw, dict) else raw
    if isinstance(metric, ViewportMetrics):
        values = (metric.sw, metric.innerH, metric.hOverflow)
        errors = measured_dimension_errors(metric.sw, metric.innerH, metric.measurement_status)
        if (
            all(type(value) is int and value >= 0 for value in values)
            and type(metric.inFold) is bool
            and metric.measurement_status in {"measured", "unmeasured", "blocked"}
            and isinstance(metric.measurement_error, str)
            and not errors
            and not (
                metric.measurement_status == "measured"
                and metric.measurement_error
            )
        ):
            return metric
        return blocked(
            "; ".join(errors) if errors else "capture metric object has invalid fields"
        )
    if not isinstance(metric, dict):
        return blocked("capture matrix has no metrics")

    status = metric.get("measurementStatus")
    errors: list[str] = []
    if status not in {"measured", "unmeasured", "blocked"}:
        errors.append("measurementStatus is invalid")
        status = "blocked"

    values: list[int] = []
    for key in ("sw", "innerH", "hOverflow"):
        value = metric.get(key)
        if type(value) is not int or value < 0:
            errors.append(f"{key} is not a non-negative integer")
            values.append(0)
        else:
            values.append(value)

    errors.extend(measured_dimension_errors(values[0], values[1], status))

    disclosure = metric.get("disclosure")
    in_fold = disclosure.get("inFold") if isinstance(disclosure, dict) else None
    if type(in_fold) is not bool:
        errors.append("disclosure.inFold is not boolean")
        in_fold = False

    measurement_error = metric.get("measurementError", "")
    if not isinstance(measurement_error, str):
        errors.append("measurementError is not a string")
        measurement_error = ""
    elif status == "measured" and measurement_error:
        errors.append("measured metric carries measurementError")
    if errors:
        status = "blocked"
        measurement_error = "; ".join(errors)

    return ViewportMetrics(
        sw=values[0],
        innerH=values[1],
        hOverflow=values[2],
        inFold=in_fold,
        measurement_status=status,
        measurement_error=measurement_error,
    )


def _capture_screenshot_path(item: Any, name: str, snap_dir: Path) -> Path | None:
    """Return a valid canonical snapshot path, or ``None``.

    The capture runner is an injected integration boundary. Only the exact
    per-viewport file under the snapshot directory is eligible for the
    completion proof and ZIP package. Resolving the supplied path and comparing
    it with the un-resolved canonical path rejects traversal and symlink
    escapes, while the size check prevents an empty placeholder from being
    treated as real visual evidence.
    """
    if not isinstance(item, dict):
        return None
    raw_path = item.get("screenshot")
    if not isinstance(raw_path, (str, Path)) or not str(raw_path):
        return None
    try:
        base = snap_dir.resolve()
        filename = f"viewport-{name}.png"
        # ``name`` normally comes from the fixed viewport contract. Keep this
        # helper defensive if it is ever called with an untrusted value.
        if Path(filename).name != filename:
            return None
        expected = base / filename
        actual = Path(raw_path).resolve()
        if actual != expected or expected.is_symlink() or not expected.is_file():
            return None
        if expected.stat().st_size <= 0:
            return None
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    return actual


def _capture_matrix_completeness(
    matrix: Any, snap_dir: Path
) -> tuple[bool, str]:
    """Validate the complete five-viewport capture evidence contract."""
    if not isinstance(matrix, dict):
        return False, "capture runner returned a non-object matrix"

    errors: list[str] = []
    for name in VIEWPORT_ORDER:
        item = matrix.get(name)
        if not isinstance(item, dict):
            errors.append(f"capture matrix missing viewport {name}")
            continue
        metric = _metric_from_capture(item, name)
        if metric.measurement_status != "measured":
            detail = f": {metric.measurement_error}" if metric.measurement_error else ""
            errors.append(
                f"capture metric for {name} is {metric.measurement_status}{detail}"
            )
        if _capture_screenshot_path(item, name, snap_dir) is None:
            errors.append(f"capture screenshot for {name} is missing or invalid")
    return not errors, "; ".join(errors)


def _decision_records_from_run(
    run_root: Path, round_n: int, summary: str, *, confirmed: bool
) -> list[dict[str, str]]:
    """Normalize the durable round decision into §4.2 ``decisions`` entries.

    Reads ``preview/decision-round-<n>.json`` (the transaction record) for the
    reviewer's actual choice and feedback. Aborted/absent entries fall back to
    the run summary; a truly empty handoff yields an empty list.
    """
    records: list[dict[str, str]] = []
    authority = "confirmed-user" if confirmed else "pending-user"
    choice = ""
    feedback = ""
    entry_path = run_root / "preview" / f"decision-round-{round_n}.json"
    try:
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        entry = None
    if isinstance(entry, dict):
        outcome = entry.get("outcome")
        if isinstance(outcome, dict):
            choice = str(outcome.get("choice") or "")
            feedback = str(outcome.get("feedback") or "")
    if choice:
        records.append(
            {
                "id": f"DD-R{round_n}-01",
                "title": f"Round {round_n} decision: {choice}",
                "authority": authority,
            }
        )
    if feedback:
        records.append(
            {
                "id": f"DD-R{round_n}-02",
                "title": f"Round {round_n} feedback: {feedback[:80]}",
                "authority": authority,
            }
        )
    if not records and summary:
        records.append(
            {
                "id": f"DD-R{round_n}-00",
                "title": f"Round {round_n}: {summary[:80]}",
                "authority": authority,
            }
        )
    return records


def _render_index_html(
    payload: dict[str, Any], matrix: Any, snap_dir: Path
) -> str:
    """Render the delivery page with the payload inlined.

    The page carries the full JSON in a ``<script type="application/json">``
    block and the human-readable summary as static HTML, so it renders from
    disk with no network, no fetch, and no CDN (ADR-0034 §6).
    """

    def _esc(value: Any) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    statuses = payload.get("gateStatuses")
    rows = ""
    if isinstance(statuses, list):
        for index, state in enumerate(statuses[:8], start=1):
            rows += (
                f'<tr><td>G{index}</td><td class="st st-{_esc(state)}">'
                f"{_esc(state)}</td></tr>"
            )
    viewports = payload.get("viewports")
    vp_rows = ""
    if isinstance(viewports, list):
        for vp in viewports:
            if not isinstance(vp, dict):
                continue
            metrics = vp.get("metrics") or {}
            disclosure = metrics.get("disclosure") or {}
            vp_rows += (
                "<tr>"
                f"<td>{_esc(vp.get('name'))}</td>"
                f"<td>{_esc(metrics.get('sw'))}</td>"
                f"<td>{_esc(metrics.get('innerH'))}</td>"
                f"<td>{_esc(metrics.get('hOverflow'))}</td>"
                f"<td>{_esc(disclosure.get('inFold'))}</td>"
                f"<td>{_esc(metrics.get('measurementStatus'))}</td>"
                "</tr>"
            )
    decisions = payload.get("decisions")
    decision_items = ""
    if isinstance(decisions, list):
        for item in decisions:
            if isinstance(item, dict):
                decision_items += (
                    f"<li><code>{_esc(item.get('id'))}</code> "
                    f"{_esc(item.get('title'))} "
                    f"<small>({_esc(item.get('authority'))})</small></li>"
                )
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    # A literal "</script>" inside the payload would close the block early;
    # escape it (and "<" generally) - JSON readers unescape it back.
    payload_json = payload_json.replace("<", "\\u003c")

    snap_figures = ""
    for vp in VIEWPORT_ORDER:
        if isinstance(matrix, dict) and _capture_screenshot_path(
            matrix.get(vp), vp, snap_dir
        ):
            snap_figures += (
                f'<figure><img src="snapshots/viewport-{vp}.png" alt="{vp} snapshot" '
                f'loading="lazy"/><figcaption>viewport-{vp}.png</figcaption></figure>'
            )

    return (
        _page_template()
        .replace("%VERDICT%", _esc(payload.get("verdict")))
        .replace("%VERDICT_LOWERCASE%", _esc(str(payload.get("verdict")).lower()))
        .replace("%RUN_ID%", _esc(payload.get("runId")))
        .replace("%AUTHORITY%", _esc(payload.get("authority")))
        .replace("%PROFILE%", _esc(payload.get("profile")))
        .replace("%TIMESTAMP%", _esc(payload.get("timestamp")))
        .replace("%GATES_PASSED%", _esc(payload.get("gatesPassed")))
        .replace("%CAPTURE_STATUS%", _esc(payload.get("captureStatus")))
        .replace("%CONFIRMATION_NOTE%", _esc(payload.get("confirmationNote") or "—"))
        .replace("%GATE_ROWS%", rows)
        .replace("%VIEWPORT_ROWS%", vp_rows)
        .replace("%DECISION_ITEMS%", decision_items)
        .replace("%SNAPSHOT_FIGURES%", snap_figures)
        .replace("%PAYLOAD_JSON%", payload_json)
    )


def build_static_handoff(
    run_root: Path,
    deliverable: Path,
    *,
    round_n: int = 1,
    summary: str = "",
    capture_runner: Callable[..., Any] | None = None,
    gate_runner: Callable[..., Any] | None = None,
    out_dir: Path | None = None,
) -> StaticHandoffResult:
    """Build the Stage 9 static handoff from durable run artifacts.

    ``run_root`` is the run directory (``.scratch/<run>/``) carrying spec.md,
    point-back.md, preview/, evidence/, plan.md. ``deliverable`` is the Stage 7
    output (``filled-ui.html``) - the page the five-viewport matrix and the
    layout probe actually target (ADR-0034 §4). Everything is written under
    ``<run_root>/evidence/static-handoff/``: snapshots, the disclosure JSON,
    the ZIP package, and a self-contained index page.
    """
    run_root = Path(run_root)
    deliverable = Path(deliverable)
    out_dir = Path(out_dir) if out_dir is not None else run_root / "evidence" / "static-handoff"
    snap_dir = out_dir / "snapshots"

    if capture_runner is None:
        from design_playbook.mcp.evidence.capture_runtime import (
            capture_delivery_matrix,
        )

        capture_runner = capture_delivery_matrix
    if gate_runner is None:
        gate_runner = _run_gate_validation

    # Sample conditional-gate preconditions BEFORE writing anything: this
    # builder's own output lives under evidence/, and a precondition sampled
    # afterwards would be one this run manufactured for itself.
    preconditions = _gate_preconditions(run_root)

    # --- capture: the deliverable itself, never any review chrome ---
    capture_status = "captured"
    capture_error = ""
    matrix: dict[str, Any] = {}
    try:
        matrix = capture_runner(url=deliverable.resolve().as_uri(), out_dir=snap_dir)
        if not isinstance(matrix, dict):
            raise TypeError("capture runner returned a non-object matrix")
        capture_complete, capture_error = _capture_matrix_completeness(
            matrix, snap_dir
        )
        if not capture_complete:
            capture_status = "blocked"
    except Exception as exc:  # noqa: BLE001 - disclose blocked evidence
        matrix = {}
        capture_status = "blocked"
        capture_error = str(exc)

    # --- gates: canonical validation + honest conditionality ---
    try:
        gate = _normalise_gate_result(gate_runner(run_root))
    except Exception as exc:  # noqa: BLE001 - disclose blocked gates
        gate = {
            "available": False,
            "gates_passed": 0,
            "gate_statuses": ["pending"] * 8,
            "errors": [],
            "warnings": [],
            "error": str(exc),
        }
    gate_statuses = list(gate.get("gate_statuses") or ["pending"] * 8)[:8]
    gate_statuses = (gate_statuses + ["pending"] * 8)[:8]
    if gate.get("available"):
        for gate_n in CONDITIONAL_GATES:
            if not preconditions.get(gate_n, True) and gate_statuses[gate_n - 1] != "fail":
                # The validator produced no finding because the gate never
                # had a chance to fire. That is not a pass (ADR-0034 §7).
                gate_statuses[gate_n - 1] = "not-applicable"
    gates_passed = sum(1 for state in gate_statuses if state == "pass")
    gates_resolved = all(state in {"pass", "not-applicable"} for state in gate_statuses)
    # `gatesPassed` reports gate evaluation, which is a fact about artifacts and
    # is independent of whether a human confirmed. The old code zeroed it unless
    # confirmed, which understated real validator results; confirmation is
    # carried by `authority`/`verdict` instead. ADR-0034 §7 scopes this count to
    # gates evaluated *and* passed - `not-applicable` never counts.

    # --- confirmation: the durable record, never re-derived ---
    confirmed, confirmation_reason = _confirmation_from_record(run_root, round_n)

    capture_complete = capture_status == "captured"
    if confirmed and capture_complete and gate.get("available") and gates_resolved:
        verdict = "Pass"
    elif confirmed:
        verdict = "Recirculate"
    else:
        verdict = "Pending"

    deliverable_bytes = deliverable.read_bytes()
    run_id = (
        f"static-handoff-{round_n}-{hashlib.sha256(deliverable_bytes).hexdigest()[:12]}"
    )
    metrics = {
        name: _metric_from_capture(matrix.get(name), name)
        for name in VIEWPORT_ORDER
    } if isinstance(matrix, dict) and matrix else None

    payload = build_disclosure(
        run_id=run_id,
        verdict=verdict,
        profile=_declared_run_tier(run_root) or "unknown",
        authority="confirmed-user" if confirmed else "pending-user",
        timestamp=_iso_now(),
        decisions=_decision_records_from_run(
            run_root, round_n, summary, confirmed=confirmed
        ),
        gates_passed=gates_passed,
        viewport_metrics=metrics,
    )
    # Operational state for the page; JSON and ZIP consume this same object.
    payload["captureStatus"] = capture_status
    if capture_error:
        payload["captureError"] = capture_error
    payload["gateStatus"] = "passed" if verdict == "Pass" else "pending"
    payload["gateStatuses"] = gate_statuses
    payload["confirmationSource"] = "confirm-record" if confirmed else "unsubstantiated"
    if not confirmed:
        payload["confirmationNote"] = confirmation_reason
    gate_error = str(gate.get("error") or "")
    if gate_error:
        payload["gateError"] = gate_error

    # --- write the artifact set ---
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "disclosure-review.json"
    json_path.write_text(disclosure_json(payload), encoding="utf-8")

    artifacts: dict[str, str] = {}
    if snap_dir.is_dir():
        for vp in VIEWPORT_ORDER:
            snap = _capture_screenshot_path(matrix.get(vp), vp, snap_dir)
            if snap is not None:
                artifacts[f"snapshots/viewport-{vp}.png"] = str(snap)
    zip_path = out_dir / "static-handoff.zip"
    build_handoff_zip(
        payload,
        artifact_files=artifacts,
        # spec §4.1: the handoff ships "snapshots and prototype code". PNGs
        # alone do not let the recipient rebuild the reviewed page.
        text_members={"deliverable.html": deliverable_bytes.decode("utf-8")},
        zip_target=str(zip_path),
    )

    index_html = out_dir / "index.html"
    index_html.write_text(
        _render_index_html(payload, matrix, snap_dir), encoding="utf-8"
    )

    return StaticHandoffResult(
        out_dir=out_dir,
        payload=payload,
        json_path=json_path,
        zip_path=zip_path,
        index_html=index_html,
    )
