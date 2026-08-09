# ADR-0018: Capture contract v1 lands atomically

## Status

Accepted (vNext grill Q3, 2026-08-08)

## Context

The evidence provider currently accepts an unversioned flat request and owns hard-coded browser defaults. vNext needs explicit viewport inputs and deterministic capture freeze while also establishing contract version discipline. Landing any one surface first would let the spec, provider, and manifest describe different executions.

Evidence manifests are run-local execution records, not durable project contracts. Supporting old unversioned records through a second reader would create permanent ambiguity for little migration value.

## Decision

Ship capture contract v1 as one merge and release boundary.

- Every request carries `schemaVersion: 1`.
- Viewport is explicit: width, height, device-pixel ratio, and color scheme.
- `observe*` enables freeze by default: disable animations and transitions, wait for fonts, and optionally wait for network idle.
- The spec template, orchestrator derivation, `execute_capture_plan` tool schema and runtime, embedded manifest request snapshot, validator, fixtures, documentation, and tests change together.
- Missing or unknown schema versions fail closed with a recapture instruction.
- Existing unversioned run-local evidence is recaptured. There is no dual-read compatibility path or feature flag.
- Implementation may use incremental red-green commits, but a partial contract must not merge or ship.

The provider boundary remains unchanged in one important respect: it receives no criterion ID, writes no manifest, and makes no acceptance judgment.

## Consequences

- A manifest records enough viewport and freeze data to reproduce a capture without relying on provider defaults.
- The first versioned contract has no interval where fields exist without version semantics.
- Fixtures for old unversioned evidence must be upgraded or explicitly retained only as rejection cases.
- Users resuming a pre-vNext run must recapture its evidence.
- Later schema changes require a new supported version rather than in-place reinterpretation.

## Enforcement sites (landed with the deepening, 2026-08-08)

1. `mcp/evidence/capture_contract.py` owns the v1 rules: `parse_capture_contract` (write authority, normalized request + fail-closed ValueError), `validate_capture_snapshot` (read authority, host-neutral full-shape facts), and the contract-fields JSON Schema fragment composed into the provider tool schema. The module is named to avoid collision with `scripts/contract_v1.py` (persistent contract, ADR-0017).
2. Provider (`mcp/evidence/server.py`) retains Runtime Object fields, path/overwrite boundaries, and Playwright I/O only; it imports the contract module for schema/parse.
3. G6 (`scripts/validate_run.py`) validates bound manifest request snapshots through `validate_capture_snapshot` — schemaVersion=1, full viewport shape, freeze — replacing the previous partial hand-written checks (schemaVersion + viewport-dict only).
4. The orchestrator derives and embeds the provider-echoed request snapshot unchanged, so real snapshots always carry freeze defaults; hand-written minimal fixtures were upgraded to full shape.

