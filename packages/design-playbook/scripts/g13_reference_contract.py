"""G13 reference-contract gate (T-153 / research I4, ADR-0011).

Conditional: fires only when the run carries ``reference/contract.md``
(ADR-0011 artifact layout). The contract was declared in the stage table
(``stages.py``) and consumed by ux-spec / ui-picker / ui-evaluator prose, but
no gate read its shape — a contract that declared none of its axes passed
every seam. This module owns that one judgment.

Required axes come from the template SSOT
(``skills/reference-intake/references/contract-template.md``: "Headings are
required", "Do not invent alternate headings") plus the two constraint
markers the fixture shape check already demands
(``tests/test_reference_intake_fixtures.py``). Axis *declaration* is what is
checked: section bodies are multi-line by design and may be deliberately
blank-and-noted (template no-vision rule), so an empty bullet is not a
finding.

Presence policy (ADR-0011 §5: missing reference artifacts never fail a run):
a run with no contract is not checked; a contract that exists but declares
none of the axes fails. The two are different results, never one red.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.scripts._diagnostics import Finding, finding  # noqa: E402

# Template SSOT headings, in template order.
REQUIRED_HEADINGS: tuple[str, ...] = (
    "Source summary",
    "Evidence (observed)",
    "Inferred (labeled)",
    "Keep",
    "Change",
    "Do not copy",
    "Functional constraints for ux-spec",
    "Visual cues for ui-picker",
    "License / brand risks",
    "Unresolved questions",
)

# Bullet prompts the same template marks required, restricted to the two the
# existing fixture shape check already enforces.
REQUIRED_MARKERS: tuple[str, ...] = (
    "always / ask / never hints:",
    "Captured at",
)


def _missing_axes(text: str) -> list[str]:
    """Declared-axis names absent from the contract (template order)."""
    missing: list[str] = []
    for heading in REQUIRED_HEADINGS:
        pattern = re.compile(
            r"(?m)^#{1,6}[ \t]*" + re.escape(heading) + r"[ \t]*$"
        )
        if not pattern.search(text):
            missing.append(heading)
    for marker in REQUIRED_MARKERS:
        if marker not in text:
            missing.append(marker)
    return missing


def check_g13(text: str) -> list[Finding]:
    """Return G13 findings for a reference contract.

    Presence is the caller's call: this judges the text it is handed, so an
    empty contract (an existing but blank file) declares no axis and fails.
    """
    missing = _missing_axes(text)
    if not missing:
        return []
    return [finding(
        "G13.contract_axes",
        "G13 reference: reference/contract.md is missing required "
        f"axis/axes: {', '.join(missing)}",
        owner="reference/contract.md",
        expected="every contract-template heading plus the always/ask/never "
                 "and Captured-at markers",
        actual=", ".join(missing),
        repair="Emit the missing headings and bullets from "
               "skills/reference-intake/references/contract-template.md "
               "(reference-intake Done-when: every template heading is "
               "required; do not invent alternate headings)",
    )]


def contract_unreadable_finding() -> Finding:
    """The present-but-unreadable outcome (distinct from absent)."""
    return finding(
        "G13.contract_unreadable",
        "G13 reference: reference/contract.md exists but could not be read "
        "as UTF-8 text",
        owner="reference/contract.md",
        expected="UTF-8 markdown contract",
        actual="unreadable",
        repair="Re-emit reference/contract.md as UTF-8 markdown, or remove "
               "the stray file",
    )
