"""G1 spec-shape gate (ADR-0023).

Owns the success-shape rule set for ``spec.md``: L1-L6 layers present and
every top-level L6 acceptance criterion is Given/When/Then in order. The
orchestrator (``validate_run.py``) also imports ``_l6_items`` here to size
the G2 ledger and G6 binding checks against the same spec read.
"""
from __future__ import annotations

import re

from design_playbook.scripts._diagnostics import Finding, finding

SPEC_LAYERS = ["L1", "L2", "L3", "L4", "L5", "L6"]


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
    items = _l6_items(text)
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
        positions = {
            keyword: re.search(rf"\b{keyword}\b", item, re.I)
            for keyword in ("Given", "When", "Then")
        }
        missing = [name for name, match in positions.items() if not match]
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
        if not (positions["Given"].start() < positions["When"].start() <
                positions["Then"].start()):
            errs.append(finding(
                "G1.gwt_order",
                f"G1 spec: L6.{number} must order Given -> When -> Then",
                owner=f"spec.md#L6.{number}",
                expected="Given -> When -> Then order",
                actual="out of order",
                repair=f"Reorder keywords for L6.{number}",
            ))
    return errs
