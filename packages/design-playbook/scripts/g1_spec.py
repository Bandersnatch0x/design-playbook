"""G1 spec-shape gate (ADR-0023 + vNext S1 deepening).

Owns the success-shape rule set for ``spec.md``: L1-L6 layers present and
every top-level L6 acceptance criterion is Given/When/Then in order. The
orchestrator (``validate_run.py``) also imports ``_l6_items`` here to size
the G2 ledger and G6 binding checks against the same spec read.

vNext S1 deepening (matrix-draft Q2=A minimal gate): when the spec declares
``spec-schema: 2``, G1 additionally requires the L2-L5 structured field
blocks — per-page duty table, path table, per-page five-state matrix — with
per-page five-state completeness and L6 <-> path-table reference closure.
The deepened checks fire only for new-format specs; historical specs keep
the legacy shape (compatibility contract: no retroactive re-checking).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from design_playbook.scripts._diagnostics import Finding, finding

SPEC_LAYERS = ["L1", "L2", "L3", "L4", "L5", "L6"]

SPEC_SCHEMA_2 = re.compile(r"spec-schema:\s*2\b")
FIVE_STATES = ("initial", "loading", "success", "failure", "empty")
PATH_REF = re.compile(r"\(path:\s*(P\d+)\)")


@dataclass(frozen=True)
class SpecificationCriterion:
    """One owner-parsed authoritative L6 acceptance criterion."""

    criterion_id: str
    title: str | None
    given: str
    when: str
    then: str


@dataclass(frozen=True)
class SpecificationProjection:
    """Immutable intent values owned by one Specification."""

    summary: str
    criteria: tuple[SpecificationCriterion, ...]


class SpecificationProjectionError(ValueError):
    """A stable, path-free reason that intent cannot be projected."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class _L6Syntax:
    """Single owner parse used by both validation and projection."""

    text: str
    positions: tuple[tuple[str, int | None, int | None], ...]

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(name for name, start, _ in self.positions if start is None)

    @property
    def ordered(self) -> bool:
        starts = tuple(start for _, start, _ in self.positions)
        return None not in starts and starts == tuple(sorted(starts))

    def projection(self, criterion_id: str) -> SpecificationCriterion:
        offsets = {name: (start, end) for name, start, end in self.positions}
        given_start, given_end = offsets["Given"]
        when_start, when_end = offsets["When"]
        then_start, then_end = offsets["Then"]
        assert None not in (
            given_start, given_end, when_start, when_end, then_start, then_end)
        assert given_start < when_start < then_start

        return SpecificationCriterion(
            criterion_id=criterion_id,
            title=_criterion_title(self.text[:given_start]),
            given=_clause(self.text[given_end:when_start]),
            when=_clause(self.text[when_end:then_start]),
            then=_text_value(self.text[then_end:]),
        )


def _l6_body(text: str) -> str:
    parts = re.split(r"^#+\s*L6\b", text, maxsplit=1, flags=re.M)
    if len(parts) == 1:
        return ""
    return re.split(r"^#+\s+", parts[1], maxsplit=1, flags=re.M)[0]


def _l6_items(text: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(
        r"^(?:[-*]|\d+[.)])\s+(.*?)(?=^(?:[-*]|\d+[.)])\s+|\Z)",
        _l6_body(text),
        re.M | re.S,
    )]


def _l6_syntax(text: str) -> tuple[_L6Syntax, ...]:
    items: list[_L6Syntax] = []
    for item in _l6_items(text):
        positions = tuple(
            (keyword, match.start(), match.end()) if match else
            (keyword, None, None)
            for keyword in ("Given", "When", "Then")
            for match in (re.search(rf"\b{keyword}\b", item, re.I),)
        )
        items.append(_L6Syntax(text=item, positions=positions))
    return tuple(items)


def _text_value(text: str) -> str:
    return " ".join(text.strip().split())


def _criterion_title(text: str) -> str | None:
    value = _text_value(text)
    if not value:
        return None
    if value.endswith(":"):
        value = value[:-1].rstrip()
    return value or None


def _clause(text: str) -> str:
    return _text_value(text).strip(" ,，")


