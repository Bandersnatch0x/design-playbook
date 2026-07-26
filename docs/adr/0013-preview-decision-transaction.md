# ADR-0013: Durable Preview decision transaction

## Status

Accepted and implemented (2026-07-26).

## Context

Preview authority previously crossed browser submission handling, feedback-floor judgment, confirm writing, and append-only logging. A process failure could leave partial artifacts; a same-round retry could reopen human review or overwrite authority; concurrent calls could open competing windows.

ADR-0008 still defines feedback-floor and G5 confirmation semantics. ADR-0009 still defines bundled MCP layout. This decision changes transaction ownership and persistence, not those rulings.

## Decision

`mcp/preview/transaction.py` owns complete Preview decision transaction. Browser adapter owns only HTTP trust boundary and returns authenticated raw submission. MCP server validates tool arguments and maps typed transaction failures onto shared transport.

Each new outcome first atomically writes `preview/decision-round-<n>.json`. Entry contains generated `decision_id`, request binding, timestamp, and derived outcome. Binding covers round, normalized prototype hash, report reference, normalized summary, and ordered options.

Decision entry is audit and recovery authority. It is never confirmation authority. G5 continues accepting confirmation only from valid current `confirm-round-<n>.json` records under ADR-0008 report, floor, round, and prototype-integrity checks.

Confirm attempts atomically write existing confirm artifact after decision entry. All outcomes then rebuild `preview/log.md` as deterministic atomic projection of valid decision entries. Evaluator and status workflows continue consuming log plus confirm artifacts; they do not infer confirmation from decision entries.

Same-binding retries repair missing confirm/log projections without reopening browser. Different same-round bindings and legacy confirm collisions fail closed and require next round.

One active transaction per Preview directory and round holds atomic lock metadata. Heartbeat refreshes every 30 seconds; lock is stale after three missed heartbeats. Only matching binding may recover stale lock. Conflicts and incomplete projections return typed recoverable metadata through MCP; ordinary exceptions keep prior transport mapping.

Atomic replacement means same-directory temporary write, file flush/close, then `os.replace`. Parent-directory fsync and power-loss durability are outside v0 contract.

## Compatibility

Existing prototype, log, and legacy confirm signals retain G5 behavior. Valid decision entry additionally counts as Preview occurrence, so decision entry without valid current confirm fails closed. Legacy confirms remain readable and G5-valid when they satisfy existing rules, but new transactions never overwrite them.

## Consequences

- One deep module owns authority, commit order, repair, and result construction.
- Human decision is collected once per binding.
- Partial persistence is observable and repairable by `decision_id`.
- `log.md` remains readable and duplicate-free.
- Decision entries cannot become second approval path.
