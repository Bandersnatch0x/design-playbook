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

import math
from dataclasses import dataclass
from typing import Any

CAPTURE_SCHEMA_VERSION = 1
COLOR_SCHEMES = frozenset({"light", "dark", "no-preference"})
MIN_VIEWPORT_DPR = 0.1
RECAPTURE_HINT = "recapture with capture contract schemaVersion=1"
FREEZE_DEFAULTS = {
    "enabled": True,
    "waitFonts": True,
    "networkIdle": False,
}
# Declared design-token axes a capture may be bound to. These are the same
# three axes ``page_defects.declared_token_axes`` reads, so the contract
# boundary and the render-token probe cannot disagree about what is declared.
DESIGN_AXES = ("fontSizes", "colors", "radii")
_DESIGN_AXIS_DESCRIPTIONS = {
    "fontSizes": "Declared type scale: px numbers (or '16px' strings).",
    "colors": "Declared palette: hex or rgb() color literals.",
    "radii": "Declared radius scale: px numbers (or '12px' strings).",
}


@dataclass(frozen=True)
class CaptureFact:
    """One host-neutral capture-contract violation (empty facts = valid)."""

    code: str
    detail: str
    expected: str = ""
    actual: str = ""


def _is_schema_version(value: object) -> bool:
    return type(value) is int and value == CAPTURE_SCHEMA_VERSION


def _bad_viewport(viewport: dict[str, Any]) -> str | None:
    """First malformed viewport field, or None when the shape is valid.

    Mirrors the parser's field rules exactly so the read side and write side
    cannot disagree on what a valid viewport is.
    """
    width = viewport.get("width")
    height = viewport.get("height")
    dpr = viewport.get("devicePixelRatio")
    scheme = viewport.get("colorScheme")
    if type(width) is not int or width < 1:
        return "viewport.width must be a positive integer"
    if type(height) is not int or height < 1:
        return "viewport.height must be a positive integer"
    if (
        type(dpr) not in (int, float)
        or not math.isfinite(dpr)
        or dpr < MIN_VIEWPORT_DPR
    ):
        return (
            "viewport.devicePixelRatio must be a number greater than or equal "
            f"to {MIN_VIEWPORT_DPR}"
        )
    if not isinstance(scheme, str) or scheme not in COLOR_SCHEMES:
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


def _bad_design(design: object) -> str | None:
    """First malformed ``design`` field, or None when the binding is usable.

    A binding is an object of the three named axes, each an **array** of
    literals. Nothing else is a binding: a scalar axis, a name→literal object
    and an explicit ``null`` are caller mistakes at the boundary, not a second
    declaration shape. Which *literal* inside an array is unreadable stays the
    probe's call (a token reference or a relative unit comes back
    ``undecidable``, never clean), so the array items are deliberately not
    typed here.
    """
    if not isinstance(design, dict):
        return (
            "design must be an object of declared token axes; expected one of "
            f"{sorted(DESIGN_AXES)}"
        )
    for key in design:
        if key not in DESIGN_AXES:
            return (
                f"design.{key} is not a declared token axis; "
                f"expected one of {sorted(DESIGN_AXES)}"
            )
    for axis in DESIGN_AXES:
        if axis in design and not isinstance(design[axis], (list, tuple)):
            return f"design.{axis} must be an array of literals"
    return None


def _copy_declared_axes(design: dict[str, Any]) -> dict[str, Any]:
    """Echo a checked declaration as fresh literal arrays, declared axes only.

    An axis the caller omitted stays omitted, so the probe reports it
    ``undecidable`` instead of reading a default as a bound declaration.
    """
    return {axis: list(design[axis]) for axis in DESIGN_AXES if axis in design}


def parse_capture_contract(args: dict[str, Any]) -> dict[str, Any]:
    """Validate capture contract v1 fields and return a normalized request.

    Write authority (ADR-0018): raises ValueError with a recapture instruction
    for missing/unknown versions or an incomplete viewport. Pure — no browser
    side effects. The normalized output is what the provider echoes into the
    manifest request snapshot, so real snapshots always carry freeze defaults
    and, when bound, the declared token axes as literal lists.
    """
    if "schemaVersion" not in args:
        raise ValueError(
            f"capture contract schemaVersion is required; {RECAPTURE_HINT}"
        )
    version = args.get("schemaVersion")
    if not _is_schema_version(version):
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

    # Optional, but an *absent* key is the only way to say "unbound": a
    # present key must be a readable binding, so an explicit null fails here
    # like any other malformed declaration.
    design: dict[str, Any] | None = None
    if "design" in args:
        bad_design = _bad_design(args.get("design"))
        if bad_design is not None:
            raise ValueError(bad_design)
        design = _copy_declared_axes(args["design"])

    request = {
        "schemaVersion": CAPTURE_SCHEMA_VERSION,
        "viewport": {
            "width": width,
            "height": height,
            "devicePixelRatio": float(dpr),
            "colorScheme": scheme,
        },
        "freeze": freeze,
    }
    if design is not None:
        request["design"] = design
    return request


