"""G11 coverage-statement gate (vNext S1, review-prototype Q7).

Minimal existence check on the six-block point-back report: when the report
uses the vNext six-block shape, it must contain a ``## Coverage statement``
block with both required sub-structures — the exhaustive-review completion
status and the explicit unreviewed list. Content is not judged (coverage
truthfulness and sampling reasons stay protocol-side).

vNext S3 extension (review-prototype 2.1 / Q3=A): the coverage statement
may declare the five-state x page sampling matrix — one list line per
declared spec-L5 cell, either naming sampling evidence or marking the cell
explicitly unreviewed with a reason. When the matrix block is present,
``check_sampling_matrix`` enumerates the cells declared by the spec and
reports every gap: a cell with no matrix line and no unreviewed entry is a
machine-enumerable coverage gap (unreviewed items never default to pass).
Legacy or matrix-less reports do not trigger the extension.

vNext S6 extension (loop-prototype 1.2 tier matrix): the full profile
declares "sampling matrix fully executed" as a P3 obligation — for a run
whose effective tier is P3 the matrix block is mandatory, not opt-in. The
check fires on the declared tier only (legacy runs without a run-profile
block are never re-checked), resolving the S3 leftover coupling of matrix
completeness to tier.

Old-format reports (no new blocks, no additional finding fields, no
invalidated block) do not trigger the gate: the six-block extension is
additive and legacy reports keep passing (compatibility contract).
``required=True`` (strict mode) forces the check regardless of shape.
"""
from __future__ import annotations

import re
from pathlib import Path

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.g1_spec import FIVE_STATES, _layer_body, _table_by_header

COVERAGE_HEADING = re.compile(r"^#{2,6}\s*Coverage statement\s*$", re.M | re.I)
VNEXT_BLOCK_MARKERS = (
    "## Positive findings",
    "## Coverage statement",
    "## Limitations statement",
    "invalidated:",
)
EXTRA_FIELD_MARKER = re.compile(
    r"^(track|disposition|confidence|rule|dd|dimension|face|basis):"
    r"[ \t]*\S", re.I | re.M)
EXHAUSTIVE_MARKERS = ("必审", "exhaustive", "must-review")
UNREVIEWED_MARKERS = ("未审", "unreviewed", "not-reviewed", "declared-unreviewed")

# Sampling-matrix block (S3, Q3=A): the marker line opts the report into
# per-cell enumeration; each list line names one spec-declared cell. The
# state token is validated against FIVE_STATES by the check itself so a
# typo like `loaded` surfaces as an unknown cell instead of silence.
MATRIX_MARKER = re.compile(
    r"^\s*(采样矩阵|sampling-matrix)\s*:\s*$", re.M)
MATRIX_LINE = re.compile(
    r"^[ \t]*[-*][ \t]+(\S+)[ \t]*/[ \t]*([A-Za-z][A-Za-z-]*)"
    r"[ \t]*:[ \t]*(.*)$", re.M)
UNREVIEWED_VALUE = re.compile(
    r"^(未审|unreviewed|not-reviewed|declared-unreviewed)\b", re.I)


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


def spec_matrix_cells(spec_text: str) -> list[tuple[str, str]]:
    """Enumerate ``(page, state)`` cells declared by the spec L5 matrix.

    Only cells with a declared value count: a blank cell declares nothing
    to sample (blank cells are G1's diagnostic, not coverage input).
    """
    matrix = _table_by_header(
        _layer_body(spec_text, "L5"), ("Page",) + FIVE_STATES)
    if matrix is None or len(matrix) < 2:
        return []
    header = matrix[0]
    state_idx = [header.index(state) for state in FIVE_STATES]
    cells: list[tuple[str, str]] = []
    for row in matrix[1:]:
        page = row[0] if row else ""
        if not page:
            continue
        for state, index in zip(FIVE_STATES, state_idx):
            value = row[index] if index < len(row) else ""
            if value:
                cells.append((page, state))
    return cells


def parse_matrix_lines(section: str) -> list[tuple[str, str, str]]:
    """Parse ``- <page>/<state>: <value>`` lines from the coverage section."""
    return [
        (match.group(1), match.group(2), match.group(3).strip())
        for match in MATRIX_LINE.finditer(section)
    ]


