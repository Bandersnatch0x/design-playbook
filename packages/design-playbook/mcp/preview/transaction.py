"""Preview decision authority and artifact transaction.

Browser collectors return authenticated submission data. This module owns
choice classification, feedback-floor judgment, persistence order, and result
construction for one Preview decision.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from confirm import (
    _append_log,
    _check_feedback_floor,
    _ensure_prototype,
    _preview_dir_for,
    _write_confirm,
    prototype_html_digest,
)
from control import _format_feedback
from i18n import CONFIRM_LABELS

BrowserCollector = Callable[[Path, str, list[str], int], dict[str, Any]]


def run_preview_transaction(
    *,
    path_arg: str | None,
    html: str | None,
    summary: str,
    round_n: int,
    report_ref: str,
    options: list[str],
    collect: BrowserCollector,
) -> dict[str, Any]:
    """Collect and commit one Preview decision using current artifact format."""
    summary = summary.strip()
    report_ref = report_ref.strip()
    preview_dir = _preview_dir_for(Path(path_arg) if path_arg else None)
    prototype = _ensure_prototype(path_arg, html, round_n, preview_dir)

    submission = collect(prototype, summary, options, round_n)
    anchors = list(submission.get("anchors") or [])
    raw_feedback = str(submission.get("feedback") or "")
    feedback = _format_feedback(raw_feedback, anchors)
    rejected = bool(submission.get("rejected"))
    aborted = bool(submission.get("aborted"))
    choice = str(submission.get("choice") or "")
    selected = [] if aborted or rejected or not choice else [choice]

    confirm_labels = {label.casefold() for label in CONFIRM_LABELS}
    user_confirmed = (
        not aborted
        and not rejected
        and choice.casefold() in confirm_labels
    )
    if rejected:
        floor_pass = False
        floor_failure = str(submission.get("floor_failure") or "")
    else:
        floor_pass, floor_failure = _check_feedback_floor(raw_feedback, anchors)
    confirmed = user_confirmed and floor_pass

    confirm_path = ""
    if user_confirmed:
        proto_hash = submission.get("prototype_html_hash")
        if not proto_hash:
            proto_hash = prototype_html_digest(prototype.read_bytes())
        out = _write_confirm(
            preview_dir,
            round_n=round_n,
            report_ref=report_ref,
            selected=selected,
            feedback=feedback,
            prototype_html_hash=str(proto_hash),
            confirmed=confirmed,
            floor_pass=floor_pass,
            floor_failure=floor_failure,
        )
        confirm_path = str(out)

    _append_log(
        preview_dir,
        round_n=round_n,
        report_ref=report_ref,
        feedback=feedback,
        aborted=aborted,
        selected=selected,
        anchors=anchors,
        floor_pass=floor_pass,
        floor_failure=floor_failure,
        rejected=rejected,
        rejection=str(submission.get("rejection") or ""),
    )
    return {
        "confirmed": confirmed,
        "floor_pass": floor_pass,
        "selected_options": selected,
        "feedback": feedback,
        "anchors": anchors,
        "round": round_n,
        "confirm_record_path": confirm_path,
        "aborted": aborted,
    }
