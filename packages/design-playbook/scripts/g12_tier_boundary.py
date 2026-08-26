"""G12 tier-boundary gate (vNext S4, loop-prototype 1.2 / 1.5 / G12 row).

Machine judgment of "the actual declaration touch is a subset of the
declared tier's allowed face". The S1-S3 protocol consumption (agent
checks the 1.2 table at review; G7 backstops the contract face) becomes a
mechanical diff:

- **contract touch** — bind snapshot (``contract-bind.json``, the G7 diff
  basis) versus the current effective contract (``load_contract`` +
  ``apply_decisions``, the same comparison ability G7 uses; nothing is
  re-built). Categories: revised paths (any post-bind field change),
  added paths, added criteria (new ``l6.cN``), removed paths, ``l1.*``
  changes;
- **spec face** — no new L6 top-level items beyond the bound criteria
  (``len(spec L6 items) <= bound l6.c* count``); the within-section line
  diff of the P1 R2 line patch (L4 state rows / L5 five-state rows inside
  already-declared segments) stays protocol-side — no spec bind snapshot
  exists to diff against;
- **finding routes** — the declared tier's route face (P1: R4/R5 plus
  R2-line only);
- **decision face** — E-tier (explore) DD entries are P3 territory (E3);
- **blocking count** — P1 bounds blocking findings to one.

Tier faces (loop-prototype 1.2):

===== ============================ ========================= =========
Tier  Contract diff               Routes / decisions        Blocking
===== ============================ ========================= =========
P1    none (bind consistent)      R4, R5, R2-line; no DD    <= 1
P2    additions only (no          all routes; R/C DD only   any
      revision/removal of         (explore hits E3 -> P3)
      existing fields; l1.* is
      P3)
P3    anything (revises via       anything                  any
      supersedes, l1.* changes)
===== ============================ ========================= =========

The failure exit is **escalate and re-walk, not exemption** (loop-prototype
G12 row): a violation emits the E5 signal with the minimum covering tier,
and the machine then checks the run-profile upgrade events — a recorded
upgrade reaching the covering tier satisfies the gate (over-compliance is
kept, artifacts are never discarded), a missing one is a G12 error. The
E1-E6 signal derivation lives in ``escalation_signals``; this module owns
the diff, the face table, and the accounting.

Runs without a run-profile block (legacy) are not re-checked; the gate is
silent for them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.contract_v1 import (
    CONTRACT_FILENAME,
    DECISIONS_FILENAME,
    ContractError,
    apply_decisions,
    load_contract,
    load_decisions,
    normalize_contract,
    read_bind_snapshot,
)
from design_playbook.scripts.escalation_signals import (
    EscalationSignal,
    check_routes,
    collect_signals,
    effective_tier,
    max_tier,
    parse_routes,
    recorded_regrades,
    tier_rank,
)
from design_playbook.scripts.finding_syntax import parse_findings
from design_playbook.scripts.repair_rounds import is_blocking

CRITERION_PATH = re.compile(r"^l6\.c\d+$")


@dataclass(frozen=True)
class ContractTouch:
    """Post-bind declaration touch, computed from the bind-snapshot diff."""

    revised: tuple[str, ...] = ()        # paths changed after bind
    added: tuple[str, ...] = ()          # new paths
    added_criteria: tuple[str, ...] = ()  # new l6.cN criteria
    removed: tuple[str, ...] = ()        # dropped paths
    l1_changes: tuple[str, ...] = ()     # added/changed l1.* product fields

    @property
    def empty(self) -> bool:
        return not (self.revised or self.added or self.removed)

    def summary(self) -> str:
        parts: list[str] = []
        if self.revised:
            parts.append(f"revised {', '.join(self.revised)}")
        if self.added:
            parts.append(f"added {', '.join(self.added)}")
        if self.removed:
            parts.append(f"removed {', '.join(self.removed)}")
        return "; ".join(parts) if parts else "no contract touch"


def bind_fields(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    """Normalized bound fields from a bind-first snapshot; None if absent."""
    bound = snapshot.get("bound_contract")
    if not isinstance(bound, Mapping):
        return None
    try:
        return normalize_contract(bound)["fields"]
    except ContractError:
        return None


def load_bind_snapshot(run_dir: Path) -> dict[str, Any] | None:
    """Bind snapshot for the diff; None when it is not completely readable.

    The read, the torn-write classification, and the resolution invariant are
    owned by ``contract_v1`` (ADR-0039); G12 needs only "usable or not".
    """
    read = read_bind_snapshot(run_dir)
    return read.data if read.complete else None


def load_effective_contract(project_dir: Path) -> dict[str, Any] | None:
    """Current effective contract fields (decisions applied); None on error.

    Reuses the exact G7 comparison ability (load_contract -> load_decisions
    -> apply_decisions); G7 owns the drift diagnostics, G12 only the diff.
    """
    try:
        contract = load_contract(project_dir / CONTRACT_FILENAME)
        decisions = load_decisions(project_dir / DECISIONS_FILENAME)
        effective = (
            apply_decisions(contract, decisions) if decisions else contract
        )
    except (ContractError, OSError, UnicodeError):
        return None
    return effective["fields"]


def contract_touch(
        bound: Mapping[str, Any],
        current: Mapping[str, Any]) -> ContractTouch:
    """Diff the bound fields against the current effective fields."""
    revised: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    for path in sorted(set(bound) | set(current)):
        if path not in bound:
            added.append(path)
        elif path not in current:
            removed.append(path)
        elif bound[path] != current[path]:
            revised.append(path)
    return ContractTouch(
        revised=tuple(revised),
        added=tuple(added),
        added_criteria=tuple(p for p in added if CRITERION_PATH.match(p)),
        removed=tuple(removed),
        l1_changes=tuple(
            p for p in added + revised if p.startswith("l1.")),
    )


def blocking_count(pointback_text: str) -> int:
    """Number of blocking findings in the report."""
    return sum(1 for parsed in parse_findings(pointback_text)
               if is_blocking(parsed))


def covering_tier(
        *, touch: ContractTouch | None = None,
        routes: frozenset[str] = frozenset(),
        dd_explore: bool = False,
        blocking: int = 0,
        spec_l6_count: int = 0,
        bound_criteria: int | None = None,
        touch_revises: bool = False) -> str:
    """The minimum tier whose face covers every observed fact.

    This is the upgrade suggestion E5 carries (loop-prototype 1.5:
    "escalate to the lowest tier covering the actual touch").
    """
    tier = "P1"
    if touch is not None and not touch.empty:
        if touch.added:
            tier = max_tier(tier, "P2")
        if touch.revised or touch.removed or touch.l1_changes:
            tier = max_tier(tier, "P3")
    if touch_revises:
        tier = max_tier(tier, "P3")
    if routes - {"R4", "R5", "R2-line"}:
        tier = max_tier(tier, "P2")   # R1 / structural R2 beyond the P1 face
    if "R3" in routes:
        tier = max_tier(tier, "P3")
    if dd_explore:
        tier = max_tier(tier, "P3")
    if blocking > 1:
        tier = max_tier(tier, "P2")   # P1 bounds blocking findings to one
    if bound_criteria is not None and spec_l6_count > bound_criteria:
        tier = max_tier(tier, "P2")   # new L6 top-level items
    return tier


def _face_violations(
        declared: str, *,
        touch: ContractTouch | None,
        routes: frozenset[str],
        dd_explore: bool,
        blocking: int,
        spec_l6_count: int,
        bound_criteria: int | None) -> list[str]:
    """Facts outside the declared tier's allowed face (P3 face allows all)."""
    violations: list[str] = []
    if declared == "P3":
        return violations
    if declared == "P1":
        if touch is not None and not touch.empty:
            violations.append(
                f"contract touch beyond the P1 face ({touch.summary()})")
        beyond = sorted(routes - {"R4", "R5", "R2-line"})
        if beyond:
            violations.append(
                f"routes {', '.join(beyond)} outside the P1 route face "
                "(R4/R5 plus R2 line patches)")
        if dd_explore:
            violations.append("E-tier (explore) DD entry under P1")
        if blocking > 1:
            violations.append(
                f"{blocking} blocking findings (P1 bounds blocking to one)")
        if bound_criteria is not None and spec_l6_count > bound_criteria:
            violations.append(
                f"{spec_l6_count} spec L6 items over {bound_criteria} "
                "bound criteria (no new L6 top-level items under P1)")
        return violations
    # P2: additions only; revisions/removals and l1.* are P3 territory.
    if touch is not None:
        if touch.revised or touch.removed:
            violations.append(
                f"revision/removal of bound fields ({touch.summary()}) "
                "beyond the P2 additions-only face")
        if touch.l1_changes:
            violations.append(
                f"l1.* product-level changes ({', '.join(touch.l1_changes)}) "
                "are P3 territory")
    if dd_explore:
        violations.append("E-tier (explore) DD entry under P2 (E3 -> P3)")
    return violations


