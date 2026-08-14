"""G11 coverage-statement gate (vNext S1, review-prototype Q7).

Minimal existence check on the six-block point-back report: when the report
uses the vNext six-block shape, it must contain a ``## Coverage statement``
block with both required sub-structures — the exhaustive-review completion
status and the explicit unreviewed list. Content is not judged (coverage
truthfulness and sampling reasons stay protocol-side).

Old-format reports (no new blocks, no additional finding fields, no
invalidated block) do not trigger the gate: the six-block extension is
additive and legacy reports keep passing (compatibility contract).
``required=True`` (strict mode) forces the check regardless of shape.
"""
from __future__ import annotations

import re

from design_playbook.scripts._diagnostics import Finding, finding

COVERAGE_HEADING = re.compile(r"^#{2,6}\s*Coverage statement\s*$", re.M | re.I)
VNEXT_BLOCK_MARKERS = (
    "## Positive findings",
    "## Coverage statement",
    "## Limitations statement",
    "invalidated:",
)
EXTRA_FIELD_MARKER = re.compile(
    r"^(track|disposition|confidence|rule|dd):[ \t]*\S", re.I | re.M)
EXHAUSTIVE_MARKERS = ("必审", "exhaustive", "must-review")
UNREVIEWED_MARKERS = ("未审", "unreviewed", "not-reviewed", "declared-unreviewed")


def _section_after_heading(text: str, heading: re.Pattern[str]) -> str:
    match = heading.search(text)
    if match is None:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"^#{1,6}\s+\S", rest, re.M)
    return rest[:next_heading.start()] if next_heading else rest


def is_vnext_report(text: str) -> bool:
    """True when the report declares the six-block shape or new-axis fields."""
    if any(marker in text for marker in VNEXT_BLOCK_MARKERS):
        return True
    return bool(EXTRA_FIELD_MARKER.search(text))


def check_coverage(text: str, *, required: bool = False) -> list[Finding]:
    """Return G11 findings (empty = pass or gate not triggered)."""
    if not required and not is_vnext_report(text):
        return []
    errs: list[Finding] = []
    section = _section_after_heading(text, COVERAGE_HEADING)
    if not COVERAGE_HEADING.search(text):
        errs.append(finding(
            "G11.missing_coverage_block",
            "G11 coverage: vNext-shaped point-back must contain a "
            "'## Coverage statement' block",
            owner="point-back.md#coverage",
            expected="## Coverage statement section",
            actual="missing",
            repair="Record exhaustive-review completion, sampling, and the "
                   "explicit unreviewed list",
        ))
        return errs
    has_exhaustive = any(
        marker in section for marker in EXHAUSTIVE_MARKERS
    )
    if not has_exhaustive:
        errs.append(finding(
            "G11.missing_exhaustive_status",
            "G11 coverage: Coverage statement lacks the exhaustive-review "
            "completion status",
            owner="point-back.md#coverage",
            expected="a 必审/exhaustive completion line",
            actual="missing",
            repair="State which exhaustive (must-review) items completed "
                   "and which are coverage gaps",
        ))
    has_unreviewed = any(
        marker in section for marker in UNREVIEWED_MARKERS
    )
    if not has_unreviewed:
        errs.append(finding(
            "G11.missing_unreviewed_list",
            "G11 coverage: Coverage statement lacks the explicit "
            "unreviewed list (未审 items do not default to pass)",
            owner="point-back.md#coverage",
            expected="an explicit 未审/unreviewed list (empty list is "
                     "still named)",
            actual="missing",
            repair="List what was sampled-but-not-covered or state the "
                   "empty unreviewed set explicitly",
        ))
    return errs
