"""Run-external, append-only Preview round ledger (T-086 / DEF-2).

Every committed Preview decision appends one JSON line here, outside the
run tree, so moving/renaming/deleting ``preview/`` cannot wash the G5 gate:
the gate takes the union of on-disk rounds and ledger rounds and treats
ledger-only rounds (orphans) as INVALID with an observable reason.

Ledger lines are never rewritten or deleted by this module — append-only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

LEDGER_ENV_VAR = "DESIGN_PLAYBOOK_PREVIEW_LEDGER_DIR"


def ledger_root() -> Path:
    """Ledger directory: env override, else the user-level .design-playbook dir."""
    override = os.environ.get(LEDGER_ENV_VAR)
    return Path(override) if override else Path.home() / ".design-playbook" / "preview-ledger"


def ledger_path(preview_dir: Path, *, root: Path | None = None) -> Path:
    """One append-only file per preview directory (absolute-path keyed)."""
    key = hashlib.sha256(
        str(preview_dir.resolve()).encode("utf-8")
    ).hexdigest()
    return (root or ledger_root()) / f"{key}.jsonl"


def append_record(
    preview_dir: Path, record: dict[str, Any], *, root: Path | None = None
) -> None:
    """Append one round record; a failed append fails the transaction."""
    path = ledger_path(preview_dir, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def rounds_for(
    preview_dir: Path, *, root: Path | None = None
) -> tuple[int, ...]:
    """All round numbers ever registered for this preview directory."""
    path = ledger_path(preview_dir, root=root)
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ()
    rounds: set[int] = set()
    for line in raw.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("round"), int):
            rounds.add(record["round"])
    return tuple(sorted(rounds))
