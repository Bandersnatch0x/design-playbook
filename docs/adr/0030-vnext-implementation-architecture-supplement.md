# ADR-0030: vNext implementation architecture supplement (S2-S6 unrecorded decisions)

## Status

Accepted (vNext S6, issue #41, 2026-08-14). Companion to ADR-0029
(final state) and ADR-0028 (severity alias removal): records the S2-S6
implementation decisions that had no ADR of their own because each
slice shipped inside one issue's boundary.

## Context

ADR-0023 established the closed-loop gate split (gate modules over one
orchestrator). S2-S6 extended that surface repeatedly — design-decision
entries, method semantics, registry coverage, repair rounds, tier
boundary, governance, learning candidates — and four structural choices
recurred without being written down: where new gate logic goes, how the
two G8 levels share a parser, what the gates consume as tier input, and
how pure-derived views stay write-free.

## Decision

1. **Gate-module modularity precedent extended.** Every new machine
   face lands as a sibling module under
   `packages/design-playbook/scripts/` (`dd_entries`,
   `g10_design_decisions`, `g8_run_registry`, `method_semantics`,
   `interaction_dimensions`, `repair_rounds`, `escalation_signals`,
   `g12_tier_boundary`, `run_profile`, `shaping_log`,
   `rules_governance`, `learning_candidates`) orchestrated by
   `validate_run.py`, which only wires paths, strict flags, and finding
   order (ADR-0023 rule). Pure parsing/derivation is importable and
   unit-tested without the orchestrator.
2. **One registry parser, two G8 levels.** `rules_registry.py` is the
   shared parser for the product-level self-check (`scripts/validate.py`)
   and the run-level coverage gate (`g8_run_registry.py`); the shipped
   package owns the module so both levels can never drift.
3. **Gates consume the effective tier.** `escalation_signals.
   effective_tier(declared, upgrades)` resolves the declared tier plus
   recorded run-profile upgrade events; G8 (full predicate evaluation),
   G10 (P1 rejects decision entries), and G11 (P3 matrix obligation)
   read the effective tier — after an escalation the run walks the new
   tier's obligations.
4. **Governance log layering.** `rules-governance.jsonl` records only
   user-decisive events (candidate opened / adjudicated / exemptions);
   agent-level run exemptions live in the craft audit rows and never
   enter the project-level log. G8's product-level check cross-references
   machine-enforced entries against governance adjudication records.
5. **Candidate queue is a pure derivation.** `learning_candidates`
   derives rule-promotion candidates from run history (repeat blockers
   + finding additional fields; distinct runs ≥3, contexts ≥2,
   unexplained false positives = 0) and only renders them — the
   run-review report gained an additive section; nothing writes back to
   the registry, decisions, or severities, and counting never mutates
   rules (the #24-Q6=B closed-loop deferral).
6. **Fixture strategy for full-chain verification.** Full-profile
   demonstrations are static synthesized artifact sets under
   `examples/` (P2 `export-entry`, P3 `export-upgrade`, S6 self-dogfood
   `dogfood/` over this repo's own showcase queue surface), consumed by
   `validate_run.py --strict` from unit tests — no chromium, no
   provider runtime; evidence hashes and transaction ids are real where
   the gates hash-check them (preview html digests).

## Consequences

- New gate proposals follow the same shape: sibling module + orchestrator
  wiring + unit suite + one fixture demonstration.
- The shared-parser rule means registry format changes release both G8
  levels atomically.
- The dogfood fixture doubles as the living example of every P3
  obligation in one place; keeping it green is part of the S6 exit
  criteria.
