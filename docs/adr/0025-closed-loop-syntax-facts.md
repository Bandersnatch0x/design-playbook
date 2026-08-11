# ADR-0025: Closed-loop syntax facts are parsed once

## Status

Accepted (architecture second confirmation, 2026-08-11). Supersedes ADR-0023
only for Evidence ledger and Verdict parsing ownership.

## Context

ADR-0023 placed the G2 Evidence ledger parser and G3 Verdict parser with gate
policy, while G6 and run status retained separate projections of the same
point-back text. The projections have different fidelity: G2 retains repeated
field values, G6 derives a leading artifact token, and run status accepts
Verdict text that the G3 gate rejects. A normalized shared dictionary would
remove duplication by discarding facts that existing consumers rely on.

## Decision

Use two separate deep modules for closed-loop syntax facts: one for the
Evidence ledger and one for Verdict. Both accept point-back text and return
structured syntax facts without applying gate or status policy.

The Evidence ledger result preserves row order, field occurrence order,
duplicate values, raw observed text, and the derived leading artifact token.
G2 and G6 project their existing policy from that result and retain their
current rule IDs, messages, finding order, and accepted artifact syntax.

The Verdict result records heading and value cardinality and exposes a
canonical value only when exactly one valid Verdict exists. G3 retains its
diagnostic mapping. Run status may report `Run complete (Pass)` only from one
uniquely valid `Pass`; missing, malformed, ambiguous, or repeated Verdict text
does not complete a run.

Ledger and Verdict stay separate modules rather than becoming a broad
point-back parser. Existing parsing paths are removed after their consumers
migrate; no compatibility parser is layered beside them.

## Considered options

- Keep the duplicate parsers: rejected because syntax fixes can continue to
  diverge across gates and status.
- Normalize immediately to one consumer's dictionary or pair shape: rejected
  because it loses multiplicity, ordering, raw text, or derived-token facts.
- Build one parser for every point-back section: rejected as a shallow module
  with unrelated consumers and policy pressure.

## Consequences

Syntax knowledge becomes local and testable through two small interfaces.
Gate policy remains explicit at each enforcement site, while the sanctioned
status correction prevents invalid Verdict text from reporting completion.
