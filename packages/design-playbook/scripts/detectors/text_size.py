"""A11Y-05 — readable text size and scaling (machine detector).

Payload contract (computed text metrics plus the 200 percent zoom capture)::

    {"nodes": [
        {"label": "Caption", "fontSizePx": 10, "fontWeight": 400,
         "script": "latin"},
        {"label": "Body", "fontSizePx": 16, "fontWeight": 300,
         "script": "cjk"}],
     "zoom": {"percent": 200, "clipped": [{"label": "Card title"}]}}

Floor resolution follows the registry threshold reading: Latin-script text
reaches 11 CSS px, CJK text 12 CSS px, and weights under 400 are not used
below 16 CSS px. Equality passes — 11 px Latin, 12 px CJK, and a thin weight
at exactly 16 px are not findings.

The ``zoom`` capture is required: the rule also demands text stays complete
at 200 percent, so a payload without it raises
:class:`~detectors._shared.DetectorInputError` instead of passing silently.
"""
from __future__ import annotations

from typing import Any

from ._shared import (
    DetectorInputError,
    as_mapping,
    as_number,
    as_rows,
    as_text,
    finding,
)

RULE_ID = "A11Y-05"
LATIN_MIN_PX = 11.0
CJK_MIN_PX = 12.0
THIN_WEIGHT_BELOW = 400
THIN_WEIGHT_MIN_PX = 16.0
TEXT_ZOOM_PERCENT = 200.0


def detect(payload: object) -> list[dict[str, Any]]:
    """Return one finding per node under its size floor or thin below 16 px."""
    data = as_mapping(payload, "payload")
    findings: list[dict[str, Any]] = []
    for node_index, raw_node in enumerate(as_rows(data.get("nodes"), "nodes")):
        field = f"nodes[{node_index}]"
        node = as_mapping(raw_node, field)
        label = as_text(node, "label", field)
        size = as_number(node, "fontSizePx", field, minimum=0.0)
        weight = as_number(node, "fontWeight", field, minimum=1.0)
        script = node.get("script")
        if script not in {"latin", "cjk"}:
            raise DetectorInputError(
                f"{field}: script must be 'latin' or 'cjk'"
            )
        floor = CJK_MIN_PX if script == "cjk" else LATIN_MIN_PX
        if size < floor:
            findings.append(finding(
                RULE_ID,
                f"{label}: {script} text at {size:g}px is under the "
                f"{floor:g}px floor",
                label=label,
                script=script,
                fontSizePx=size,
                floor=floor,
            ))
        if weight < THIN_WEIGHT_BELOW and size < THIN_WEIGHT_MIN_PX:
            findings.append(finding(
                RULE_ID,
                f"{label}: weight {weight:g} at {size:g}px is under the "
                f"{THIN_WEIGHT_MIN_PX:g}px thin-weight floor",
                label=label,
                fontWeight=weight,
                fontSizePx=size,
                floor=THIN_WEIGHT_MIN_PX,
            ))

    zoom = as_mapping(data.get("zoom"), "zoom")
    percent = as_number(zoom, "percent", "zoom", minimum=0.0)
    if percent < TEXT_ZOOM_PERCENT:
        raise DetectorInputError(
            f"zoom.percent: text-zoom capture must be >= {TEXT_ZOOM_PERCENT:g}"
        )
    for clipped_index, raw_clipped in enumerate(
            as_rows(zoom.get("clipped"), "zoom.clipped")):
        field = f"zoom.clipped[{clipped_index}]"
        clipped = as_mapping(raw_clipped, field)
        label = as_text(clipped, "label", field)
        findings.append(finding(
            RULE_ID,
            f"{label}: text is clipped or truncated at {percent:g}% zoom",
            label=label,
            textZoomPercent=percent,
        ))
    return findings
