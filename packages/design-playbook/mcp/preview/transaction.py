"""Durable Preview decision authority and artifact transaction.

Browser collectors return authenticated submission data. This module owns
request binding, choice authority, atomic persistence, recovery, projections,
and result construction for one Preview decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from confirm import (
    _check_feedback_floor,
    _ensure_prototype,
    _preview_dir_for,
    prototype_html_digest,
)
from control import _format_feedback
from i18n import CONFIRM_LABELS
from util import _now_iso

BrowserCollector = Callable[[Path, str, list[str], int], dict[str, Any]]
ENTRY_SCHEMA_VERSION = 1


class PreviewTransactionError(ValueError):
    """Recoverable transaction failure with actionable artifact context."""

    def __init__(
        self, message: str, *, retryable: bool, round_n: int,
        decision_id: str, artifact: str,
    ) -> None:
        super().__init__(message)
        self.details = {
            "error": "preview_transaction",
            "message": message,
            "retryable": retryable,
            "round": round_n,
            "decision_id": decision_id,
            "artifact": artifact,
        }


class TransactionConflict(PreviewTransactionError):
    """Existing same-round authority cannot be replaced by this request."""


LOCK_HEARTBEAT_SECONDS = 30
LOCK_STALE_SECONDS = LOCK_HEARTBEAT_SECONDS * 3


def _lock_metadata(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _claim_stale_lock(
    path: Path, *, binding_digest: str, round_n: int, decision_id: str,
) -> None:
    """Serialize stale takeover so one recoverer cannot delete another's lock."""
    guard = path.with_suffix(path.suffix + ".recovery")
    try:
        fd = os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PreviewTransactionError(
            f"Preview round {round_n} recovery is already active",
            retryable=True, round_n=round_n, decision_id=decision_id,
            artifact=str(guard),
        ) from exc
    os.close(fd)
    try:
        existing = _lock_metadata(path)
        try:
            age = time.time() - path.stat().st_mtime
        except FileNotFoundError:
            return
        if age < LOCK_STALE_SECONDS:
            raise PreviewTransactionError(
                f"Preview round {round_n} is already active",
                retryable=True, round_n=round_n,
                decision_id=str(existing.get("decision_id") or decision_id),
                artifact=str(path),
            )
        if existing.get("binding_digest") != binding_digest:
            raise TransactionConflict(
                f"stale lock binding differs; use next round: {round_n}",
                retryable=False, round_n=round_n,
                decision_id=str(existing.get("decision_id") or decision_id),
                artifact=str(path),
            )
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    finally:
        try:
            guard.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def _round_lock(
    preview_dir: Path, *, round_n: int, binding_digest: str, decision_id: str,
) -> Iterator[None]:
    preview_dir.mkdir(parents=True, exist_ok=True)
    path = preview_dir / f"decision-round-{round_n}.lock"
    owner_id = uuid.uuid4().hex
    metadata = {
        "owner_id": owner_id,
        "decision_id": decision_id,
        "binding_digest": binding_digest,
        "heartbeat": time.time(),
    }
    raw = json.dumps(metadata, sort_keys=True)
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            _claim_stale_lock(
                path, binding_digest=binding_digest,
                round_n=round_n, decision_id=decision_id,
            )
            continue
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(raw)
                fh.flush()
            break

    stopped = threading.Event()
    heartbeat_errors: list[OSError] = []

    def heartbeat() -> None:
        while not stopped.wait(LOCK_HEARTBEAT_SECONDS):
            current = _lock_metadata(path)
            if current.get("owner_id") != owner_id:
                return
            metadata["heartbeat"] = time.time()
            try:
                _atomic_write(path, json.dumps(metadata, sort_keys=True))
            except OSError as exc:
                heartbeat_errors.append(exc)
                return

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        yield
        if heartbeat_errors:
            raise PreviewTransactionError(
                f"Preview lock heartbeat failed: {heartbeat_errors[0]}",
                retryable=True, round_n=round_n, decision_id=decision_id,
                artifact=str(path),
            )
    finally:
        stopped.set()
        thread.join(timeout=1)
        if _lock_metadata(path).get("owner_id") == owner_id:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def _atomic_write(path: Path, content: str) -> None:
    """Flush a same-directory temporary file before atomically replacing path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _binding(
    *, round_n: int, prototype_hash: str, report_ref: str,
    summary: str, options: list[str],
) -> dict[str, Any]:
    fields = {
        "round": round_n,
        "prototype_html_hash": prototype_hash,
        "report_ref": report_ref,
        "summary": summary,
        "options": list(options),
    }
    canonical = json.dumps(
        fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {"digest": hashlib.sha256(canonical).hexdigest(), **fields}


def _load_entry(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransactionConflict(
            f"round decision metadata is unreadable; use next round: {path}",
            retryable=False, round_n=_round_from_path(path), decision_id="",
            artifact=str(path),
        ) from exc
    required = {
        "schema_version", "decision_id", "timestamp", "binding", "outcome"
    }
    round_n = _round_from_path(path)
    binding = entry.get("binding") if isinstance(entry, dict) else None
    outcome = entry.get("outcome") if isinstance(entry, dict) else None
    binding_valid = False
    if isinstance(binding, dict):
        try:
            expected = _binding(
                round_n=round_n,
                prototype_hash=binding["prototype_html_hash"],
                report_ref=binding["report_ref"], summary=binding["summary"],
                options=binding["options"],
            )
            binding_valid = binding == expected
        except (KeyError, TypeError):
            binding_valid = False
    if (
        not isinstance(entry, dict)
        or entry.get("schema_version") != ENTRY_SCHEMA_VERSION
        or not required.issubset(entry)
        or not isinstance(entry.get("decision_id"), str)
        or not entry["decision_id"]
        or not isinstance(entry.get("timestamp"), str)
        or not binding_valid
        or not isinstance(outcome, dict)
        or not isinstance(outcome.get("selected_options"), list)
        or not isinstance(outcome.get("anchors"), list)
        or not isinstance(outcome.get("feedback"), str)
        or not isinstance(outcome.get("confirmed"), bool)
        or not isinstance(outcome.get("user_confirmed"), bool)
        or not isinstance(outcome.get("floor_pass"), bool)
        or not isinstance(outcome.get("aborted"), bool)
    ):
        raise TransactionConflict(
            f"round decision metadata is invalid; use next round: {path}",
            retryable=False, round_n=round_n, decision_id="",
            artifact=str(path),
        )
    return entry


def _round_from_path(path: Path) -> int:
    try:
        return int(path.stem.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def _confirm_record(entry: dict[str, Any]) -> dict[str, Any]:
    binding = entry["binding"]
    outcome = entry["outcome"]
    record: dict[str, Any] = {
        "round": binding["round"],
        "report_ref": binding["report_ref"],
        "confirmed": outcome["confirmed"],
        "floor_pass": outcome["floor_pass"],
        "selected_options": outcome["selected_options"],
        "feedback": outcome["feedback"],
        "timestamp": entry["timestamp"],
        "prototype_path": f"preview/round-{binding['round']}.html",
        "prototype_html_hash": binding["prototype_html_hash"],
        "decision_id": entry["decision_id"],
    }
    if outcome.get("floor_failure"):
        record["floor_failure"] = outcome["floor_failure"]
    return record


def _render_log(entries: list[dict[str, Any]]) -> str:
    blocks = ["# preview log\n"]
    for entry in sorted(
        entries, key=lambda item: (str(item["timestamp"]), str(item["decision_id"]))
    ):
        binding = entry["binding"]
        outcome = entry["outcome"]
        anchors = list(outcome.get("anchors") or [])
        lines = [
            "",
            f"## round {binding['round']}",
            f"- report_ref: {binding['report_ref']}",
            f"- timestamp: {entry['timestamp']}",
            f"- decision_id: {entry['decision_id']}",
            f"- feedback: {outcome.get('feedback') or ''}",
            f"- selected: {', '.join(outcome.get('selected_options') or [])}",
            f"- aborted: {str(bool(outcome.get('aborted'))).lower()}",
            f"- anchors: {len(anchors)}",
            f"- floor_pass: {str(bool(outcome.get('floor_pass'))).lower()}",
        ]
        if outcome.get("floor_failure"):
            lines.append(f"- floor_failure: {outcome['floor_failure']}")
        if outcome.get("rejected"):
            lines.append("- rejected: true")
            if outcome.get("rejection"):
                lines.append(f"- rejection: {outcome['rejection']}")
        for index, anchor in enumerate(anchors, 1):
            lines.append(
                f"  - [{index}] {anchor.get('selector') or ''} | "
                f"{anchor.get('label') or ''} | {anchor.get('comment') or ''}"
            )
        blocks.append("\n".join(lines) + "\n")
    return "".join(blocks)


def _valid_entries(preview_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in preview_dir.glob("decision-round-*.json"):
        entry = _load_entry(path)
        if entry is not None:
            entries.append(entry)
    return entries


def _commit_projections(preview_dir: Path, entry: dict[str, Any]) -> str:
    binding = entry["binding"]
    outcome = entry["outcome"]
    confirm_path = preview_dir / f"confirm-round-{binding['round']}.json"
    if outcome["user_confirmed"]:
        existing_confirm = None
        if confirm_path.is_file():
            try:
                existing_confirm = json.loads(confirm_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                existing_confirm = None
        if existing_confirm and existing_confirm.get("decision_id") not in {
            None, entry["decision_id"]
        }:
            raise TransactionConflict(
                f"confirm belongs to another decision; use next round: {confirm_path}",
                retryable=False, round_n=int(binding["round"]),
                decision_id=str(entry["decision_id"]), artifact=str(confirm_path),
            )
        if existing_confirm and "decision_id" not in existing_confirm:
            raise TransactionConflict(
                f"legacy confirm cannot be overwritten; use next round: {confirm_path}",
                retryable=False, round_n=int(binding["round"]),
                decision_id=str(entry["decision_id"]), artifact=str(confirm_path),
            )
        _atomic_write(confirm_path, _json_text(_confirm_record(entry)))
        confirm_result = str(confirm_path)
    else:
        confirm_result = ""
    _atomic_write(preview_dir / "log.md", _render_log(_valid_entries(preview_dir)))
    return confirm_result


def _result(entry: dict[str, Any], confirm_path: str) -> dict[str, Any]:
    binding = entry["binding"]
    outcome = entry["outcome"]
    return {
        "confirmed": outcome["confirmed"],
        "floor_pass": outcome["floor_pass"],
        "selected_options": list(outcome["selected_options"]),
        "feedback": outcome["feedback"],
        "anchors": list(outcome["anchors"]),
        "round": binding["round"],
        "confirm_record_path": confirm_path,
        "aborted": outcome["aborted"],
        "decision_id": entry["decision_id"],
    }


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
    """Serialize, collect once, or repair one bound Preview decision."""
    summary = summary.strip()
    report_ref = report_ref.strip()
    preview_dir = _preview_dir_for(Path(path_arg) if path_arg else None)
    if path_arg:
        prototype = Path(path_arg)
        if not prototype.is_file():
            raise ValueError(f"prototype path does not exist: {path_arg}")
        prototype_hash = prototype_html_digest(prototype.read_bytes())
    else:
        if not html:
            raise ValueError("path or html is required")
        prototype_hash = prototype_html_digest(html.encode("utf-8"))
    binding = _binding(
        round_n=round_n, prototype_hash=prototype_hash,
        report_ref=report_ref, summary=summary, options=options,
    )
    entry_path = preview_dir / f"decision-round-{round_n}.json"
    existing = _load_entry(entry_path)
    decision_id = str(existing.get("decision_id") if existing else uuid.uuid4().hex)
    try:
        with _round_lock(
            preview_dir, round_n=round_n,
            binding_digest=binding["digest"], decision_id=decision_id,
        ):
            return _run_locked(
                path_arg=path_arg, html=html, summary=summary, round_n=round_n,
                report_ref=report_ref, options=options, collect=collect,
                preview_dir=preview_dir, prototype_hash=prototype_hash,
                binding=binding, decision_id=decision_id,
            )
    except PreviewTransactionError:
        raise
    except OSError as exc:
        confirm_path = preview_dir / f"confirm-round-{round_n}.json"
        log_path = preview_dir / "log.md"
        if not entry_path.is_file():
            artifact = entry_path
        else:
            entry = _load_entry(entry_path)
            needs_confirm = bool(entry and entry["outcome"].get("user_confirmed"))
            if needs_confirm and not confirm_path.is_file():
                artifact = confirm_path
            else:
                artifact = log_path
        raise PreviewTransactionError(
            f"Preview persistence incomplete: {exc}", retryable=True,
            round_n=round_n, decision_id=decision_id, artifact=str(artifact),
        ) from exc


def _run_locked(
    *, path_arg: str | None, html: str | None, summary: str, round_n: int,
    report_ref: str, options: list[str], collect: BrowserCollector,
    preview_dir: Path, prototype_hash: str, binding: dict[str, Any],
    decision_id: str,
) -> dict[str, Any]:
    entry_path = preview_dir / f"decision-round-{round_n}.json"
    if path_arg:
        prototype = Path(path_arg)
        if not prototype.is_file():
            raise ValueError(f"prototype path does not exist: {path_arg}")
        prototype_hash = prototype_html_digest(prototype.read_bytes())
    else:
        if not html:
            raise ValueError("path or html is required")
        prototype_hash = prototype_html_digest(html.encode("utf-8"))
        prototype = preview_dir / f"round-{round_n}.html"

    existing = _load_entry(entry_path)
    if existing is not None:
        if existing["binding"].get("digest") != binding["digest"]:
            raise TransactionConflict(
                f"round binding differs from durable decision; use next round: {round_n}",
                retryable=False, round_n=round_n,
                decision_id=str(existing["decision_id"]), artifact=str(entry_path),
            )
        confirm_path = _commit_projections(preview_dir, existing)
        return _result(existing, confirm_path)

    legacy_confirm = preview_dir / f"confirm-round-{round_n}.json"
    if legacy_confirm.is_file():
        raise TransactionConflict(
            f"legacy confirm cannot be overwritten; use next round: {legacy_confirm}",
            retryable=False, round_n=round_n, decision_id=decision_id,
            artifact=str(legacy_confirm),
        )

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
        not aborted and not rejected and choice.casefold() in confirm_labels
    )
    if rejected:
        floor_pass = False
        floor_failure = str(submission.get("floor_failure") or "")
    else:
        floor_pass, floor_failure = _check_feedback_floor(raw_feedback, anchors)
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
        },
    }
    _atomic_write(entry_path, _json_text(entry))
    confirm_path = _commit_projections(preview_dir, entry)
    return _result(entry, confirm_path)