def validate_capture_snapshot(snapshot: object) -> list[CaptureFact]:
    """Read authority: full-shape validation of a bound manifest snapshot.

    Host-neutral — never raises, returns facts (empty list = valid). Strict on
    the v1 full shape: schemaVersion=1, a complete typed viewport, and a
    complete boolean freeze. The parser normalizes defaults at capture time;
    the read side requires the recorded snapshot to be self-contained so the
    manifest alone can reproduce the capture (ADR-0018). Malformed viewport
    shape or missing freeze therefore fail closed (sanctioned correction; was
    lax in the old hand-written G6 checks). ``design`` is optional and its
    *absence* means the capture declared no token binding; a present key —
    including an explicit null — must be a readable object of array axes, so
    an unbound capture is never read as a bound clean one. Unknown extra keys
    are tolerated (host-neutral forward compatibility).
    """
    if not isinstance(snapshot, dict):
        return [CaptureFact(
            "missing_schema_version",
            "no request snapshot on the bound entry",
            expected="schemaVersion=1 with viewport and freeze",
            actual=("None" if snapshot is None else type(snapshot).__name__),
        )]
    version = snapshot.get("schemaVersion")
    if not _is_schema_version(version):
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
    # ``design`` is the one optional contract field, and absence is the only
    # way to say "unbound": every render-token axis is then undecidable.
    # A present key — including an explicit null — must be readable, so a
    # malformed binding can never be read as if it were a valid one.
    if "design" in snapshot:
        bad_design = _bad_design(snapshot.get("design"))
        if bad_design is not None:
            return [CaptureFact(
                "bad_design_shape",
                bad_design,
                expected=(
                    "design object with declared axes "
                    f"{sorted(DESIGN_AXES)} as literal lists"
                ),
                actual=bad_design,
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
                    "devicePixelRatio": {
                        "type": "number",
                        "minimum": MIN_VIEWPORT_DPR,
                    },
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
            "design": {
                "type": "object",
                "description": (
                    "Optional declared design tokens the screenshot probe "
                    "compares rendered computed values against. Omit the key "
                    "entirely to declare no binding; every axis is then "
                    "reported undecidable, never clean. An axis is an array "
                    "of literals — a scalar, a name→literal object or an "
                    "explicit null is rejected before the browser starts. "
                    "Root-level only, no token-reference resolution: a "
                    "literal the probe cannot read stays undecidable."
                ),
                "properties": {
                    axis: {
                        "type": "array",
                        "description": _DESIGN_AXIS_DESCRIPTIONS[axis],
                    }
                    for axis in DESIGN_AXES
                },
                "additionalProperties": False,
            },
        },
        "required": ["schemaVersion", "viewport"],
    }


def capture_result_schema() -> dict[str, Any]:
    """JSON Schema for the payload ``execute_capture_plan`` returns (T-145).

    Mirrors ``capture_runtime._captured``/``_failed``: five keys always
    present, ``request`` only once a snapshot exists, ``warnings`` only on a
    misrooted run, ``probe_artifact`` only for a probed screenshot. The
    nested ``request`` reuses the contract fragment so the advertised shape
    and the parser cannot drift.
    """
    contract = capture_contract_schema_fragment()
    return {
        "type": "object",
        "properties": {
            "artifact": {"type": "string"},
            "observed_state": {"type": "string"},
            "result": {"type": "string", "enum": ["captured", "failed"]},
            "error": {"type": "string"},
            "written_path": {"type": "string"},
            "request": {
                "type": "object",
                "properties": contract["properties"],
                "required": contract["required"],
                "additionalProperties": False,
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
            "probe_artifact": {"type": "string"},
        },
        "required": [
            "artifact",
            "observed_state",
            "result",
            "error",
            "written_path",
        ],
        "additionalProperties": False,
    }
