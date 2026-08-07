# ADR-0019: Defer layered contract inheritance

## Status

Accepted (vNext grill Q4, 2026-08-08)

## Context

Persistent specification contracts do not exist in the product yet, so the repository has no real reuse history showing stable project, page, or component override boundaries. Introducing inheritance now would require precedence, merge, conflict, invalidation, and provenance rules before the base contract has been exercised. It would also create a second granularity mechanism alongside the L6 user-risk budget.

## Decision

Persistent contract v1 has one scope: the project.

- Bind-first imports the project contract as a whole into the current run.
- A run-specific difference is an explicit decision. It either stays local to that run or updates the project contract after user confirmation.
- v1 has no project/page/component hierarchy, deep merge, precedence rules, partial overrides, inheritance placeholders, or compatibility hooks.
- Reopen inheritance design only when at least two independent product scopes repeatedly override the same field and demonstrably need to evolve separately.
- When that trigger occurs, use a new grill and ADR to choose the scope axis and conflict rules from evidence.

## Consequences

- Contract reuse and governance can be tested without a speculative merge engine.
- Every v1 field has one visible project-level authority.
- Run-local exceptions remain explicit and auditable rather than becoming hidden precedence.
- Future inheritance may require a new schema version; v1 does not reserve empty fields for it.

