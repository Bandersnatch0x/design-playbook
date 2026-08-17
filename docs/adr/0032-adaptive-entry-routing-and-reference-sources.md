# ADR-0032: Adaptive entry routing and durable reference sources

## Status

Accepted (2026-08-17).

## Context

The orchestrator already owns P1/P2/P3 grading and `reference-intake` already accepts screenshots and generic design files, but read-only requests have only a prose fast path and temporary image attachments can disappear after the session. Adding a public workflow-simplifier skill or Figma/Lanhu conversion layer would create a second routing authority and vendor coupling.

## Decision

Deepen the existing run-profile module so normalized request facts produce either a `no-run` disposition or a Design I/O run with an initial P1/P2/P3 tier. `no-run` creates no run artifacts. Temporary raster images used by a design run are validated, copied, and hashed into the run-local reference tree; the manifest records provider-neutral source facts and `storage: copied|linked|remote|symbolic`. Existing baseline declarations/evidence provide read-only component candidates to `ui-picker`, recorded through the existing `components:` decision face.

This decision narrows ADR-0012's read-only exemption to `no-run` requests. A review, diagnosis, or plan that explicitly requests durable Design I/O artifacts enters `design-run`; for an existing product, it follows the router's baseline prerequisite like every other design run.

Figma MCP, Lanhu exports, and other design tools remain upstream providers. They may contribute observed reference facts but cannot write `spec.md`, the decision report, Fill code, or evaluator verdicts. No public skill, provider adapter, new gate, run-state authority, component repository, or automatic Git write is introduced.

## Consequences

Initial route grading, profile shape, and validation remain local to one module. Vision-capable hosts may inspect images directly on `no-run`; text-only hosts retain an explicit limitation. Reference media remains prohibited as a Fill source, and provider replacement does not change core contracts.
