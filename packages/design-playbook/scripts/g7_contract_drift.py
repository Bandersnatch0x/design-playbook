#!/usr/bin/env python3
"""G7 contract-drift checks (ADR-0020).

Compares the bind-first snapshot against the current project contract and
decision log. Reports structural consistency only — never user identity.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.contract_v1 import (
    BIND_SNAPSHOT_FILENAME,
    CONTRACT_FILENAME,
    DECISIONS_FILENAME,
    ContractError,
    apply_decisions,
    contract_sha,
    decision_log_sha,
    load_contract,
    load_decisions,
    normalize_contract,
)


def _load_bind_snapshot(run_dir: Path) -> dict[str, Any]:
    path = run_dir / BIND_SNAPSHOT_FILENAME
    if not path.is_file():
        raise ContractError(f"missing bind-first snapshot: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"bind snapshot malformed JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("bind snapshot must be an object")
    return data


def check_g7(project_dir: Path, run_dir: Path) -> list[Finding]:
    """Return G7 findings. Empty means structural consistency holds."""
    findings: list[Finding] = []
    try:
        snap = _load_bind_snapshot(run_dir)
    except ContractError as exc:
        return [finding(
            "G7.missing_binding",
            f"G7 contract: {exc}",
            owner=str(run_dir / BIND_SNAPSHOT_FILENAME),
            expected="contract-bind.json from bind_first",
            actual="missing or unreadable",
            repair="Run bind-first before acceptance",
        )]

    version = snap.get("schemaVersion", snap.get("schema_version"))
    if version != 1:
        findings.append(finding(
            "G7.unsupported_version",
            f"G7 contract: unsupported bind schemaVersion {version!r}",
            owner=BIND_SNAPSHOT_FILENAME,
            expected="schemaVersion=1",
            actual=repr(version),
            repair="Re-bind with contract v1",
        ))
        return findings

    bound_contract_sha = snap.get("contract_sha")
    bound_log_sha = snap.get("decision_log_sha")
    if not isinstance(bound_contract_sha, str) or not bound_contract_sha:
        findings.append(finding(
            "G7.missing_binding",
            "G7 contract: bind snapshot missing contract_sha",
            owner=BIND_SNAPSHOT_FILENAME,
            expected="contract_sha",
            actual="missing",
            repair="Re-run bind_first",
        ))
        return findings
    if not isinstance(bound_log_sha, str):
        findings.append(finding(
            "G7.missing_binding",
            "G7 contract: bind snapshot missing decision_log_sha",
            owner=BIND_SNAPSHOT_FILENAME,
            expected="decision_log_sha string (empty log allowed)",
            actual=repr(bound_log_sha),
            repair="Re-run bind_first",
        ))
        return findings

    try:
        current = load_contract(project_dir / CONTRACT_FILENAME)
        decisions = load_decisions(project_dir / DECISIONS_FILENAME)
        effective = apply_decisions(current, decisions) if decisions else current
        current_contract_sha = contract_sha(effective)
        current_log_sha = decision_log_sha(records=decisions)
    except ContractError as exc:
        return [finding(
            "G7.unsupported_version",
            f"G7 contract: current project contract unusable: {exc}",
            owner=str(project_dir / CONTRACT_FILENAME),
            expected="valid contract v1 + append-only decisions",
            actual=str(exc),
            repair="Fix the project contract/decision log, then re-bind",
        )]

    bound_contract = snap.get("bound_contract")
    if not isinstance(bound_contract, dict):
        findings.append(finding(
            "G7.missing_binding",
            "G7 contract: bind snapshot missing bound_contract body",
            owner=BIND_SNAPSHOT_FILENAME,
            expected="bound_contract object",
            actual="missing",
            repair="Re-run bind_first",
        ))
        return findings

    try:
        bound_norm = normalize_contract(bound_contract)
    except ContractError as exc:
        findings.append(finding(
            "G7.unsupported_version",
            f"G7 contract: bound contract invalid: {exc}",
            owner=BIND_SNAPSHOT_FILENAME,
            expected="valid contract v1 snapshot",
            actual=str(exc),
            repair="Re-run bind_first with a valid contract",
        ))
        return findings

    # Append-only: current decision log must start with the bound log bytes when
    # both are non-empty; new decisions may only append.
    # When contract fields change, require decision coverage for changed paths.
    bound_fields = bound_norm["fields"]
    current_fields = effective["fields"]
    all_paths = sorted(set(bound_fields) | set(current_fields))
    changed: list[str] = []
    for path in all_paths:
        left = bound_fields.get(path)
        right = current_fields.get(path)
        if left != right:
            changed.append(path)

    if not changed:
        if current_contract_sha != bound_contract_sha:
            findings.append(finding(
                "G7.contract_sha_mismatch",
                "G7 contract: normalized field set unchanged but contract SHA drifted",
                owner=CONTRACT_FILENAME,
                expected=bound_contract_sha,
                actual=current_contract_sha,
                repair="Re-bind after canonical rewrite or restore the bound contract",
            ))
        if current_log_sha != bound_log_sha:
            findings.append(finding(
                "G7.decision_log_mismatch",
                "G7 contract: decision log changed without field changes",
                owner=DECISIONS_FILENAME,
                expected=bound_log_sha,
                actual=current_log_sha,
                repair="Only append decisions that change contract fields, or re-bind",
            ))
        return findings

    # Changed fields require matching decision IDs after bind for those paths.
    # Require that each changed path has at least one decision whose field
    # matches and whose resolution is decided on the effective contract.
    decided_paths = {
        path for path, entry in current_fields.items()
        if entry.get("resolution") == "decided"
    }
    for path in changed:
        if path not in decided_paths:
            findings.append(finding(
                "G7.unrecorded_field_change",
                f"G7 contract: field {path} changed without a decided decision record",
                owner=path,
                expected="append-only decision promoting the field",
                actual=str(current_fields.get(path)),
                repair=f"Append a user-confirmed decision for {path} or restore the bound value",
            ))
            continue
        # Ensure some decision targets this field.
        if not any(item.get("field") == path for item in decisions):
            findings.append(finding(
                "G7.unrecorded_field_change",
                f"G7 contract: field {path} is decided but no decision log row targets it",
                owner=DECISIONS_FILENAME,
                expected=f"decision.field == {path}",
                actual="no matching decision",
                repair=f"Append a decision for {path}",
            ))

    if current_log_sha == bound_log_sha and changed:
        findings.append(finding(
            "G7.decision_log_mismatch",
            "G7 contract: fields changed but decision-log SHA is unchanged",
            owner=DECISIONS_FILENAME,
            expected="appended decisions for changed paths",
            actual=current_log_sha,
            repair="Append decision records for the changed fields",
        ))

    # Non-append history: duplicate ids already rejected by contract_v1 loader.
    ids = [item["id"] for item in decisions]
    if len(ids) != len(set(ids)):
        findings.append(finding(
            "G7.non_append_history",
            "G7 contract: decision log is not append-only (duplicate ids)",
            owner=DECISIONS_FILENAME,
            expected="unique decision ids",
            actual="duplicate ids present",
            repair="Restore the append-only log; never rewrite prior lines",
        ))

    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: g7_contract_drift.py <project_dir> <run_dir>", file=sys.stderr)
        return 2
    findings = check_g7(Path(argv[1]), Path(argv[2]))
    if not findings:
        print("G7 OK: contract binding is structurally consistent")
        return 0
    print("G7 INVALID:")
    for item in findings:
        print(f"  FAIL  {item.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
