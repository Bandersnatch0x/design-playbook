# ADR-0031: Architecture deepening for run facts, release transaction, and showcase state

## Status

Accepted (architecture review, 2026-08-16). Unreleased on
`fix/architecture-deepening`; does not alter stable `main` or v0.20.1.

## Context

The v0.20.1 review found three real seams and one correctness gap:

- run-profile validation existed but the production run gate did not consume it;
- run-status and validation independently loaded some vNext artifacts even after
  `RunFacts` became the shared snapshot for core artifacts;
- release identity and bounded npm verification were duplicated between two
  GitHub Actions workflows;
- queue-monitor dialog transitions mixed pure retry rules with DOM and timer
  effects, making race behavior browser-only to test.

## Decision

1. `RunFacts` remains a read-only snapshot and now includes parsed run-profile,
   decision-report, and shaping facts. Gate modules retain policy; run-status
   retains narration. It is not a second run-state SSOT.
2. `scripts/release_transaction.py` owns immutable tag/package/main identity and
   bounded registry/provenance verification. Local release code and GitHub
   Actions remain adapters. Stable-main, gate-then-merge, and atomic promotion
   remain unchanged.
3. `showcase/queue-monitor-state.js` owns pure dialog-session, execution-lock,
   scope-selection, and retry-transition rules. `queue-monitor.html` remains
   the DOM/timer adapter. The showcase is not migrated into a frontend package.
4. Unsupported run-profile versions fail at both the main run validation seam
   and the standalone G8 CLI entry point.
5. `scripts/package_inventory.py` owns normalized package inventory facts
   (`version`, skills, commands, MCP servers, and MCP entrypoints). Source,
   marketplace/plugin, and npm-unpacked surfaces remain adapters; install smoke
   owns orchestration and live process probes.

## Consequences

- One artifact snapshot gives gates and status shared facts, improving locality
  without moving policy into loading.
- Release state and verification tests exercise Python behavior directly; YAML
  tests assert adapter wiring rather than re-testing shell implementations.
- Queue-monitor transition tests run without a browser, while existing Chromium
  tests retain DOM/timer coverage.
- Package inventory comparison catches MCP entrypoint drift, not only server
  counts, while distribution-specific discovery remains local to each adapter.
- Release registry classification and provenance retry policy are deterministic
  under injected command, clock, temp-directory, and cleanup adapters.
- New release transaction behavior stays on a feature branch until the normal
  release gate promotes it; no public package or tag changes in this ADR.
