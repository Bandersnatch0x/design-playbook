# ADR-0037: The Console is an on-demand, single-run local projection

## Status

Accepted (2026-08-25).

## Context

ADR-0035 fixes the Run View as a rebuildable projection and typed facade, but does not choose its delivery lifecycle. A generated static page would preserve the read boundary but make refresh and later typed actions awkward. A persistent local daemon, project dashboard, or cloud Workspace would introduce discovery, authentication, retention, cross-run aggregation, and service ownership before the product has validated repeat use. Reading source files independently during a refresh could also present a mixed-time state as if it were current.

## Decision

1. The **Closed-loop Run Console** is an on-demand local Web application bound only to loopback and opened for one explicitly selected run. Closing the session ends its serving lifecycle; it is not a persistent daemon or remotely reachable service.
2. A recent-run locator may help the operator select or reopen a run, but the active Console has exactly one run context. It does not aggregate verdicts, rank runs, or become a project or organization dashboard.
3. Read parity lands before actions. Later actions use a narrow allowlist and route typed commands to the existing authority owner; the Console never edits arbitrary artifacts or owns a generic run mutation endpoint.
4. Each refresh builds one **Run snapshot** from authoritative sources and records the hashes used. Explicit refresh and a completed typed action trigger a full rebuild rather than incremental Console-owned state mutation.
5. Stale sources, partial writes, hash changes during construction, missing authorities, and unknown values are visible outcomes. The Console never silently substitutes the last successful value or labels a mixed-time snapshot current.
6. Normative claims carry a required approving role only where acceptance depends on that judgment. A missing Role attestation blocks the dependent result, not every run stage, and no universal three-role gate is introduced.

## Consequences

- The Console can support refresh and later safe actions without becoming a second run-state store.
- Single-run scope preserves the Closed-loop run boundary; cross-run learning continues through its existing derived aggregate rather than a dashboard.
- Loopback binding reduces exposure but is not treated as authentication. Any future remote access or long-lived service requires a separate security and lifecycle decision.
- Snapshot construction needs parity, source-change, partial-write, and unknown-state tests before the Console may claim current status.
