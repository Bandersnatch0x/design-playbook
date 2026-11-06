"""Evidence manifest v1 schema access (T-145).

The schema file is the written-down shape of a manifest line; this module is
how code and third-party providers reach it without copying constants. It
does not run at write time — ``scripts/evidence_manifest.py`` keeps its own
guard order and messages (behavior is unchanged); this is the contract a
reader or a registered provider validates against.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from design_playbook.mcp._schema import violations

SCHEMA_PATH = Path(__file__).with_name("manifest_v1.schema.json")


def manifest_schema() -> dict[str, Any]:
    """Load the v1 manifest entry schema."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_manifest_entry(entry: object) -> list[str]:
    """Return every v1 violation of one manifest entry (empty = valid)."""
    return violations(entry, manifest_schema())
