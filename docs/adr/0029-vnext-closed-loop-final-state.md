# ADR-0029: vNext closed-loop final state — run profiles, G1-G12 spectrum, R1-R5 re-entry

## Status

Accepted (vNext S6, issue #41, 2026-08-14). Spec authority:
[`docs/specs/ui-ux-vnext/`](../specs/ui-ux-vnext/) (eight finalized
prototypes; `loop-prototype.md` owns the tier matrix and state machine,
`vnext-prototype.md` owns the slice plan S1-S6). This ADR records the
delivered final state so the architecture is discoverable from
`docs/adr/`; per-decision rationale and the full tables live in the spec
directory and are not restated here.

## Context

Slices S1-S6 (issues #34-#41) landed the vNext loop on top of the v0
pipeline: first-party rule registry with product- and run-level G8,
tiered run profiles, the shaping session, dual-track review with the
six-block report, design-decision entries, machine-counted repair
rounds, tier-boundary judgment, and the learning/governance protocol.
The v0 gate set (G1-G7, ADR-0023) had no single record of how the
extended spectrum fits together once all slices shipped.

## Decision

1. **One state machine, three depths.** P1 point-fix / P2 standard /
   P3 full differ only in *which steps run how deep, which gates fire,
   which artifacts are produced* — never in artifact formats or gate
   semantics. The tier axis is declaration touch (revised decided
   fields, new criteria, E-tier design decisions), machine-checked by
   G12 against the G7 bind-snapshot diff.
2. **Tier declaration lives in `plan.md` as the mandatory
   `run-profile` block** (tier + grading checklist + one user
   confirmation + skip list + upgrade events). Agent proposes, user
   confirms once; upgrades are automatic and recorded, downgrades need
   the user; over-compliance is kept. Gates consume the *effective*
   tier (declared plus recorded upgrades).
3. **Gate spectrum G1-G12 with a tier applicability matrix.** G1-G7
   keep their v0 semantics (deepened where the spec says so); G8 is
   two-level (product self-check + run-level registry coverage, one
   shared parser); G9-G12 are conditional gates (shaping exit,
   design-decision entries, coverage statement, tier boundary). P3 adds
   the full-profile obligations: full predicate evaluation (already
   P2+), the full G1-G12 spectrum, and the five-state × page sampling
   matrix **block mandatory** in the Coverage statement (S6 machine
   face, resolving the S3 leftover coupling).
4. **Re-entry is one mechanism.** Findings route by the two-hop map to
   R1-R5; the minimal invalidated set is expressed once
   (`point-back.md` `invalidated:` block); repair order follows the
   declaration-layer dependency order R1→R2→R3→R4 with R5 anytime; the
   two-cycle stop is machine-counted; escalation signals E1-E6 feed
   tier re-grading whose only exit is escalate-and-rewalk (never gate
   exemption).
5. **Exemptions never target gates.** Structural gates pass/fail/don't
   fire; only *rule hits* are exemptable (advisory: agent run-level
   with reason; machine-enforced: user only, logged in
   `rules-governance.jsonl`).
6. **Verdict domain stays `Pass | Recirculate`.** Escalated stops and
   suspension are run-status narration states derived from artifacts.
7. **Legacy runs are never re-checked.** New obligations bind only
   when a run declares a run-profile block (all vNext runs) or carries
   the vNext-shaped artifacts.

## Consequences

- The spec directory remains the single authority; this ADR is the
  entry point. Future tier-criteria changes go through the spec docs
  first, then the gate modules.
- A P3 declaration now fails validation without a complete sampling
  matrix block — fixture runs and dogfood demonstrate the obligation
  (`examples/export-upgrade/`, `examples/dogfood/`).
- The learning loop stays protocol-level: candidate queues are pure
  derived views; promotion and severity changes are user-only events.
