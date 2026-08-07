# ADR-0020: G7 validates contract drift, not user approval

## Status

Accepted (vNext grill Q5, 2026-08-08)

## Context

The proposed G7 gate protects a persistent contract from silent drift. If it treated the mere presence of an agent-written decision record as proof of user approval, it would recreate the self-approval loop the independent decision log was meant to avoid.

The existing Preview transaction provides the relevant boundary: a decision entry is audit and recovery authority, never confirmation authority. G7 needs the same distinction. It also cannot be implemented coherently before validator failures have stable IDs and the persistent contract and decision log exist.

## Decision

G7 is a structural contract-drift consistency gate.

- G7 is blocked by three prerequisites: stable machine-readable validator rule IDs, persistent contract v1, and the independent append-only `decisions.jsonl` from ADR-0017.
- Bind-first writes a run binding containing `schemaVersion`, persistent contract SHA, and decision log SHA.
- Final validation compares normalized contract-v1 fields against the bound version.
- Changed field paths require matching appended decision records, and the final evidence ledger binds the final decision log SHA.
- The validator checks that the decision log extends the bound log rather than rewriting history.
- Missing bindings, unsupported versions, non-append-only logs, unrecorded field changes, and SHA mismatches fail under stable `G7.*` rule IDs. Each failure includes owner, expected, actual, and a repair instruction.

Decision records are audit and recovery authority. They are not machine proof of the user's identity or consent. Explicit confirmation in the interaction remains the authority defined by ADR-0017; G7 only proves that the artifacts consistently record and bind the resulting decision.

## Consequences

- G7 cannot ship early as a hash-only approximation.
- The machine gate detects silent or partial mutation without making semantic product decisions.
- A structurally valid forged log remains outside G7's claim; this design does not advertise cryptographic approval.
- Ticket dependencies must place G7 after rule-ID output, contract v1, and decision-log implementation.
- Contract normalization and field-path identity become part of the versioned contract interface.

