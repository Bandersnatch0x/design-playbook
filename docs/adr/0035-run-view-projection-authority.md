# ADR-0035: Run View is a projection, not a new authority

## Status

Accepted (2026-08-25).

## Context

The roadmap proposed a writable `DesignRun` object containing status, decisions, and issues, followed by a Workspace artifact that also carried decision, Evidence, and `accepted` status. The existing product deliberately separates those authorities: the persistent Contract and Decision log own durable decisions, the Preview transaction owns confirmation, the Manifest binds artifacts to Criteria, the Evaluator owns the source verdict, and run status is rebuilt from durable artifacts. ADR-0034 already demonstrated that a convenient projection can silently become a competing confirmation authority.

## Decision

The next visible run surface is a **Run View**: a deterministic, source-linked projection and typed application facade over one Closed-loop run.

1. The view exposes stable domain assertions such as intent, source verdict, blocker ownership, next action, criterion coverage, limitations, freshness, and unknown reasons. It exposes opaque source locators rather than making raw file topology or gate internals a public API.
2. Every assertion is rebuildable from its existing authority. The view cannot copy a decision, Evidence binding, confirmation, finding, or verdict into independent writable state, and it cannot infer a stronger claim than its source supports.
3. A view action is typed and routed to the transaction owner for that assertion. There is no generic `DesignRun` writer and no `append_reasoning` contract; only necessary auditable rationale or decision facts may enter their existing authority.
4. The next 90 days do not migrate any authority. Canvas, general Design Memory, Multi-Agent coordination, and Workspace-owned acceptance remain non-goals until the closed-loop value and repeat use are externally demonstrated.
5. A future minimal run coordinator may be proposed only for real coordination facts such as command identity, expected-version transitions, leases, cancellation, or transition ordering. It requires an approved second command writer or reproducible concurrency failures, replay parity, a field-by-field old/new owner map, one writer per schema epoch, explicit cutover and rollback, and no permanent dual write. Contract, Preview, Manifest, Finding, and Verdict semantics remain outside that coordinator.

## Consequences

- A compact local Run Console is product work, not a new domain authority.
- UI demand or inconvenient file access justifies an index or projection, not an authority migration.
- The public view contract must remain stable while internal artifact paths and schemas may evolve.
- This decision does not supersede any existing ADR. A later coordination cutover would require a new ADR that explicitly supersedes the affected ownership clauses.
