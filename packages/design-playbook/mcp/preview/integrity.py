"""Shared, host-neutral integrity rules for Preview artifacts."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ARTIFACT_ROUND = re.compile(
    r"^(?:(?:confirm|decision)-)?round-(\d+)\.(?:html|json)$", re.I
)
_CONFIRM_NAME = re.compile(r"^confirm-round-(\d+)\.json$", re.I)
_DECISION_NAME = re.compile(r"^decision-round-(\d+)\.json$", re.I)
_LOG_ROUND = re.compile(r"^## round (\d+)", re.MULTILINE)


@dataclass(frozen=True)
class FloorResult:
    passed: bool
    reason: str


@dataclass(frozen=True)
class IntegrityFact:
    code: str
    detail: str
    path: Path | None = None
    expected: str = ""
    actual: str = ""


@dataclass(frozen=True, init=False)
class ConfirmRecord:
    path: Path
    _data_json: str
    round: int | None
    valid: bool
    prototype_status: str
    expected_digest: str = ""
    actual_digest: str = ""

    def __init__(
        self,
        path: Path,
        data: object,
        round: int | None,
        valid: bool,
        prototype_status: str,
        expected_digest: str = "",
        actual_digest: str = "",
    ) -> None:
        object.__setattr__(self, "path", path)
        object.__setattr__(
            self,
            "_data_json",
            json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        object.__setattr__(self, "round", round)
        object.__setattr__(self, "valid", valid)
        object.__setattr__(self, "prototype_status", prototype_status)
        object.__setattr__(self, "expected_digest", expected_digest)
        object.__setattr__(self, "actual_digest", actual_digest)

    @property
    def data(self) -> object:
        """Return a detached value so callers cannot mutate the snapshot."""
        return json.loads(self._data_json)


@dataclass(frozen=True)
class PreviewSnapshot:
    preview_dir: Path
    occurred: bool
    occurrence_sources: tuple[str, ...]
    current_round: int | None
    current_confirms: tuple[ConfirmRecord, ...]
    canonical_current_confirm: ConfirmRecord | None
    facts: tuple[IntegrityFact, ...]


def evaluate_feedback_floor(
    feedback: str, anchors: list[object]
) -> FloorResult:
    """Apply ADR-0008 structural feedback-floor authority."""
    feedback = (feedback or "").strip()
    if not feedback and not anchors:
        return FloorResult(
            False,
            "confirm with no substantive feedback: empty feedback and no anchor",
        )
    for anchor in anchors:
        if not isinstance(anchor, dict):
            return FloorResult(False, "anchor is not an object")
        selector = str(anchor.get("selector") or "").strip()
        comment = str(anchor.get("comment") or "").strip()
        if not selector or not comment:
            return FloorResult(
                False,
                "anchor missing non-empty selector and comment: "
                f"selector={selector!r} comment={comment!r}",
            )
    return FloorResult(True, "")


def prototype_html_digest(raw: bytes) -> str:
    """Return LF-normalized SHA-256 for trusted prototype bytes."""
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _round_from_name(name: str) -> int | None:
    match = _ARTIFACT_ROUND.match(name)
    return int(match.group(1)) if match else None


def _confirm_round(path: Path, data: dict[str, Any]) -> int | None:
    filename_round = _round_from_name(path.name)
    raw = data.get("round")
    json_round: int | None = None
    if isinstance(raw, int) and not isinstance(raw, bool):
        json_round = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        json_round = int(raw)
    if (
        filename_round is not None
        and json_round is not None
        and filename_round != json_round
    ):
        return None
    return json_round if json_round is not None else filename_round


def _is_confirmed_valid(data: object) -> bool:
    return (
        isinstance(data, dict)
        and data.get("confirmed") is True
        and data.get("floor_pass") is True
        and data.get("aborted") is not True
    )


def _valid_decision_entry(path: Path) -> bool:
    match = _DECISION_NAME.match(path.name)
    if not match or not path.is_file():
        return False
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(entry, dict) or entry.get("schema_version") != 1:
        return False
    binding = entry.get("binding")
    outcome = entry.get("outcome")
    if not (
        isinstance(entry.get("decision_id"), str)
        and bool(entry["decision_id"])
        and isinstance(binding, dict)
        and binding.get("round") == int(match.group(1))
        and isinstance(binding.get("prototype_html_hash"), str)
        and isinstance(binding.get("report_ref"), str)
        and isinstance(binding.get("summary"), str)
        and isinstance(binding.get("options"), list)
        and all(isinstance(item, str) for item in binding["options"])
        and isinstance(outcome, dict)
    ):
        return False
    fields = {
        "round": binding["round"],
        "prototype_html_hash": binding["prototype_html_hash"],
        "report_ref": binding["report_ref"],
        "summary": binding["summary"],
        "options": binding["options"],
    }
    canonical = json.dumps(
        fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return binding.get("digest") == hashlib.sha256(canonical).hexdigest()


def inspect_preview(preview_dir: Path) -> PreviewSnapshot:
    """Read Preview artifacts once and return current-first integrity facts."""
    if not preview_dir.is_dir():
        return PreviewSnapshot(
            preview_dir=preview_dir,
            occurred=False,
            occurrence_sources=(),
            current_round=None,
            current_confirms=(),
            canonical_current_confirm=None,
            facts=(),
        )

    facts: list[IntegrityFact] = []
    try:
        entries = sorted(
            preview_dir.iterdir(), key=lambda path: (path.name.casefold(), path.name)
        )
    except OSError as exc:
        log_path = preview_dir / "log.md"
        log_present = log_path.is_file()
        return PreviewSnapshot(
            preview_dir=preview_dir,
            occurred=log_present,
            occurrence_sources=("log.md",) if log_present else (),
            current_round=None,
            current_confirms=(),
            canonical_current_confirm=None,
            facts=(IntegrityFact("preview_unreadable", str(exc), preview_dir),),
        )

    rounds = [
        round_n
        for path in entries
        if path.is_file()
        for round_n in [_round_from_name(path.name)]
        if round_n is not None
    ]
    log_path = preview_dir / "log.md"
    if log_path.is_file():
        try:
            rounds.extend(
                int(match.group(1))
                for match in _LOG_ROUND.finditer(log_path.read_text(encoding="utf-8"))
            )
        except (OSError, UnicodeError):
            pass
    current_round = max(rounds) if rounds else None
    occurrence_sources: list[str] = []
    if log_path.is_file():
        occurrence_sources.append("log.md")
    for path in entries:
        if not path.is_file():
            continue
        if _round_from_name(path.name) is not None and path.suffix.lower() == ".html":
            occurrence_sources.append(path.name)
        elif _valid_decision_entry(path):
            occurrence_sources.append(path.name)
    occurred = bool(occurrence_sources)

    parsed: list[tuple[Path, object, int | None]] = []
    for path in entries:
        if not path.is_file() or not _CONFIRM_NAME.match(path.name):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            facts.append(
                IntegrityFact(
                    "invalid_confirm_record",
                    f"invalid confirm record {path.name}: {exc}",
                    path,
                )
            )
            continue
        if not isinstance(data, dict):
            facts.append(
                IntegrityFact(
                    "confirm_not_object",
                    f"confirm record {path.name} is not an object",
                    path,
                    expected="JSON object",
                    actual=type(data).__name__,
                )
            )
            parsed.append((path, data, _round_from_name(path.name)))
            continue
        parsed.append((path, data, _confirm_round(path, data)))

    canonical_current_confirm: ConfirmRecord | None = None
    current_records: list[ConfirmRecord] = []
    for path, data, record_round in parsed:
        valid = _is_confirmed_valid(data)
        if (
            current_round is not None
            and path == preview_dir / f"confirm-round-{current_round}.json"
        ):
            canonical_current_confirm = ConfirmRecord(
                path=path,
                data=data,
                round=record_round,
                valid=valid,
                prototype_status="unchecked",
            )
        if current_round is not None and record_round != current_round:
            continue
        prototype_status = "unchecked"
        expected_digest = ""
        actual_digest = ""
        if valid:
            stored = data.get("prototype_html_hash")
            if not isinstance(stored, str) or not stored:
                prototype_status = "missing_hash"
                facts.append(
                    IntegrityFact(
                        "missing_hash",
                        "confirmed record missing prototype_html_hash",
                        path,
                    )
                )
            elif current_round is None:
                prototype_status = "missing_prototype"
                facts.append(
                    IntegrityFact(
                        "missing_prototype",
                        "confirmed record prototype html is missing",
                        path,
                    )
                )
            else:
                prototype = preview_dir / f"round-{current_round}.html"
                try:
                    preview_root = preview_dir.resolve()
                    resolved = prototype.resolve()
                    resolved.relative_to(preview_root)
                    if not resolved.is_file():
                        raise FileNotFoundError(str(resolved))
                    actual_digest = prototype_html_digest(resolved.read_bytes())
                except (OSError, ValueError):
                    prototype_status = "missing_prototype"
                    facts.append(
                        IntegrityFact(
                            "missing_prototype",
                            "confirmed record prototype html is missing",
                            path,
                        )
                    )
                else:
                    expected_digest = stored
                    prototype_status = "match" if actual_digest == stored else "mismatch"
                    if prototype_status == "mismatch":
                        facts.append(
                            IntegrityFact(
                                "hash_mismatch",
                                "confirmed record prototype digest mismatch",
                                path,
                                expected=stored,
                                actual=actual_digest,
                            )
                        )
        current_records.append(
            ConfirmRecord(
                path=path,
                data=data,
                round=record_round,
                valid=valid,
                prototype_status=prototype_status,
                expected_digest=expected_digest,
                actual_digest=actual_digest,
            )
        )

    return PreviewSnapshot(
        preview_dir=preview_dir,
        occurred=occurred,
        occurrence_sources=tuple(occurrence_sources),
        current_round=current_round,
        current_confirms=tuple(current_records),
        canonical_current_confirm=canonical_current_confirm,
        facts=tuple(facts),
    )