def _l1_summary(text: str) -> str:
    parts = re.split(
        r"^#+\s*L1\b[^\r\n]*(?:\r?\n|\Z)",
        text,
        maxsplit=1,
        flags=re.M,
    )
    body = (
        re.split(r"^##\s+", parts[1], maxsplit=1, flags=re.M)[0]
        if len(parts) == 2 else ""
    )
    for line in body.splitlines():
        value = re.sub(r"^(?:[-*]|\d+[.)])\s+", "", line.strip())
        if not value:
            continue
        labelled = re.match(
            r"(?:Outcome summary|Goal|用户可见目标|一句话定义)\s*[:：]\s*(.*)",
            value,
            re.I,
        )
        if labelled:
            return _text_value(labelled.group(1))
        return _text_value(value)
    return ""


def project_specification(text: str) -> SpecificationProjection:
    """Return the Specification owner's typed intent projection."""
    summary = _l1_summary(text)
    if not summary:
        raise SpecificationProjectionError("summary-missing")

    syntax = _l6_syntax(text)
    if not syntax:
        raise SpecificationProjectionError("criteria-missing")

    criteria: list[SpecificationCriterion] = []
    normalized: set[tuple[str | None, str, str, str]] = set()
    for number, item in enumerate(syntax, 1):
        if item.missing:
            raise SpecificationProjectionError("criterion-incomplete")
        if not item.ordered:
            raise SpecificationProjectionError("criterion-out-of-order")
        criterion = item.projection(f"L6.{number}")
        if not all((criterion.given, criterion.when, criterion.then)):
            raise SpecificationProjectionError("criterion-malformed")
        identity = (
            criterion.title,
            criterion.given,
            criterion.when,
            criterion.then,
        )
        if identity in normalized:
            raise SpecificationProjectionError("criterion-duplicate")
        normalized.add(identity)
        criteria.append(criterion)
    return SpecificationProjection(summary=summary, criteria=tuple(criteria))


def _layer_body(text: str, layer: str) -> str:
    """Slice one L<k> layer body, including its sub-headings (### blocks).

    The structured-field tables live under sub-headings inside the layer
    (e.g. ``### Page duties``), so the body extends to the next same-or-
    higher level heading (``##``), not to the first sub-heading.
    """
    parts = re.split(rf"^#+\s*{layer}\b", text, maxsplit=1, flags=re.M)
    if len(parts) == 1:
        return ""
    return re.split(r"^##\s+", parts[1], maxsplit=1, flags=re.M)[0]


