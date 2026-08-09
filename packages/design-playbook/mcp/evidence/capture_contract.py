#!/usr/bin/env python3
"""Capture contract v1 rules, owned by the bundled Evidence runtime.

ADR-0018 enforcement site 1: this module is the single owner of the v1
contract surface — the write-side parse/normalize authority, the read-side
full-shape snapshot validator, and the contract-fields JSON Schema fragment
the provider tool schema composes. The provider (server.py) keeps only
Runtime Object fields, path/overwrite boundaries, and Playwright I/O; G6
(scripts/validate_run.py) validates bound manifest request snapshots through
``validate_capture_snapshot`` instead of hand-written partial checks.

Named ``capture_contract.py`` to avoid collision with
``scripts/contract_v1.py`` (the persistent contract, ADR-0017).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CAPTURE_SCHEMA_VERSION = 1
COLOR_SCHEMES = frozenset({"light", "dark", "no-preference"})
RECAPTURE_HINT = "recapture with capture contract schemaVersion=1"
FREEZE_DEFAULTS = {
    "enabled": True,
    "waitFonts": True,
    "networkIdle": False,
}


@dataclass(frozen=True)
class CaptureFact:
    """One host-neutral capture-contract violation (empty facts = valid)."""

    code: str
    detail: str
    expected: str = ""
    actual: str = ""


def _bad_viewport(viewport: dict[str, Any]) -> str | None:
    """First malformed viewport field, or None when the shape is valid.

    Mirrors the parser's field rules exactly so the read side and write side
    cannot disagree on what a valid viewport is.
    """
    width = viewport.get("width")
    height = viewport.get("height")
    dpr = viewport.get("devicePixelRatio")
    scheme = viewport.get("colorScheme")
    if not isinstance(width, int) or width < 1:
        return "viewport.width must be a positive integer"
    if not isinstance(height, int) or height < 1:
        return "viewport.height must be a positive integer"
    if not isinstance(dpr, (int, float)) or dpr <= 0:
        return "viewport.devicePixelRatio must be a positive number"
    if scheme not in COLOR_SCHEMES:
        return (
            f"viewport.colorScheme must be one of {sorted(COLOR_SCHEMES)}; "
            f"got {scheme!r}"
        )
    return None


def _bad_freeze(freeze: dict[str, Any]) -> str | None:
    """First malformed freeze field, or None when the shape is valid."""
    for key in FREEZE_DEFAULTS:
        if not isinstance(freeze.get(key), bool):
            return f"freeze.{key} must be a boolean"
    return None


def parse_capture_contract(args: dict[str, Any]) -> dict[str, Any]:
    """Validate capture contract v1 fields and return a normalized request.

    Write authority (ADR-0018): raises ValueError with a recapture instruction
    for missing/unknown versions or an incomplete viewport. Pure — no browser
    side effects. The normalized output is what the provider echoes into the
    manifest request snapshot, so real snapshots always carry freeze defaults.
    """
    if "schemaVersion" not in args:
        raise ValueError(
            f"capture contract schemaVersion is required; {RECAPTURE_HINT}"
        )
    version = args.get("schemaVersion")
    if version != CAPTURE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported capture schemaVersion {version!r}; {RECAPTURE_HINT}"
        )
    viewport = args.get("viewport")
    if not isinstance(viewport, dict):
        raise ValueError(
            f"viewport object is required for schemaVersion=1; {RECAPTURE_HINT}"
        )
    bad_viewport = _bad_viewport(viewport)
    if bad_viewport is not None:
        raise ValueError(bad_viewport)
    width = viewport["width"]
    height = viewport["height"]
    dpr = viewport["devicePixelRatio"]
    scheme = viewport["colorScheme"]

    freeze_raw = args.get("freeze")
    if freeze_raw is None:
        freeze_raw = {}
    if not isinstance(freeze_raw, dict):
        raise ValueError("freeze must be an object when provided")
    freeze = {
        key: freeze_raw.get(key, FREEZE_DEFAULTS[key])
        for key in FREEZE_DEFAULTS
    }
    bad_freeze = _bad_freeze(freeze)
    if bad_freeze is not None:
        raise ValueError(bad_freeze)

    return {
        "schemaVersion": CAPTURE_SCHEMA_VERSION,
        "viewport": {
            "width": width,
            "height": height,
            "devicePixelRatio": float(dpr),
            "colorScheme": scheme,
        },
        "freeze": freeze,
    }


def validate_capture_snapshot(snapshot: object) -> list[CaptureFact]:
    """Read authority: full-shape validation of a bound manifest snapshot.

    Host-neutral — never raises, returns facts (empty list = valid). Strict on
    the v1 full shape: schemaVersion=1, a complete typed viewport, and a
    complete boolean freeze. The parser normalizes defaults at capture time;
    the read side requires the recorded snapshot to be self-contained so the
    manifest alone can reproduce the capture (ADR-0018). Malformed viewport
    shape or missing freeze therefore fail closed (sanctioned correction; was
    lax in the old hand-written G6 checks). Unknown extra keys are tolerated
    (host-neutral forward compatibility).
    """
    if not isinstance(snapshot, dict):
        return [CaptureFact(
            "missing_schema_version",
            "no request snapshot on the bound entry",
            expected="schemaVersion=1 with viewport and freeze",
            actual=("None" if snapshot is None else type(snapshot).__name__),
        )]
    version = snapshot.get("schemaVersion")
    if version != CAPTURE_SCHEMA_VERSION:
        return [CaptureFact(
            ("missing_schema_version" if version is None
             else "unsupported_schema_version"),
            ("missing schemaVersion" if version is None
             else f"unsupported schemaVersion {version!r}"),
            expected="schemaVersion=1",
            actual=repr(version),
        )]
    viewport = snapshot.get("viewport")
    if not isinstance(viewport, dict):
        return [CaptureFact(
            "missing_viewport",
            "viewport object is required for schemaVersion=1",
            expected="viewport width/height/devicePixelRatio/colorScheme",
            actual=type(viewport).__name__ if viewport is not None else "missing",
        )]
    bad_viewport = _bad_viewport(viewport)
    if bad_viewport is not None:
        return [CaptureFact(
            "bad_viewport_shape",
            bad_viewport,
            expected="viewport width/height/devicePixelRatio/colorScheme",
            actual=bad_viewport,
        )]
    freeze = snapshot.get("freeze")
    if not isinstance(freeze, dict):
        return [CaptureFact(
            "missing_freeze",
            "freeze snapshot is required on the bound entry",
            expected="freeze enabled/waitFonts/networkIdle booleans",
            actual=type(freeze).__name__ if freeze is not None else "missing",
        )]
    bad_freeze = _bad_freeze(freeze)
    if bad_freeze is not None:
        return [CaptureFact(
            "bad_freeze_shape",
            bad_freeze,
            expected="freeze enabled/waitFonts/networkIdle booleans",
            actual=bad_freeze,
        )]
    return []


def capture_contract_schema_fragment() -> dict[str, Any]:
    """JSON Schema fragment for the contract fields (schemaVersion/viewport/freeze).

    The provider composes this into its tool schema alongside its Runtime
    Object fields. const/enum/required/default all come from the same module
    constants the parser uses, so the schema and the parser cannot drift.
    """
    return {
        "properties": {
            "schemaVersion": {
                "type": "integer",
                "description": "Capture contract version. Only 1 is supported.",
                "const": CAPTURE_SCHEMA_VERSION,
            },
            "viewport": {
                "type": "object",
                "description": (
                    "Required capture viewport. Provider does not invent "
                    "desktop defaults."
                ),
                "properties": {
                    "width": {"type": "integer", "minimum": 1},
                    "height": {"type": "integer", "minimum": 1},
                    "devicePixelRatio": {"type": "number", "minimum": 0.1},
                    "colorScheme": {
                        "type": "string",
                        "enum": sorted(COLOR_SCHEMES),
                    },
                },
                "required": [
                    "width",
                    "height",
                    "devicePixelRatio",
                    "colorScheme",
                ],
                "additionalProperties": False,
            },
            "freeze": {
                "type": "object",
                "description": (
                    "Deterministic freeze controls. Defaults: "
                    "enabled=true, waitFonts=true, networkIdle=false."
                ),
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "default": FREEZE_DEFAULTS["enabled"],
                    },
                    "waitFonts": {
                        "type": "boolean",
                        "default": FREEZE_DEFAULTS["waitFonts"],
                    },
                    "networkIdle": {
                        "type": "boolean",
                        "default": FREEZE_DEFAULTS["networkIdle"],
                    },
                },
                "additionalProperties": False,
            },
        },
        "required": ["schemaVersion", "viewport"],
    }
