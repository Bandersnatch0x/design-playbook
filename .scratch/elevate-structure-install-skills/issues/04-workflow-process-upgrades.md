# 04 - Workflow process upgrades

**Type:** grilling  
**Status:** resolved  
**Blocked by:** 03 (resolved)

## Question

Given dogfood gaps and code-review findings, which **process upgrades** are in elevate (priority-ordered), and which wait?

Output: ordered backlog of **decisions about what to change**, not the skill diffs themselves.

## Answer

**Decision: default accepted. Ordered "what to change" backlog (decisions, not diffs).**

### This increment (P0-P2)

- **P0 - Recirculate closure becomes a dogfood gate.** dogfood 002 listed blocking findings without a recirculate -> fix -> re-eval -> zero-blocking trail. Add a sixth gate: *blocking findings have a recirculate trail*. Done when: the dogfood log shows `recirculate -> fix -> re-eval -> 0 blocking` (or each blocking item is explicitly accepted). Justification: Q2 success #4 (recirculate) is a core sell, cannot stay soft.
- **P1 - Recirculate table single source of truth.** Code review flagged the recirculate map duplicated in `design-playbook/SKILL.md` and `ui-evaluator/SKILL.md` (Divergent Change). Decision: **SSOT = `ui-evaluator`** (the acceptance side owns the recirculate table); the `design-playbook` orchestrator keeps a one-line pointer, not a copy. Justification: kills dual-write drift, one edit point.
- **P2 - Description trigger-branch trim (writing-great-skills pass).** Six descriptions already carry triggers; do a light pass: each keeps "leading word + 1 trigger/branch + reach clause"; drop synonym branches (duplication per 08). Bodies untouched (anti-sprawl). Justification: lower context load, sharper triggering.

### Deferred (Not-yet-specified)

- Third dogfood scene (data-dense table/chart) as a release gate - next increment's craft stress, not a v0 blocker.
- Skill regression automation - depends on remote/CI (06 "not yet").
- Demote `craft-guard`/`ui-evaluator` to user-only - load acceptable at six; trigger condition not met.
- Maintainer-loop bridge docs - not needed; 05 already isolates `product-*` to root and root `CLAUDE.md` points at workflow.

### Out of scope

- Rewriting skill body structure (sprawl risk; P2 touches descriptions only).
- New skills/commands (03 locked the surface).

Unblocks: nothing - this is the last ticket. Map clears; hand off to `/to-spec`.
