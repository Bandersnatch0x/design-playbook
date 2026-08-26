#!/usr/bin/env python3
"""Persistent contract v1 lifecycle (bind, promote, decide, hash, verify).

One deterministic module owns project-level contract IR operations so skills
and validators do not reimplement authority rules. See ADR-0017 / ADR-0019.

Public surface:
  normalize_contract, contract_sha, decision_log_sha,
  load_contract, dump_contract, load_decisions, append_decision,
  promote_fields, bind_first, apply_decisions, verify_contract,
  read_bind_snapshot, parse_bind_snapshot, bind_resolution_lists,
  bind_resolution_conflicts
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1
PROVENANCES = frozenset({"observed", "inferred"})
RESOLUTIONS = frozenset({"decided", "assumed", "open"})
# v1 forbids layered inheritance / partial override hooks (ADR-0019).
FORBIDDEN_KEYS = frozenset({
    "extends", "inherits", "inheritance", "layers", "parent",
    "overrides", "merge", "partial",
})

CONTRACT_FILENAME = "contract.json"
DECISIONS_FILENAME = "decisions.jsonl"
BIND_SNAPSHOT_FILENAME = "contract-bind.json"


class ContractError(ValueError):
    """Invalid contract, decision, or lifecycle request."""


def _json_canonical(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a JSON object")
    return value


def _check_forbidden(raw: Mapping[str, Any], *, where: str) -> None:
    bad = sorted(FORBIDDEN_KEYS.intersection(raw))
    if bad:
        raise ContractError(
            f"{where} rejects layered inheritance keys in v1: {', '.join(bad)}"
        )


def _normalize_field(path: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    _check_forbidden(raw, where=f"field {path}")
    if "value" not in raw:
        raise ContractError(f"field {path} missing value")
    provenance = raw.get("provenance")
    resolution = raw.get("resolution")
    if provenance not in PROVENANCES:
        raise ContractError(
            f"field {path} provenance must be observed|inferred, got {provenance!r}"
        )
    if resolution not in RESOLUTIONS:
        raise ContractError(
            f"field {path} resolution must be decided|assumed|open, got {resolution!r}"
        )
    out: dict[str, Any] = {
        "value": raw["value"],
        "provenance": provenance,
        "resolution": resolution,
    }
    if "source_hash" in raw:
        source_hash = raw["source_hash"]
        if source_hash is not None and not isinstance(source_hash, str):
            raise ContractError(f"field {path} source_hash must be a string or null")
        out["source_hash"] = source_hash
    if "notes" in raw and raw["notes"] is not None:
        if not isinstance(raw["notes"], str):
            raise ContractError(f"field {path} notes must be a string")
        out["notes"] = raw["notes"]
    return out


def normalize_contract(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministically ordered, validated contract document."""
    data = _require_mapping(raw, "contract")
    _check_forbidden(data, where="contract")
    version = data.get("schemaVersion", data.get("schema_version"))
    if version != SCHEMA_VERSION:
        raise ContractError(
            f"unsupported contract schemaVersion {version!r}; expected {SCHEMA_VERSION}"
        )
    fields_raw = data.get("fields")
    if not isinstance(fields_raw, dict) or not fields_raw:
        raise ContractError("contract.fields must be a non-empty object")
    fields: dict[str, Any] = {}
    for path in sorted(fields_raw):
        if not isinstance(path, str) or not path.strip():
            raise ContractError(f"invalid field path: {path!r}")
        entry = fields_raw[path]
        if not isinstance(entry, dict):
            raise ContractError(f"field {path} must be an object")
        fields[path] = _normalize_field(path, entry)

    changelog: list[dict[str, Any]] = []
    raw_log = data.get("changelog", [])
    if raw_log is None:
        raw_log = []
    if not isinstance(raw_log, list):
        raise ContractError("contract.changelog must be a list")
    for i, item in enumerate(raw_log):
        if not isinstance(item, dict):
            raise ContractError(f"changelog[{i}] must be an object")
        summary = item.get("summary")
        at = item.get("at")
        if not isinstance(summary, str) or not summary.strip():
            raise ContractError(f"changelog[{i}] requires non-empty summary")
        if not isinstance(at, str) or not at.strip():
            raise ContractError(f"changelog[{i}] requires non-empty at timestamp")
        changelog.append({"at": at, "summary": summary})

    return {
        "schemaVersion": SCHEMA_VERSION,
        "fields": fields,
        "changelog": changelog,
    }


