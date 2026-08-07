# ADR-0017: Persistent contract decisions require explicit user authority

## Status

Accepted (vNext grill Q2, 2026-08-08)

## Context

vNext promotes accepted run specifications into reusable project contracts. Reuse creates leverage only if unresolved assumptions do not silently become defaults. Keeping user decisions inside an agent-rewritable `spec.md` would also let the contract author approve its own work and make a later drift gate circular.

## Decision

Persistent contract fields carry an explicit resolution state: `decided`, `assumed`, or `open`.

- Only explicit user confirmation can create `decided`. An agent may propose a value, mark it `assumed` or `open`, and detect staleness, but cannot promote its own proposal.
- Bind-first review resurfaces every `assumed` and `open` field whenever a contract is reused.
- `open` blocks dependent work. `assumed` may be used only after the user explicitly acknowledges that assumption for the current run.
- Accepting an entire spec persists it but does not promote its assumptions or open questions.
- Relevant provenance-source hash changes or schema changes mark affected fields for review. We do not use an arbitrary calendar TTL.
- Confirmed decisions append to a `decisions.jsonl` stored independently from `spec.md`. Each record has a stable ID, field path, decision, rationale, confirmation time, and optional superseded decision ID.
- The run ledger records the decision log SHA used by that run.

The agent may append the mechanical record only after the confirmation appears in the conversation. This is an authority boundary and audit trail, not a cryptographic anti-tamper mechanism.

## Consequences

- Whole-document approval cannot hide unresolved defaults.
- A batch confirmation is valid only when it names the decision IDs being approved.
- Reused assumptions create a visible confirmation pause rather than silently accumulating as project truth.
- Source or schema drift preserves the historical decision but prevents unreviewed reuse of the affected field.
- Future G7 drift checks must consume the independently bound decision log rather than approval text inside `spec.md`.

