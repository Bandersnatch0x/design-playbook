"""A11Y-03 — contrast in every declared appearance (machine detector).

Payload contract (colors ``#rgb`` or ``#rrggbb``)::

    {"appearances": [
        {"name": "light", "pairs": [
            {"label": "Body copy", "foreground": "#767676",
             "background": "#ffffff", "kind": "text",
             "fontSizePx": 16, "bold": false},
            {"label": "Input border", "foreground": "#949494",
             "background": "#ffffff", "kind": "nontext"}]}]}

Floor resolution follows the registry threshold reading: ``kind: text`` uses
4.5:1, except 24 CSS px and up (or 19 CSS px and up at weight 700+) which is
large text at 3:1; ``kind: nontext`` (control boundaries, focus indicators,
state icons, meaningful chart marks) uses 3:1. Equality passes — a pair
sitting exactly on its floor is not a finding.

Not covered (documented false-positive boundary): text over images or
gradients has no single background color, and the cross-appearance
"increased contrast changes nothing" signal needs node matching across
captures. Both are captured by the rule's prose signals, not this detector.
"""
from __future__ import annotations

import re
from typing import Any

from ._shared import (
    DetectorInputError,
    as_bool,
    as_mapping,
    as_number,
    as_rows,
    as_text,
    finding,
)

RULE_ID = "A11Y-03"
TEXT_CONTRAST = 4.5
LARGE_TEXT_CONTRAST = 3.0
NON_TEXT_CONTRAST = 3.0
LARGE_TEXT_FROM_PX = 24.0
LARGE_BOLD_TEXT_FROM_PX = 19.0
BOLD_WEIGHT = 700

_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _channels(color: str, field: str) -> tuple[float, float, float]:
    match = _HEX.match(color.strip())
    if match is None:
        raise DetectorInputError(
            f"{field}: expected #rgb or #rrggbb, got {color!r}"
        )
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return tuple(  # type: ignore[return-value]
        int(digits[start:start + 2], 16) / 255 for start in (0, 2, 4)
    )


def _linear(channel: float) -> float:
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str, field: str = "color") -> float:
    """WCAG 2.x relative luminance of one hex color."""
    red, green, blue = _channels(color, field)
    return 0.2126 * _linear(red) + 0.7152 * _linear(green) + 0.0722 * _linear(blue)


def contrast_ratio(foreground: str, background: str, field: str = "pair") -> float:
    """WCAG 2.x contrast ratio (1.0–21.0), order independent."""
    first = relative_luminance(foreground, field)
    second = relative_luminance(background, field)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _floor(pair: Any, field: str) -> tuple[float, str]:
    kind = pair.get("kind")
    if kind == "nontext":
        return NON_TEXT_CONTRAST, "non-text 3:1"
    if kind != "text":
        raise DetectorInputError(f"{field}: kind must be 'text' or 'nontext'")
    size = as_number(pair, "fontSizePx", field, minimum=0.0)
    bold = as_bool(pair, "bold", field)
    if size >= LARGE_TEXT_FROM_PX or (bold and size >= LARGE_BOLD_TEXT_FROM_PX):
        return LARGE_TEXT_CONTRAST, "large-text 3:1"
    return TEXT_CONTRAST, "text 4.5:1"


def detect(payload: object) -> list[dict[str, Any]]:
    """Return one finding per pair below its floor, in every appearance."""
    appearances = as_rows(as_mapping(payload, "payload").get("appearances"),
                          "appearances")
    findings: list[dict[str, Any]] = []
    for appearance_index, raw_appearance in enumerate(appearances):
        field = f"appearances[{appearance_index}]"
        appearance = as_mapping(raw_appearance, field)
        name = as_text(appearance, "name", field)
        pairs = as_rows(appearance.get("pairs"), f"{name}.pairs")
        for pair_index, raw_pair in enumerate(pairs):
            pair_field = f"{name}.pairs[{pair_index}]"
            pair = as_mapping(raw_pair, pair_field)
            label = as_text(pair, "label", pair_field)
            foreground = as_text(pair, "foreground", pair_field)
            background = as_text(pair, "background", pair_field)
            floor, floor_name = _floor(pair, pair_field)
            ratio = contrast_ratio(foreground, background, pair_field)
            if ratio < floor:
                findings.append(finding(
                    RULE_ID,
                    f"{name}: {label} contrast {ratio:.2f}:1 is below "
                    f"{floor:g}:1 ({floor_name})",
                    appearance=name,
                    label=label,
                    foreground=foreground,
                    background=background,
                    ratio=round(ratio, 3),
                    floor=floor,
                ))
    return findings