def contract_sha(contract: Mapping[str, Any]) -> str:
    """SHA-256 of the normalized contract (stable across key order)."""
    normalized = normalize_contract(contract)
    return _sha256_text(_json_canonical(normalized))


def _normalize_decision(raw: Mapping[str, Any]) -> dict[str, Any]:
    data = _require_mapping(raw, "decision")
    decision_id = data.get("id")
    field_path = data.get("field")
    decision = data.get("decision")
    rationale = data.get("rationale")
    confirmed_at = data.get("confirmed_at")
    if not isinstance(decision_id, str) or not decision_id.strip():
        raise ContractError("decision.id is required")
    if not isinstance(field_path, str) or not field_path.strip():
        raise ContractError("decision.field is required")
    if "decision" not in data:
        raise ContractError("decision.decision is required")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ContractError("decision.rationale is required")
    if not isinstance(confirmed_at, str) or not confirmed_at.strip():
        raise ContractError("decision.confirmed_at is required")
    out: dict[str, Any] = {
        "id": decision_id,
        "field": field_path,
        "decision": decision,
        "rationale": rationale,
        "confirmed_at": confirmed_at,
    }
    supersedes = data.get("supersedes")
    if supersedes is not None:
        if not isinstance(supersedes, str) or not supersedes.strip():
            raise ContractError("decision.supersedes must be a non-empty string when set")
        out["supersedes"] = supersedes
    return out


def load_decisions(path: Path) -> list[dict[str, Any]]:
    """Load an append-only decision log; missing file means empty history."""
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"{path.name}:{line_no} invalid JSON: {exc}") from exc
        records.append(_normalize_decision(raw))
    return records


def decision_log_sha(path: Path | None = None, records: Iterable[Mapping[str, Any]] | None = None) -> str:
    """SHA-256 of the canonical decision log contents."""
    if records is None:
        if path is None:
            raise ContractError("decision_log_sha requires path or records")
        records = load_decisions(path)
    normalized = [_normalize_decision(item) for item in records]
    # Preserve append order; do not sort — order is the authority trail.
    payload = [_json_canonical(item) for item in normalized]
    return _sha256_text("\n".join(payload) + ("\n" if payload else ""))


