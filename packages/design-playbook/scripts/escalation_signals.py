"""E1-E6 upgrade-correction signals (vNext S4, loop-prototype 1.5).

Grading a run too low is corrected by escalation, never by exemption: when
a correction signal appears the agent must immediately escalate the tier
and complete the steps the old tier skipped (upgrades are the safe
direction; downgrades need the user). The signal table:

===== =============================== ============================== =========
Sig  Trigger (machine face)          Detected from                 Requires
===== =============================== ============================== =========
E1   an R1 finding appears (owner-   route: R1 lines                P2; P3 when
     less / unjudgeable / falsified                                  the touch
     assumed)                                                        revises
E2   a structural R2 finding (path   route: R2-structural lines    P2
     break / page duty / decision
     point beyond line patching)
E3   an R3 challenge or an E-tier    route: R3 / dd: lines /       P3
     design-decision hit             DD entries with tier explore
E4   a blocking finding spans        route sets covering >= 2      P2
     >= 2 owning layers              declaration layers
E5   G12 boundary violation (the     g12_tier_boundary contract    covering
     actual touch exceeds the        diff + declared face           tier
     declared tier's allowed face)
E6   user re-grade (any direction)   run-profile upgrades events   none
                                      (recorded fact, not derived)
===== =============================== ============================== =========

Route values are the second-hop repair targets (repair.md) with the S4
scope split: ``R1 | R2-line | R2-structural | R3 | R4 | R5``. Multi-layer
findings may carry several (the minimum owning set). Route annotations are
additional finding fields: findings without them are untouched and produce
no signals (protocol-side default).

This module owns parsing and signal derivation only; the accounting
(signal vs recorded upgrades) lives in ``g12_tier_boundary.check_g12``,
and ``run_status`` narrates the derived signals.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.dd_entries import is_positive_finding
from design_playbook.scripts.g2_g4_pointback import _findings
from design_playbook.scripts.repair_rounds import is_blocking

VALID_ROUTES = frozenset({
    "R1", "R2-line", "R2-structural", "R3", "R4", "R5",
})
# Declaration-layer number per route (R2 line/structural share layer 2);
# E4 counts distinct layers spanned by one blocking finding.
ROUTE_LAYERS = {
    "R1": 1, "R2-line": 2, "R2-structural": 2, "R3": 3, "R4": 4, "R5": 5,
}
TIER_RANK = {"P1": 1, "P2": 2, "P3": 3}
# Upgrade lines record "<ts> <signal?> <reason> -> <tier>" (trailing prose
# after the tier is legal); the arrow-tier pair and any E1-E6 token are the
# machine face (lenient parse: prose lines without an arrow tier are
# narration-only and never block accounting).
UPGRADE_TIER = re.compile(r"(?:->|→)\s*(P[123])(?!\d)")
UPGRADE_SIGNAL = re.compile(r"\b(E[1-6])\b")


def tier_rank(tier: str) -> int:
    """Ordinal of a tier (P1 < P2 < P3); unknown tiers rank 0."""
    return TIER_RANK.get(tier, 0)


def max_tier(*tiers: str) -> str:
    """The highest of the given tiers."""
    return max(tiers, key=tier_rank)


@dataclass(frozen=True)
class EscalationSignal:
    """One derived correction signal with the tier it requires."""

    signal: str          # E1..E6
    detail: str
    required_tier: str   # minimum covering tier
    source: str          # artifact the signal was derived from


def finding_routes(parsed: dict[str, list[str]]) -> frozenset[str]:
    """Route set of one parsed finding (empty when unannotated).

    Multi-layer findings carry the minimum owning set on one line
    (whitespace-separated); a second ``route:`` line is a shape error the
    route check reports.
    """
    routes: set[str] = set()
    for value in parsed.get("route", []):
        routes.update(value.split())
    return frozenset(routes)


def parse_routes(text: str) -> tuple[tuple[int, str, frozenset[str]], ...]:
    """(finding index, issue, routes) for every route-annotated finding."""
    out: list[tuple[int, str, frozenset[str]]] = []
    for index, parsed in enumerate(_findings(text), 1):
        routes = finding_routes(parsed)
        if not routes:
            continue
        issue = parsed["issue"][0] if parsed["issue"] else ""
        out.append((index, issue, routes))
    return tuple(out)


def route_hits(text: str) -> dict[str, int]:
    """Hit counts per route value across all findings (narration face)."""
    hits: dict[str, int] = {}
    for _index, _issue, routes in parse_routes(text):
        for route in sorted(routes):
            hits[route] = hits.get(route, 0) + 1
    return hits


def blocking_layer_spans(text: str) -> list[tuple[str, int]]:
    """Blocking findings spanning >= 2 distinct declaration layers."""
    spans: list[tuple[str, int]] = []
    for parsed in _findings(text):
        if not is_blocking(parsed):
            continue
        layers = {
            ROUTE_LAYERS[route] for route in finding_routes(parsed)
            if route in ROUTE_LAYERS
        }
        if len(layers) >= 2:
            issue = parsed["issue"][0] if parsed["issue"] else ""
            spans.append((issue, len(layers)))
    return spans


def check_routes(text: str) -> list[Finding]:
    """Validate route annotations (G12 rule ids; empty = pass/absent)."""
    errs: list[Finding] = []
    for index, parsed in enumerate(_findings(text), 1):
        values = parsed.get("route", [])
        if not values:
            continue
        if len(values) > 1:
            errs.append(finding(
                "G12.route_repeated",
                f"G12 tier: finding {index} repeats route:",
                owner=f"point-back.md#finding.{index}",
                expected="single route: line (multi-layer sets go on it)",
                actual=f"{len(values)} lines",
                repair=f"Keep one route: line on finding {index} listing "
                       "the minimum owning set",
            ))
        unknown = sorted(
            token for value in values for token in value.split()
            if token not in VALID_ROUTES
        )
        if unknown:
            errs.append(finding(
                "G12.route_invalid",
                f"G12 tier: finding {index} route {', '.join(unknown)!r} "
                "not in R1|R2-line|R2-structural|R3|R4|R5",
                owner=f"point-back.md#finding.{index}",
                expected="R1|R2-line|R2-structural|R3|R4|R5",
                actual=", ".join(unknown),
                repair="Annotate the second-hop repair target "
                       "(R2 scope split: line vs structural)",
            ))
    return errs


def dd_targets(text: str) -> tuple[str, ...]:
    """dd: references carried by findings (R3 challenge face).

    Issue #44: positive (S0) findings carry observation links, not
    challenges — their ``dd:`` values never fire E3 (G10 reports the
    misuse as a structural error instead).
    """
    targets: list[str] = []
    for parsed in _findings(text):
        if is_positive_finding(parsed):
            continue
        targets.extend(value.strip() for value in parsed.get("dd", [])
                       if value.strip())
    return tuple(targets)


def collect_signals(
        pointback_text: str, *,
        touch_revises: bool = False,
        dd_explore: bool = False) -> list[EscalationSignal]:
    """Derive E1-E4 signals from the point-back report.

    E5 (G12 boundary) is derived by ``g12_tier_boundary`` from the contract
    diff plus the declared face; E6 is the recorded user re-grade read
    from run-profile upgrades. Both are appended by the gate, not here.
    """
    signals: list[EscalationSignal] = []
    routes = parse_routes(pointback_text)
    all_values = {route for _i, _issue, rs in routes for route in rs}

    if "R1" in all_values:
        # E1: review surfaced an R1 finding — requirement work happened.
        # Revising existing decided fields through it is P3 territory.
        required = "P3" if touch_revises else "P2"
        signals.append(EscalationSignal(
            signal="E1",
            detail="R1 finding (ownerless / unjudgeable / falsified "
                   "assumed) — requirement face touched in review",
            required_tier=required,
            source="point-back.md#findings",
        ))
    if "R2-structural" in all_values:
        signals.append(EscalationSignal(
            signal="E2",
            detail="structural R2 finding (path break / page duty / "
                   "decision point beyond line patching)",
            required_tier="P2",
            source="point-back.md#findings",
        ))
    if "R3" in all_values or dd_targets(pointback_text) or dd_explore:
        detail = "R3 challenge or E-tier design-decision hit"
        if dd_explore:
            detail = "E-tier (explore) DD entry present" + (
                " plus R3 findings" if "R3" in all_values else "")
        signals.append(EscalationSignal(
            signal="E3",
            detail=detail,
            required_tier="P3",
            source="point-back.md#findings+decision-report.md",
        ))
    spans = blocking_layer_spans(pointback_text)
    if spans:
        signals.append(EscalationSignal(
            signal="E4",
            detail=f"blocking finding spans {spans[0][1]} owning layers "
                   f"({spans[0][0]!r})",
            required_tier="P2",
            source="point-back.md#findings",
        ))
    return signals


def upgrade_tiers(upgrades: tuple[str, ...]) -> list[tuple[str, str]]:
    """(tier, line) for every upgrade line carrying a trailing tier."""
    out: list[tuple[str, str]] = []
    for line in upgrades:
        match = UPGRADE_TIER.search(line.strip())
        if match:
            out.append((match.group(1), line.strip()))
    return out


def recorded_regrades(upgrades: tuple[str, ...]) -> list[EscalationSignal]:
    """E6 signals: user re-grades read from run-profile upgrade events.

    E6 is a recorded fact rather than a derived trigger, so the required
    tier is simply the tier the re-grade reached (any direction; a
    downgrade keeps over-compliance per loop-prototype 1.3).
    """
    return [
        EscalationSignal(
            signal="E6",
            detail=line,
            required_tier=reached,
            source="plan.md#run-profile.upgrades",
        )
        for reached, line in upgrade_tiers(upgrades)
    ]


def effective_tier(tier: str, upgrades: tuple[str, ...]) -> str:
    """The tier after recorded upgrades (last tier wins; else the declared)."""
    recorded = upgrade_tiers(upgrades)
    return recorded[-1][0] if recorded else tier
