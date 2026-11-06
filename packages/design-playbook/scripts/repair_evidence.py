"""Paired repair evidence (T-152 / research seam I8).

A repaired blocker used to close on a sentence: the closure trail said
"fix -> re-eval -> 0 blocking" and nothing required the pair of bound
artifacts behind it. This module machines the countable face of that pair
so "repaired" is evidence rather than narration.

The pair lives on the closure trail, one annotation per closure:

```text
- closes: <id or issue> -> fix -> re-eval -> 0 blocking
  repair-evidence: before=evidence/L6.3-empty-r1.png after=evidence/L6.3-empty-r2.png
```

Both halves resolve through the evidence manifest (the binding mechanism
that already exists, ``evidence/manifest.jsonl``): the two bound entries
must name the same ``criterion`` (the node) and the same
``request.viewport`` snapshot (the viewport), and they must carry different
``sha256`` bytes. A missing half, an unbound artifact, a criterion or
viewport mismatch, and byte-identical halves all fail closed.

The verdict value domain is untouched (``Pass | Recirculate``, #32-Q4=A).
An unpaired closure is required proof that is ``blocked``, so the run is
not Pass and stays in recirculate — the existing ``blocked`` -> Recirculate
semantics, implemented once, not a second verdict rule.

Repeat-state detection is two faces, neither new: byte-identical halves are
``G4.repair_evidence_unchanged`` here (the repaired surface is the failure
surface), and a repeated blocker is the existing ``rounds:`` counter with
``G4.round_stop_missing`` escalating the two-cycle stop in
``repair_rounds.py``.

Machine policy is additive: a report with no ``repair-evidence:`` line does
not trigger the gate, so legacy reports keep passing.
"""
from __future__ import annotations

import re

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.g6_records import latest_by_instant

# `- repair-evidence: before=... after=...` on the closure trail. The leading
# bullet is optional so the annotation reads the same whether it sits inside
# the closure list or a fenced block.
_REPAIR_EVIDENCE_LINE = re.compile(
    r"^[ \t]*(?:[-*][ \t]+)?repair-evidence:[ \t]*(.*)$", re.I | re.M)
_HALF = re.compile(r"\b(before|after)[ \t]*=[ \t]*(\S+)")


def parse_repair_evidence(text: str) -> list[dict[str, str]]:
    """Each ``repair-evidence:`` annotation as its declared halves.

    Keys are the halves that were written (``before`` / ``after``); a half
    that is missing from a line is absent, never defaulted.
    """
    pairs: list[dict[str, str]] = []
    for body in _REPAIR_EVIDENCE_LINE.findall(text):
        halves = {name.casefold(): value for name, value in _HALF.findall(body)}
        pairs.append(halves)
    return pairs


def _viewport(entry: dict) -> object:
    request = entry.get("request")
    if not isinstance(request, dict):
        return None
    return request.get("viewport")


def _bound_entry(entries: list[dict], artifact: str) -> dict | None:
    """The manifest entry binding ``artifact``, or None when unusable.

    None covers both no binding and a binding whose ``ts`` cannot order it
    (``latest_by_instant`` fails closed there): either way the half has no
    usable binding, so the repair proof stays blocked.
    """
    matching = [entry for entry in entries if entry.get("artifact") == artifact]
    if not matching:
        return None
    return latest_by_instant(matching)


def _unpaired(pair: dict[str, str]) -> list[str]:
    return [half for half in ("before", "after") if not pair.get(half)]


def check_repair_evidence(
        text: str, entries: list[dict]) -> list[Finding]:
    """Return G4 repair-evidence findings (empty = pass or gate not triggered).

    ``entries`` are the run's manifest entries; among entries binding one
    artifact the latest by capture instant wins, mirroring G6.
    """
    errs: list[Finding] = []
    for pair in parse_repair_evidence(text):
        declared = " ".join(f"{k}={v}" for k, v in sorted(pair.items()))
        missing = _unpaired(pair)
        if missing:
            errs.append(finding(
                "G4.repair_evidence_unpaired",
                f"G4 repair-evidence: closure declares "
                f"{'/'.join(missing)} without the other half — a repair "
                "proof is a pair (failure state + repaired state)",
                owner="point-back.md#closure",
                expected="before=<artifact> after=<artifact>",
                actual=declared or "neither half",
                repair="Bind both halves under one criterion and viewport; "
                       "the unpaired closure is blocked, not passed",
            ))
            continue

        before = _bound_entry(entries, pair["before"])
        after = _bound_entry(entries, pair["after"])
        unbound = [
            pair[half] for half, entry in
            (("before", before), ("after", after)) if entry is None
        ]
        if unbound:
            errs.append(finding(
                "G4.repair_evidence_unbound",
                "G4 repair-evidence: no usable manifest binding for "
                f"{', '.join(unbound)}",
                owner="evidence/manifest.jsonl",
                expected="both halves bound to the run's evidence manifest",
                actual="unbound: " + ", ".join(unbound),
                repair="Capture the missing half and bind it, or drop the "
                       "closure — an unbound half is blocked",
            ))
            continue

        if (before.get("criterion") != after.get("criterion")
                or _viewport(before) != _viewport(after)):
            errs.append(finding(
                "G4.repair_evidence_mismatch",
                "G4 repair-evidence: the two halves do not point back to one "
                "node and viewport "
                f"(before criterion={before.get('criterion')!r} "
                f"viewport={_viewport(before)!r}; "
                f"after criterion={after.get('criterion')!r} "
                f"viewport={_viewport(after)!r})",
                owner="point-back.md#closure",
                expected="same criterion and same request.viewport on both "
                         "halves",
                actual="mismatched criterion or viewport",
                repair="Recapture the repaired half at the failing node and "
                       "viewport, or close against the right criterion",
            ))
            continue

        if before.get("sha256") == after.get("sha256"):
            errs.append(finding(
                "G4.repair_evidence_unchanged",
                "G4 repair-evidence: the two halves are byte-identical "
                f"({after.get('artifact')}), so the repaired surface is the "
                "failing surface",
                owner="point-back.md#closure",
                expected="a repaired half that differs from the failing half",
                actual="identical sha256",
                repair="Recapture after the fix; an unchanged surface means "
                       "the deviation still stands",
            ))
    return errs