def append_decision(path: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """Append one decision record. Never rewrites prior lines."""
    decision = _normalize_decision(record)
    existing = load_decisions(path) if path.is_file() else []
    known_ids = {item["id"] for item in existing}
    if decision["id"] in known_ids:
        raise ContractError(
            f"decision id {decision['id']!r} already exists; append-only log "
            "cannot rewrite history — use supersedes with a new id"
        )
    if decision.get("supersedes") and decision["supersedes"] not in known_ids:
        raise ContractError(
            f"decision supersedes unknown id {decision['supersedes']!r}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_json_canonical(decision) + "\n")
    return decision


def load_contract(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(f"contract not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"contract malformed JSON: {exc}") from exc
    return normalize_contract(raw)


def dump_contract(path: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_contract(contract)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return normalized


def promote_fields(
        fields: Mapping[str, Mapping[str, Any]],
        *,
        project_dir: Path,
        changelog_summary: str,
        at: str,
        existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Persist a project contract from accepted field proposals.

    Does **not** promote resolution to decided. Callers must pass each field's
    explicit resolution; omitted resolution fails closed.
    """
    merged_fields: dict[str, Any] = {}
    if existing is not None:
        base = normalize_contract(existing)
        merged_fields.update(base["fields"])
        changelog = list(base["changelog"])
    else:
        changelog = []
    for path, entry in fields.items():
        if not isinstance(entry, Mapping):
            raise ContractError(f"promote field {path} must be an object")
        # Accepting a whole spec must not silently invent decided.
        if entry.get("resolution") == "decided":
            raise ContractError(
                f"field {path}: promote_fields cannot create decided; "
                "use append_decision + apply_decisions after user confirmation"
            )
        merged_fields[path] = dict(entry)
    changelog.append({"at": at, "summary": changelog_summary})
    contract = normalize_contract({
        "schemaVersion": SCHEMA_VERSION,
        "fields": merged_fields,
        "changelog": changelog,
    })
    dump_contract(project_dir / CONTRACT_FILENAME, contract)
    return contract


def apply_decisions(
        contract: Mapping[str, Any],
        decisions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply the latest non-superseded decision per field onto the contract."""
    normalized = normalize_contract(contract)
    records = [_normalize_decision(item) for item in decisions]
    superseded = {
        item["supersedes"] for item in records if item.get("supersedes")
    }
    active = [item for item in records if item["id"] not in superseded]
    # Last active decision for a field wins (append order).
    latest: dict[str, dict[str, Any]] = {}
    for item in active:
        latest[item["field"]] = item
    fields = dict(normalized["fields"])
    for path, item in latest.items():
        if path not in fields:
            raise ContractError(
                f"decision {item['id']} targets unknown field {path!r}"
            )
        entry = dict(fields[path])
        entry["value"] = item["decision"]
        entry["resolution"] = "decided"
        fields[path] = entry
    return normalize_contract({
        "schemaVersion": SCHEMA_VERSION,
        "fields": fields,
        "changelog": normalized["changelog"],
    })


@dataclass
class BindResult:
    """Outcome of bind-first review for one run."""

    ok: bool
    schema_version: int
    contract_sha: str
    decision_log_sha: str
    open_fields: list[str] = field(default_factory=list)
    assumed_fields: list[str] = field(default_factory=list)
    stale_fields: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    contract: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schemaVersion": self.schema_version,
            "contract_sha": self.contract_sha,
            "decision_log_sha": self.decision_log_sha,
            "open_fields": list(self.open_fields),
            "assumed_fields": list(self.assumed_fields),
            "stale_fields": list(self.stale_fields),
            "blockers": list(self.blockers),
        }


def _stale_fields(
        contract: Mapping[str, Any],
        source_hashes: Mapping[str, str] | None) -> list[str]:
    if not source_hashes:
        return []
    stale: list[str] = []
    for path, entry in contract["fields"].items():
        recorded = entry.get("source_hash")
        if not isinstance(recorded, str) or not recorded:
            continue
        current = source_hashes.get(path)
        if current is not None and current != recorded:
            stale.append(path)
    return sorted(stale)


def bind_first(
        project_dir: Path,
        run_dir: Path,
        *,
        acknowledgements: Iterable[str] = (),
        source_hashes: Mapping[str, str] | None = None) -> BindResult:
    """Bind the whole project contract into a run and surface unresolved risk.

    - open fields always block dependent work
    - assumed fields block unless explicitly acknowledged for this run
    - stale source_hash fields require review
    """
    contract_path = project_dir / CONTRACT_FILENAME
    decisions_path = project_dir / DECISIONS_FILENAME
    contract = load_contract(contract_path)
    decisions = load_decisions(decisions_path)
    effective = apply_decisions(contract, decisions) if decisions else contract

    open_fields = sorted(
        path for path, entry in effective["fields"].items()
        if entry["resolution"] == "open"
    )
    assumed_fields = sorted(
        path for path, entry in effective["fields"].items()
        if entry["resolution"] == "assumed"
    )
    stale = _stale_fields(effective, source_hashes)
    acked = {item.strip() for item in acknowledgements if item and item.strip()}
    blockers: list[str] = []
    for path in open_fields:
        blockers.append(f"open field blocks work: {path}")
    for path in assumed_fields:
        if path not in acked:
            blockers.append(f"assumed field requires acknowledgement: {path}")
    for path in stale:
        blockers.append(f"source/schema drift requires review: {path}")

    result = BindResult(
        ok=not blockers,
        schema_version=SCHEMA_VERSION,
        contract_sha=contract_sha(effective),
        decision_log_sha=decision_log_sha(records=decisions),
        open_fields=open_fields,
        assumed_fields=assumed_fields,
        stale_fields=stale,
        blockers=blockers,
        contract=effective,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot = result.to_dict()
    snapshot["bound_contract"] = effective
    (run_dir / BIND_SNAPSHOT_FILENAME).write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


# --- run-side bind snapshot read authority (ADR-0039) ----------------------
#
# ``contract-bind.json`` is written by ``bind_first`` above and read back by
# three consumers with different vocabularies (G7 findings, G12 diff input,
# Run Snapshot availability). The read itself and the resolution invariant
# live here, beside the shape that produced them; each consumer projects the
# one result into its own failure vocabulary.

BIND_COMPLETE = "complete"
BIND_MISSING = "missing"
BIND_UNREADABLE = "unreadable"
BIND_PARTIAL_WRITE = "partial-write"
BIND_MALFORMED = "malformed"
BIND_CONFLICTING_RESOLUTION = "conflicting-resolution"

RESOLUTION_LIST_FIELDS = ("open_fields", "assumed_fields", "stale_fields")


@dataclass(frozen=True)
class BindSnapshotRead:
    """One read of a run-side bind snapshot: state, payload, and detail."""

    state: str
    data: dict[str, Any] | None = None
    detail: str = ""

    @property
    def complete(self) -> bool:
        return self.state == BIND_COMPLETE


def parse_bind_snapshot(text: str) -> BindSnapshotRead:
    """Parse captured bind-snapshot text. No filesystem access, never raises.

    A JSON decode failure is reported as ``partial-write``: the writer above
    replaces the file atomically, so unparsable bytes mean the reader observed
    a torn write rather than a semantically invalid record. Overlapping
    resolution lists are ``conflicting-resolution``, not complete: the
    invariant lives here so every consumer sees the same unusable state.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return BindSnapshotRead(BIND_PARTIAL_WRITE, detail=str(exc))
    if not isinstance(data, dict):
        return BindSnapshotRead(
            BIND_MALFORMED, detail="bind snapshot must be an object"
        )
    try:
        lists = bind_resolution_lists(data)
    except ContractError as exc:
        return BindSnapshotRead(BIND_MALFORMED, data=data, detail=str(exc))
    conflicts = bind_resolution_conflicts(lists)
    if conflicts:
        return BindSnapshotRead(
            BIND_CONFLICTING_RESOLUTION,
            data=data,
            detail=", ".join(conflicts),
        )
    return BindSnapshotRead(BIND_COMPLETE, data)


def read_bind_snapshot(run_dir: Path) -> BindSnapshotRead:
    """Read ``<run_dir>/contract-bind.json`` once. Never raises."""
    path = run_dir / BIND_SNAPSHOT_FILENAME
    if not path.is_file():
        return BindSnapshotRead(
            BIND_MISSING, detail=f"missing bind-first snapshot: {path.name}"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return BindSnapshotRead(BIND_UNREADABLE, detail=str(exc))
    return parse_bind_snapshot(text)


def bind_resolution_lists(snapshot: Mapping[str, Any]) -> dict[str, list[str]]:
    """The three resolution lists, validated as lists of strings."""
    lists: dict[str, list[str]] = {}
    for name in RESOLUTION_LIST_FIELDS:
        value = snapshot.get(name)
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise ContractError(f"bind snapshot {name} must be a list of strings")
        lists[name] = list(value)
    return lists


def bind_resolution_conflicts(lists: Mapping[str, list[str]]) -> list[str]:
    """Fields claimed by more than one resolution set.

    A contract field carries exactly one resolution, so the three lists are
    disjoint by construction. Any overlap means the record no longer describes
    a reachable contract state; every consumer treats the result as
    inconsistent rather than reading one of the conflicting claims.
    """
    open_fields = set(lists["open_fields"])
    assumed_fields = set(lists["assumed_fields"])
    stale_fields = set(lists["stale_fields"])
    return sorted(
        (open_fields & assumed_fields)
        | (open_fields & stale_fields)
        | (assumed_fields & stale_fields)
    )


def verify_contract(
        contract: Mapping[str, Any],
        decisions: Iterable[Mapping[str, Any]] | None = None) -> list[str]:
    """Return human-readable verification errors (empty means ok)."""
    errors: list[str] = []
    try:
        normalized = normalize_contract(contract)
    except ContractError as exc:
        return [str(exc)]
    if decisions is not None:
        try:
            records = [_normalize_decision(item) for item in decisions]
            apply_decisions(normalized, records)
            # Detect non-append identity collisions inside the provided list.
            ids = [item["id"] for item in records]
            if len(ids) != len(set(ids)):
                errors.append("decision log contains duplicate ids (not append-only)")
        except ContractError as exc:
            errors.append(str(exc))
    return errors


_DECISION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def validate_decision_ids(ids: Iterable[str]) -> None:
    for decision_id in ids:
        if not _DECISION_ID_RE.match(decision_id):
            raise ContractError(f"invalid decision id: {decision_id!r}")