def _tables(body: str) -> list[list[list[str]]]:
    """Parse markdown tables in a section body into row-cell matrices."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
                continue  # separator row
            current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _table_by_header(body: str, required: tuple[str, ...]) -> list[list[str]] | None:
    """Return the first table whose header row contains all required cells."""
    for table in _tables(body):
        if table and all(cell in table[0] for cell in required):
            return table
    return None


def _deepened_findings(text: str) -> list[Finding]:
    """spec-schema: 2 structured-field checks (matrix-draft Q2=A)."""
    errs: list[Finding] = []

    duty_table = _table_by_header(_layer_body(text, "L2"), ("Page", "Duty"))
    if duty_table is None or len(duty_table) < 2:
        errs.append(finding(
            "G1.deep_l2_duties",
            "G1 spec: L2 structured page-duty table (Page | Duty) missing "
            "or empty",
            owner="spec.md#L2",
            expected="Page/Duty table with >=1 page row",
            actual="missing or empty",
            repair="Add the per-page duty table to L2 (spec-schema: 2)",
        ))
    path_table = _table_by_header(_layer_body(text, "L3"), ("Path", "Steps"))
    if path_table is None or len(path_table) < 2:
        errs.append(finding(
            "G1.deep_l3_paths",
            "G1 spec: L3 structured path table (Path | Steps) missing or "
            "empty",
            owner="spec.md#L3",
            expected="Path/Steps table with >=1 path row",
            actual="missing or empty",
            repair="Add the path table to L3 (spec-schema: 2)",
        ))
    matrix = _table_by_header(
        _layer_body(text, "L5"), ("Page",) + FIVE_STATES)
    if matrix is None or len(matrix) < 2:
        errs.append(finding(
            "G1.deep_l5_matrix",
            "G1 spec: L5 per-page five-state matrix missing or empty",
            owner="spec.md#L5",
            expected="Page matrix with columns "
                     f"{'/'.join(FIVE_STATES)} and >=1 page row",
            actual="missing or empty",
            repair="Add the per-page five-state matrix to L5 (spec-schema: 2)",
        ))

    pages: set[str] = set()
    if matrix is not None and len(matrix) >= 2:
        header = matrix[0]
        state_idx = [header.index(state) for state in FIVE_STATES]
        for row in matrix[1:]:
            page = row[0] if row else ""
            if not page:
                errs.append(finding(
                    "G1.deep_l5_page_blank",
                    "G1 spec: L5 five-state matrix has a blank page cell",
                    owner="spec.md#L5",
                    expected="named page per row",
                    actual="blank",
                    repair="Name the page or drop the row",
                ))
                continue
            pages.add(page)
            for state, index in zip(FIVE_STATES, state_idx):
                value = row[index] if index < len(row) else ""
                if not value:
                    errs.append(finding(
                        "G1.deep_l5_state",
                        f"G1 spec: L5 five-state matrix page {page!r} has "
                        f"no {state} value",
                        owner=f"spec.md#L5.{page}",
                        expected=f"enumerable {state} value",
                        actual="blank",
                        repair=f"Fill the {state} cell for page {page!r} "
                               "(or record n/a with a reason)",
                    ))

    if duty_table is not None and len(duty_table) >= 2:
        duty_pages = {row[0] for row in duty_table[1:] if row and row[0]}
        for page in sorted(pages - duty_pages):
            errs.append(finding(
                "G1.deep_page_duty",
                f"G1 spec: page {page!r} appears in the L5 matrix without "
                "an L2 duty row",
                owner="spec.md#L2",
                expected=f"Duty row for page {page!r}",
                actual="missing",
                repair=f"Add the duty row for page {page!r} to the L2 table",
            ))

    if path_table is not None and len(path_table) >= 2:
        paths = {row[0] for row in path_table[1:] if row and row[0]}
        for number, item in enumerate(_l6_items(text), 1):
            refs = PATH_REF.findall(item)
            if not refs:
                errs.append(finding(
                    "G1.deep_l6_path_ref",
                    f"G1 spec: L6.{number} has no reachable path reference "
                    "(path: P<n>)",
                    owner=f"spec.md#L6.{number}",
                    expected=">=1 (path: P<n>) naming a path-table row",
                    actual="none",
                    repair="Reference the path that exercises this "
                           "criterion",
                ))
                continue
            for ref in refs:
                if ref not in paths:
                    errs.append(finding(
                        "G1.deep_l6_path_unknown",
                        f"G1 spec: L6.{number} references path {ref} not "
                        "in the L3 path table",
                        owner=f"spec.md#L6.{number}",
                        expected=f"path {ref} in L3 table",
                        actual="unknown path",
                        repair=f"Add path {ref} to L3 or fix the reference",
                    ))
    return errs


def check_spec(text: str) -> list[Finding]:
    errs: list[Finding] = []
    for layer in SPEC_LAYERS:
        # heading like "## L6 验收标准" or "## L6"
        if not re.search(rf"^#+\s*{layer}\b", text, re.M):
            errs.append(finding(
                "G1.missing_layer",
                f"G1 spec: missing {layer}",
                owner="spec.md",
                expected=f"heading for {layer}",
                actual="missing",
                repair=f"Add a top-level {layer} section to the spec",
            ))
    items = _l6_syntax(text)
    if not items:
        errs.append(finding(
            "G1.no_criteria",
            "G1 spec: L6 has no top-level acceptance criteria",
            owner="spec.md#L6",
            expected=">=1 top-level L6 criterion",
            actual="0",
            repair="Add Given/When/Then acceptance criteria under L6",
        ))
    for number, item in enumerate(items, 1):
        missing = item.missing
        if missing:
            errs.append(finding(
                "G1.missing_gwt",
                f"G1 spec: L6.{number} missing {', '.join(missing)}",
                owner=f"spec.md#L6.{number}",
                expected="Given, When, Then present",
                actual=f"missing {', '.join(missing)}",
                repair=f"Complete Given/When/Then for L6.{number}",
            ))
            continue
        if not item.ordered:
            errs.append(finding(
                "G1.gwt_order",
                f"G1 spec: L6.{number} must order Given -> When -> Then",
                owner=f"spec.md#L6.{number}",
                expected="Given -> When -> Then order",
                actual="out of order",
                repair=f"Reorder keywords for L6.{number}",
            ))
    if SPEC_SCHEMA_2.search(text):
        errs += _deepened_findings(text)
    return errs
