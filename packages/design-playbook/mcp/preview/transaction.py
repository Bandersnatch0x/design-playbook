"""Durable Preview decision authority and artifact transaction.

Browser collectors return authenticated submission data. This module owns the
orchestration for one Preview decision: request binding, choice authority,
commit, recovery, projections and result construction. The lock machinery lives
in locking.py and the entry/ledger record IO in entry_io.py; both are imported
into this namespace and re-exported from here, so every current importer of
`transaction` keeps working unchanged.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Protocol

from design_playbook.mcp.preview import ledger
from design_playbook.mcp.preview.control import _format_feedback
from design_playbook.mcp.preview.i18n import CONFIRM_LABELS, SKIP_LABELS
from design_playbook.mcp.preview.live_route import observe_visual_source, validate_live_route_url
from design_playbook.mcp.preview.visual_handoff import build_agent_handoff
from design_playbook.mcp.preview.visual_batch import (
    has_effective_visual_edits,
)
from design_playbook.mcp.preview.integrity import (
    binding_equivalent,
    compute_binding_digest,
    confirm_name,
    decision_name,
    evaluate_feedback_floor,
)
from design_playbook.mcp.util import now_iso as _now_iso
from design_playbook.mcp.preview.preview_request import (
    _criteria_from_report_ref,
    _criteria_review_from_submission,
    _ensure_prototype,
    _preview_dir_for,
    _resolve_prototype,
    self_check_floor as self_check_floor,
)
# Re-exports: the error vocabulary, the record IO and the lock machinery. The
# importers below and the tests that patch these targets keep going through this
# module, so the names are bound here rather than reached through their modules.
from design_playbook.mcp.preview.transaction_errors import (  # noqa: F401
    ConfirmRecordError,
    DirectoryLockError,
    PreviewTransactionError,
    TransactionConflict,
)
from design_playbook.mcp.preview.entry_io import (  # noqa: F401
    _REPLACE_RETRY_ATTEMPTS,
    _REPLACE_RETRY_SECONDS,
    _confirm_record,
    _ledger_record,
    _round_from_path,
    ENTRY_SCHEMA_VERSION,
    atomic_write,
    json_text,
    load_confirm_for_entry,
    load_entry,
    render_log,
    valid_entries,
)
from design_playbook.mcp.preview.locking import (  # noqa: F401
    DIRECTORY_LOCK_HEARTBEAT_SECONDS,
    DIRECTORY_LOCK_POLL_SECONDS,
    DIRECTORY_LOCK_STALE_SECONDS,
    DIRECTORY_LOCK_TIMEOUT_SECONDS,
    LOCK_HEARTBEAT_SECONDS,
    LOCK_STALE_SECONDS,
    PROJECTION_LOCK_NAME,
    _claim_stale_lock,
    _directory_lock_is_stale,
    _lock_metadata,
    _lock_owner,
    _release_lock_guard,
    _round_lock,
    _try_acquire_directory_lease,
    _try_lock_guard,
    directory_lock,
)


class BrowserCollector(Protocol):
    def __call__(
        self,
        prototype: Path,
        summary: str,
        options: list[str],
        round_n: int,
        *,
        criteria: list[dict[str, str]],
    ) -> dict[str, Any]:
        ...

def _commit_projections_unlocked(preview_dir: Path, entry: dict[str, Any]) -> str:
    binding = entry["binding"]
    outcome = entry["outcome"]
    confirm_path = preview_dir / confirm_name(binding["round"])
    if confirm_path.is_file():
        try:
            load_confirm_for_entry(preview_dir, entry, allow_legacy=False)
        except ConfirmRecordError as exc:
            raise TransactionConflict(
                f"{exc}; use next round: {confirm_path}",
                retryable=False, round_n=int(binding["round"]),
                decision_id=str(entry["decision_id"]), artifact=str(confirm_path),
            ) from exc
    elif outcome["user_confirmed"]:
        atomic_write(confirm_path, json_text(_confirm_record(entry)))
    if outcome["user_confirmed"]:
        confirm_result = str(confirm_path)
    else:
        confirm_result = ""
    # Historical version files remain visible in log.md through the dedicated
    # compatibility owner (ADR-0027).
    from design_playbook.mcp.preview.compatibility import render_versions_log
    decision_log = render_log(valid_entries(preview_dir))
    atomic_write(
        preview_dir / "log.md",
        render_versions_log(preview_dir, decision_log),
    )
    return confirm_result

def _commit_projections(preview_dir: Path, entry: dict[str, Any]) -> str:
    binding = entry["binding"]
    try:
        with directory_lock(preview_dir, PROJECTION_LOCK_NAME):
            return _commit_projections_unlocked(preview_dir, entry)
    except DirectoryLockError as exc:
        raise PreviewTransactionError(
            f"Preview projection lock failed: {exc}",
            retryable=True,
            round_n=int(binding["round"]),
            decision_id=str(entry["decision_id"]),
            artifact=str(preview_dir / PROJECTION_LOCK_NAME),
        ) from exc

def _result(entry: dict[str, Any], confirm_path: str) -> dict[str, Any]:
    binding = entry["binding"]
    outcome = entry["outcome"]
    result = {
        "confirmed": outcome["confirmed"],
        "floor_pass": outcome["floor_pass"],
        "selected_options": list(outcome["selected_options"]),
        "feedback": outcome["feedback"],
        "anchors": list(outcome["anchors"]),
        "round": binding["round"],
        "confirm_record_path": confirm_path,
        "aborted": outcome["aborted"],
        "skipped": bool(outcome.get("skipped")),
        "timeout": bool(outcome.get("timeout")),
        "decision_id": entry["decision_id"],
    }
    if outcome.get("criteria_review"):
        result["criteria_review"] = list(outcome["criteria_review"])
    if outcome.get("visual_edits"):
        result["visual_edits"] = dict(outcome["visual_edits"])
    if outcome.get("visual_edits_error"):
        result["visual_edits_error"] = str(outcome["visual_edits_error"])
    if outcome.get("visual_handoff"):
        result["visual_handoff"] = dict(outcome["visual_handoff"])
    return result

def run_preview_transaction(
    *,
    path_arg: str | None,
    html: str | None,
    summary: str,
    round_n: int,
    report_ref: str,
    options: list[str],
    collect: BrowserCollector,
    live_route_url: str = "",
) -> dict[str, Any]:
    """Serialize, collect once, or repair one bound Preview decision."""
    live_route_url = validate_live_route_url(live_route_url) if live_route_url else ""
    summary = summary.strip()
    report_ref = report_ref.strip()
    preview_dir = _preview_dir_for(Path(path_arg) if path_arg else None)
    criteria = _criteria_from_report_ref(report_ref)
    _prototype, prototype_hash = _resolve_prototype(
        path_arg, html, round_n, preview_dir,
    )
    binding = compute_binding_digest(
        round_n=round_n, prototype_html_hash=prototype_hash,
        report_ref=report_ref, summary=summary, options=options,
        route_url=live_route_url,
    )
    entry_path = preview_dir / decision_name(round_n)
    existing = load_entry(entry_path)
    decision_id = str(existing.get("decision_id") if existing else uuid.uuid4().hex)
    try:
        with _round_lock(
            preview_dir, round_n=round_n,
            binding_digest=binding["digest"], decision_id=decision_id,
        ):
            return _run_locked(
                path_arg=path_arg, html=html, summary=summary, round_n=round_n,
                report_ref=report_ref, options=options, collect=collect,
                criteria=criteria,
                preview_dir=preview_dir, prototype_hash=prototype_hash,
                binding=binding, decision_id=decision_id, live_route_url=live_route_url,
            )
    except PreviewTransactionError:
        raise
    except OSError as exc:
        confirm_path = preview_dir / confirm_name(round_n)
        log_path = preview_dir / "log.md"
        if not entry_path.is_file():
            artifact = entry_path
        else:
            entry = load_entry(entry_path)
            needs_confirm = bool(entry and entry["outcome"].get("user_confirmed"))
            if needs_confirm and not confirm_path.is_file():
                artifact = confirm_path
            else:
                artifact = log_path
        raise PreviewTransactionError(
            f"Preview persistence incomplete: {exc}", retryable=True,
            round_n=round_n, decision_id=decision_id, artifact=str(artifact),
        ) from exc

def _floor_verdict(
    *, rejected: bool, submission: dict[str, Any], timed_out: bool, is_skip: bool,
    raw_feedback: str, anchors: list[dict[str, Any]], has_visual_edits: bool,
) -> tuple[bool, str]:
    """The ADR-0008 floor decision for one submission: (floor_pass, floor_failure).

    Rejected and timed-out submissions never pass; a skip is an explicit exempt
    pass; anything else goes through the authoritative floor, where a validated
    visual batch that really changes a value can stand in for notes.
    """
    if rejected:
        return False, str(submission.get("floor_failure") or "")
    if timed_out:
        return False, "preview timed out waiting for user input"
    if is_skip:
        return True, ""
    floor = evaluate_feedback_floor(
        raw_feedback, anchors, has_visual_edits=has_visual_edits
    )
    return floor.passed, floor.reason

def _run_locked(
    *, path_arg: str | None, html: str | None, summary: str, round_n: int,
    report_ref: str, options: list[str], collect: BrowserCollector,
    criteria: list[dict[str, str]],
    preview_dir: Path, prototype_hash: str, binding: dict[str, Any],
    decision_id: str, live_route_url: str = "",
) -> dict[str, Any]:
    entry_path = preview_dir / decision_name(round_n)
    # Re-resolve inside the lock to detect TOCTOU: if the path-mode file
    # changed between run_preview_transaction and lock acquisition, the
    # recomputed hash will not match binding["digest"].
    _prototype, locked_hash = _resolve_prototype(
        path_arg, html, round_n, preview_dir,
    )
    if locked_hash != prototype_hash:
        raise TransactionConflict(
            "prototype changed between binding and lock acquisition",
            retryable=False, round_n=round_n, decision_id=decision_id,
            artifact=str(_prototype),
        )

    existing = load_entry(entry_path)
    if existing is not None:
        # The bound live-route URL is inside the digest, so a replay of a
        # committed round does not touch the network: an unchanged request
        # returns the record and a changed one is a binding conflict.
        # A pre-live-route record and a static replay are the same request
        # (both mean "no live route") and repair from the record instead.
        if not binding_equivalent(existing["binding"], binding):
            raise TransactionConflict(
                f"round binding differs from durable decision; use next round: {round_n}",
                retryable=False, round_n=round_n,
                decision_id=str(existing["decision_id"]), artifact=str(entry_path),
            )
        # T-086: repair the run-external registration if a crash landed
        # between the entry write and the ledger append (append-only, idempotent).
        ledger.append_record(preview_dir, _ledger_record(existing))
        confirm_path = _commit_projections(preview_dir, existing)
        return _result(existing, confirm_path)

    legacy_confirm = preview_dir / confirm_name(round_n)
    if legacy_confirm.is_file():
        raise TransactionConflict(
            f"legacy confirm cannot be overwritten; use next round: {legacy_confirm}",
            retryable=False, round_n=round_n, decision_id=decision_id,
            artifact=str(legacy_confirm),
        )

    prototype = _ensure_prototype(path_arg, html, round_n, preview_dir)
    collect_options: dict[str, Any] = {"criteria": criteria}
    if live_route_url:
        collect_options["live_route_url"] = live_route_url
    submission = collect(prototype, summary, options, round_n, **collect_options)
    anchors = list(submission.get("anchors") or [])
    raw_feedback = str(submission.get("feedback") or "")
    feedback = _format_feedback(raw_feedback, anchors)
    criteria_review = _criteria_review_from_submission(submission, criteria)
    visual_edits = submission.get("visual_edits")
    if not isinstance(visual_edits, dict):
        visual_edits = {}
    visual_edits_error = str(submission.get("visual_edits_error") or "")
    visual_handoff: dict[str, Any] = {}
    if visual_edits.get("edits") and not visual_edits_error:
        try:
            visual_handoff = build_agent_handoff(
                visual_edits,
                # The browser collector validated the batch against a source
                # it observed live; re-observing here would be a second fetch
                # inside the same round and could only race itself.
                current_source_hash=(
                    str(submission.get("visual_source_hash") or "")
                    or observe_visual_source(prototype, live_route_url)
                ),
                route_url=live_route_url,
            )
        except (ValueError, OSError) as exc:
            visual_edits_error = str(exc)
    # ADR-0008 amendment (2026-10-08): only a batch that validated against the
    # current source/route and whose net effect actually changes a value can
    # stand in for notes. A no-op or fully undone chain must not confirm.
    visual_edits_effective = bool(visual_handoff) and has_effective_visual_edits(visual_edits)
    rejected = bool(submission.get("rejected"))
    aborted = bool(submission.get("aborted"))
    # T-086: a collect timeout is a system state, never user feedback —
    # it must not be fed to the ADR-0008 floor (the "timeout waiting for
    # user" text previously passed the floor as if the user wrote it).
    timed_out = bool(submission.get("timeout"))
    choice = str(submission.get("choice") or "")
    selected = [] if aborted or rejected or not choice else [choice]

    confirm_labels = {label.casefold() for label in CONFIRM_LABELS}
    skip_labels = {label.casefold() for label in SKIP_LABELS}
    # A skip is an explicit exempt pass (ADR-0008 amendment): never a
    # confirm, the floor is not evaluated against it, and it never
    # satisfies G5 on its own - no confirm record is written.
    is_skip = choice.casefold() in skip_labels
    user_confirmed = (
        not aborted and not rejected and choice.casefold() in confirm_labels
    )
    floor_pass, floor_failure = _floor_verdict(
        rejected=rejected,
        submission=submission,
        timed_out=timed_out,
        is_skip=is_skip,
        raw_feedback=raw_feedback,
        anchors=anchors,
        has_visual_edits=visual_edits_effective,
    )
    confirmed = user_confirmed and floor_pass

    served_hash = str(submission.get("prototype_html_hash") or prototype_hash)
    if served_hash != prototype_hash:
        raise TransactionConflict(
            "served prototype hash differs from request binding",
            retryable=False, round_n=round_n, decision_id=decision_id,
            artifact=str(prototype),
        )
    entry = {
        "schema_version": ENTRY_SCHEMA_VERSION,
        "decision_id": decision_id,
        "timestamp": _now_iso(),
        "prototype_mode": "path" if path_arg else "html",
        "prototype_path": str(prototype),
        "binding": binding,
        "outcome": {
            "confirmed": confirmed,
            "user_confirmed": user_confirmed,
            "floor_pass": floor_pass,
            "floor_failure": floor_failure,
            "selected_options": selected,
            "feedback": feedback,
            "anchors": anchors,
            "aborted": aborted,
            "rejected": rejected,
            "rejection": str(submission.get("rejection") or ""),
            "skipped": is_skip,
            "timeout": timed_out,
            "visual_edits": visual_edits,
            "visual_edits_error": visual_edits_error,
        },
    }
    # Only a real handoff is recorded: an absent batch must not add an empty
    # `visual_handoff` key to every decision entry (artifact parity).
    if visual_handoff:
        entry["outcome"]["visual_handoff"] = visual_handoff
    if criteria_review:
        entry["outcome"]["criteria_review"] = criteria_review
    atomic_write(entry_path, json_text(entry))
    # T-086: register the committed round outside the run tree so the
    # G5 gate survives records being moved/renamed/deleted from preview/.
    ledger.append_record(preview_dir, _ledger_record(entry))
    confirm_path = _commit_projections(preview_dir, entry)
    return _result(entry, confirm_path)