def check_sampling_matrix(
        pointback_text: str,
        spec_text: str,
        evidence_dir: Path | None = None,
        tier: str | None = None) -> list[Finding]:
    """Five-state x page sampling-matrix gap check (S3, Q3=A).

    Fires only when the Coverage statement carries the matrix marker; the
    cells come from the spec L5 declaration. Every declared cell must have
    exactly one matrix line — naming sampling evidence or an explicit
    unreviewed entry with a reason. A cell with neither is a gap.

    S6: ``tier='P3'`` (the effective tier after recorded upgrades) makes
    the matrix block itself mandatory — the full profile's "sampling matrix
    fully executed" obligation is machine-enforced as block existence plus
    the S3 per-cell enumeration (loop-prototype 1.2 / 1.6).
    """
    section = _section_after_heading(pointback_text, COVERAGE_HEADING)
    if not section or not MATRIX_MARKER.search(section):
        if tier == "P3":
            actual = ("no Coverage statement"
                      if not section else "no sampling-matrix block")
            return [finding(
                "G11.matrix_required",
                "G11 coverage: P3 (full profile) demands the five-state x "
                f"page sampling matrix — {actual}",
                owner="point-back.md#coverage",
                expected="Coverage statement with a sampling-matrix block "
                         "naming every spec-declared cell",
                actual=actual,
                repair="Execute the sampling matrix (one line per "
                       "spec-declared cell: sampling evidence or an "
                       "explicit unreviewed entry with a reason)",
            )]
        return []  # matrix block absent: not opted in, nothing to enumerate
    errs: list[Finding] = []
    declared = spec_matrix_cells(spec_text)
    if not declared:
        errs.append(finding(
            "G11.matrix_no_spec",
            "G11 coverage: sampling matrix declared but the spec L5 "
            "five-state matrix is missing or empty (cells cannot be "
            "enumerated)",
            owner="spec.md#L5",
            expected="spec-schema: 2 five-state matrix with >=1 page",
            actual="missing or empty",
            repair="Declare the five-state matrix in the spec or drop the "
                   "coverage matrix block",
        ))
        return errs
    declared_set = set(declared)
    seen: dict[tuple[str, str], int] = {}
    sampled: set[tuple[str, str]] = set()
    for page, state, value in parse_matrix_lines(section):
        cell = (page, state)
        if state not in FIVE_STATES or cell not in declared_set:
            errs.append(finding(
                "G11.matrix_unknown_cell",
                f"G11 coverage: sampling matrix names {page}/{state} which "
                "the spec L5 matrix does not declare",
                owner="point-back.md#coverage",
                expected="a spec-declared page/state cell",
                actual=f"{page}/{state}",
                repair="Fix the cell name or declare it in the spec L5 "
                       "matrix",
            ))
            continue
        seen[cell] = seen.get(cell, 0) + 1
        if not value:
            errs.append(finding(
                "G11.matrix_blank",
                f"G11 coverage: sampling matrix cell {page}/{state} has a "
                "blank value",
                owner="point-back.md#coverage",
                expected="sampling evidence or an unreviewed marker with "
                         "a reason",
                actual="blank",
                repair=f"Sample {page}/{state} or mark it explicitly "
                       "unreviewed with a reason",
            ))
            continue
        if UNREVIEWED_VALUE.match(value):
            reason = UNREVIEWED_VALUE.sub("", value).strip("（）()：:—- ")
            if not reason:
                errs.append(finding(
                    "G11.matrix_unreviewed_reason",
                    f"G11 coverage: cell {page}/{state} marked unreviewed "
                    "without an observable reason (blank unreviewed is "
                    "invalid)",
                    owner="point-back.md#coverage",
                    expected="unreviewed with a one-line reason",
                    actual="reason missing",
                    repair=f"State why {page}/{state} stayed unreviewed",
                ))
            continue
        sampled.add(cell)
        token_match = re.match(
            r"evidence/[^\s（）(),，;；]+", value, re.I)
        if (token_match and evidence_dir is not None
                and evidence_dir.is_dir()):
            token = token_match.group(0)
            leaf = token[len("evidence/"):]
            if not (evidence_dir / leaf).is_file():
                errs.append(finding(
                    "G11.matrix_artifact_missing",
                    f"G11 coverage: sampling matrix cell {page}/{state} "
                    f"references missing artifact {token}",
                    owner=f"evidence/{leaf}",
                    expected="artifact file on disk",
                    actual="missing",
                    repair=f"Capture or restore {token}",
                ))
    for cell, count in seen.items():
        if count > 1:
            errs.append(finding(
                "G11.matrix_duplicate",
                f"G11 coverage: sampling matrix lists {cell[0]}/{cell[1]} "
                f"{count} times",
                owner="point-back.md#coverage",
                expected="exactly one line per cell",
                actual=f"{count} lines",
                repair=f"Keep one line for {cell[0]}/{cell[1]}",
            ))
    for cell in declared:
        if cell in seen:
            continue
        errs.append(finding(
            "G11.matrix_gap",
            f"G11 coverage: sampling-matrix gap — {cell[0]}/{cell[1]} has "
            "no evidence and is not in the explicit unreviewed list",
            owner="point-back.md#coverage",
            expected=f"sampling evidence or an unreviewed entry for "
                     f"{cell[0]}/{cell[1]}",
            actual="no matrix line",
            repair=f"Sample {cell[0]}/{cell[1]} or declare it unreviewed "
                   "with a reason",
        ))
    return errs
