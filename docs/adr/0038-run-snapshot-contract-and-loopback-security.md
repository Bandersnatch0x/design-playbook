# ADR-0038: Run snapshots separate assertion availability and secure loopback actions

## Status

Accepted (2026-08-25).

## Context

ADR-0037 chooses an on-demand loopback Console and a source-hash-bound Run snapshot. Without a stable domain contract, the browser would either depend directly on internal artifact paths or turn component state into an accidental API. A single `status` field would also collapse distinct facts: a source can be stale while its last domain verdict was `Pass`, or a gate result can be unknown without being pending. Finally, loopback is reachable by other local pages and processes; binding to localhost is exposure reduction, not authentication.

## Decision

1. Run snapshots use a versioned domain JSON contract. UI components consume that contract but do not define it, and internal artifact layout is not part of the browser API.
2. Each important assertion separates its domain value or result from **Assertion availability**: `known`, `unknown`, `stale`, or `inconsistent`. Non-`known` states carry an explicit reason plus the source hashes and freshness facts available to support it.
3. An opaque, run-scoped **Source locator** points to an allowlisted authoritative artifact and optional semantic anchor. The server resolves it inside the selected run root. Browser requests cannot supply arbitrary paths, escape the run root, or receive absolute paths.
4. The Console binds only to loopback but treats every browser request as untrusted. Each session uses an unguessable token; the server validates the expected Origin; GET and HEAD are read-only; every action uses a protected non-GET request with a fixed typed schema.
5. The initial action allowlist is refresh, resolve/view an authority source, copy the next Agent command, request a Role attestation through the existing owner, and generate a Diagnostic export. No action executes a repair, reruns an Agent, edits arbitrary artifacts, or writes acceptance.
6. Errors surface explicitly. Invalid tokens, Origins, locators, versions, hashes, and action payloads fail closed; the Console never falls back to a broader path, an older snapshot, or mock success.
7. The top-level snapshot contract is organized as `identity`, `intent`, `execution`, `evaluation`, `nextActions`, `limitations`, and `sources`. It is not a mirror of filenames and is not shaped around current UI components.
8. Run snapshots are disposable and are never a permanent history. Console and snapshot schema versions ship together; the Console rejects an unknown snapshot version. Long-lived backward readers apply to Diagnostic exports, not every internal snapshot version.
9. Resolving a Source locator returns a server-rendered, read-only semantic excerpt and anchor. It never exposes the filesystem path, launches an editor, or grants browser-side editing.
10. A Role-attestation request binds a stable claim ID, the claim hash, requested role, and current authoritative source hash. Only explicit human submission reaches the existing authority owner. Any bound source change invalidates the request or prior attestation; roles cannot inherit one another's confirmation.

## Consequences

- The Run snapshot can evolve independently of UI layout and internal file organization.
- Discarding snapshots avoids a second event history; permanent compatibility work is concentrated on the explicitly shared Diagnostic export contract.
- Consumers must handle availability and domain result as orthogonal axes.
- Source navigation remains auditable without disclosing or accepting raw filesystem paths.
- Typed-action endpoints require security and containment tests even though the service is local and short-lived.
- Any new action expands the authority and threat surface and therefore requires an explicit allowlist change with an identified transaction owner.