def check_g12(
        profile, *,
        pointback_text: str,
        touch: ContractTouch | None = None,
        bound_criteria: int | None = None,
        spec_l6_count: int = 0,
        dd_explore: bool = False) -> tuple[list[Finding], list[Finding],
                                           list[EscalationSignal]]:
    """Return ``(errors, warnings, signals)`` for a run with a run-profile.

    ``profile`` is the parsed run-profile block (tier + upgrades). Errors:
    route annotation shape, and escalation signals whose required tier
    exceeds the effective tier without a recorded upgrade (the exit is
    escalate-and-rewalk, so the repair is recording the upgrade event and
    completing the added steps). Warnings narrate recorded escalations.
    """
    errs: list[Finding] = []
    warns: list[Finding] = []
    errs += check_routes(pointback_text)

    declared = profile.tier
    routes = frozenset(
        {route for _i, _issue, rs in parse_routes(pointback_text)
         for route in rs})
    blocking = blocking_count(pointback_text)
    reached = effective_tier(declared, profile.upgrades)

    # E1-E4 from the report; E5 from the declared-face violations; E6 from
    # the recorded upgrade events (user re-grade is a recorded fact).
    signals = collect_signals(
        pointback_text,
        touch_revises=bool(touch is not None and touch.revised),
        dd_explore=dd_explore,
    )
    violations = _face_violations(
        declared, touch=touch, routes=routes, dd_explore=dd_explore,
        blocking=blocking, spec_l6_count=spec_l6_count,
        bound_criteria=bound_criteria)
    if violations:
        covering = covering_tier(
            touch=touch, routes=routes, dd_explore=dd_explore,
            blocking=blocking, spec_l6_count=spec_l6_count,
            bound_criteria=bound_criteria,
            touch_revises=bool(touch is not None and touch.revised))
        signals.append(EscalationSignal(
            signal="E5",
            detail="; ".join(violations),
            required_tier=covering,
            source="plan.md#run-profile",
        ))
    if regrades := recorded_regrades(profile.upgrades):
        signals.extend(regrades)

    # Escalation accounting: every signal demanding a tier above the
    # effective tier must be covered by a recorded upgrade event; covered
    # escalations narrate as warnings (over-compliance is kept).
    outstanding = [
        signal for signal in signals
        if tier_rank(signal.required_tier) > tier_rank(reached)
    ]
    covered = [
        signal for signal in signals
        if tier_rank(signal.required_tier) > tier_rank(declared)
        and tier_rank(signal.required_tier) <= tier_rank(reached)
    ]
    if outstanding:
        demand = max_tier(*{s.required_tier for s in outstanding})
        listed = "; ".join(
            f"{s.signal} ({s.required_tier})" for s in outstanding)
        errs.append(finding(
            "G12.escalation_outstanding",
            f"G12 tier: escalation signals exceed the effective tier "
            f"{reached} — {listed}; escalate to {demand} and record the "
            "upgrade (the exit is escalate-and-rewalk, not exemption)",
            owner="plan.md#run-profile",
            expected=f"upgrades reaching {demand} (tier + reason line)",
            actual=f"effective tier {reached}",
            repair="Record the upgrade event in the run-profile upgrades "
                   "list and complete the steps the new tier adds "
                   "(produced artifacts are kept)",
        ))
    for signal in covered:
        warns.append(finding(
            "G12.escalation_recorded",
            f"G12 tier: escalation {signal.signal} -> "
            f"{signal.required_tier} recorded ({signal.detail[:140]})",
            owner="plan.md#run-profile",
            expected="upgrade event + added steps completed",
            actual="recorded",
            repair="None — over-compliance is kept; artifacts stay",
            severity="warning",
        ))
    return errs, warns, signals
