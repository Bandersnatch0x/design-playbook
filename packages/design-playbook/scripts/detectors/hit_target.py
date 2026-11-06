"""A11Y-04 — hit-target size (machine detector).

Payload contract (measured targets per declared viewport)::

    {"viewports": [
        {"name": "desktop", "touchPrimary": false, "targets": [
            {"label": "Row menu", "widthPx": 20, "heightPx": 20}]},
        {"name": "mobile", "touchPrimary": true, "targets": [
            {"label": "Close", "widthPx": 44, "heightPx": 44}]}]}

Floor resolution follows the registry threshold reading: the shorter edge
must reach 24 CSS px on every viewport, and 44 CSS px on viewports the
contract declares touch-primary. Equality passes — a 24 x 24 target is not a
finding.

Not covered (documented false-positive boundary): overlapping expanded hit
areas need neighbour geometry, which the tap rows do not carry; that stays a
prose signal on the rule.
"""
from __future__ import annotations

from typing import Any

from ._shared import (
    as_bool,
    as_mapping,
    as_number,
    as_rows,
    as_text,
    finding,
)

RULE_ID = "A11Y-04"
HIT_AREA_FLOOR_PX = 24.0
TOUCH_TARGET_PX = 44.0


def detect(payload: object) -> list[dict[str, Any]]:
    """Return one finding per target whose shorter edge is under its floor."""
    viewports = as_rows(as_mapping(payload, "payload").get("viewports"),
                        "viewports")
    findings: list[dict[str, Any]] = []
    for viewport_index, raw_viewport in enumerate(viewports):
        field = f"viewports[{viewport_index}]"
        viewport = as_mapping(raw_viewport, field)
        name = as_text(viewport, "name", field)
        touch_primary = as_bool(viewport, "touchPrimary", field)
        floor = TOUCH_TARGET_PX if touch_primary else HIT_AREA_FLOOR_PX
        floor_name = "touch 44px" if touch_primary else "hit-area 24px"
        targets = as_rows(viewport.get("targets"), f"{name}.targets")
        for target_index, raw_target in enumerate(targets):
            target_field = f"{name}.targets[{target_index}]"
            target = as_mapping(raw_target, target_field)
            label = as_text(target, "label", target_field)
            width = as_number(target, "widthPx", target_field, minimum=0.0)
            height = as_number(target, "heightPx", target_field, minimum=0.0)
            shorter = min(width, height)
            if shorter < floor:
                findings.append(finding(
                    RULE_ID,
                    f"{name}: {label} hit area {width:g}x{height:g}px is "
                    f"under the {floor_name} floor",
                    viewport=name,
                    label=label,
                    widthPx=width,
                    heightPx=height,
                    floor=floor,
                ))
    return findings
