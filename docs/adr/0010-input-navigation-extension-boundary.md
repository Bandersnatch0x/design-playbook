# ADR-0010: Input/navigation signals enter only as 2D declaration/evidence extensions

## Status

Accepted (2026-07-20). Boundary decision; no implementation scheduled (candidates parked for v0.4+).

## Context

A fit analysis (2026-07-20) evaluated whether richer input/navigation signals — user attention proxies (attention/viewport/focus/scroll/hover traces) and structured navigation over run/declaration state — belong in this product. Both have plausible homologies with existing contracts:

- "what was attended" ↔ criterion-addressable evidence + the G6 bind-or-blocked rule;
- navigation over structure ↔ the run step graph that `scripts/run_status.py` already derives from artifacts.

design-playbook is a Design I/O plugin (declarations + contracts + recirculation) for product UI. The question is what shape (if any) such signals may take here.

## Decision

1. **Non-goal:** dedicated-hardware input surfaces and any input that needs a new runtime gate do not enter this repo (also recorded in `CONTEXT.md` Non-goals).
2. **Single translation rule:** an external input/navigation idea may land only as a **2D declaration/evidence extension** of existing contracts — either an evidence artifact bound to a declared L6 criterion (G6 semantics untouched; providers produce artifacts, never verdicts), or navigation over already-declared run structure. No new gates, no hardware assumptions.
3. **Vocabulary follows implementation:** glossary terms (attention-proxy, structured-navigation, …) are added to `CONTEXT.md` only when a shipped consumer exists — never parked speculatively.

## Future work (candidates, not scheduled)

- **P1 (v0.4+):** template-zone checks in evaluator/craft references. Elevating the run step graph into a navigation surface waits on `dedup-single-source` issue 03 (STAGES single-source ruling) — that ticket decides the graph's data source.
- **P2 (v0.4+):** attention/viewport interaction-trace evidence flavor in `mcp/evidence/`. Contract-compatible today (`interaction trace` is already a v1 artifact type; G5/G6 conditional gates unchanged), but requires a real dogfooded L6 criterion that consumes the trace first — otherwise it is telemetry ("evidence exists only to satisfy a declared criterion").

## Consequences

- Future "add a new input/navigation surface" proposals are evaluated against rule 2; anything needing dedicated hardware or a new gate is rejected by default.
- Implementations of P1/P2 target `packages/design-playbook/mcp/` (bundled per ADR-0009), not the sibling launchers.
