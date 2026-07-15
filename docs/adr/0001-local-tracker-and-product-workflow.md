# ADR-0001: Local markdown tracker + product workflow

## Status

Accepted

## Context

Repo is mid-pivot (demo playbook → design-playbook agent plugin). No git remote. Need a place for specs/tickets and a fixed process for polish.

## Decision

1. Issues/specs live under `.scratch/<feature>/` (local markdown tracker).
2. Product process is documented in `docs/agents/product-workflow.md` (grill → dogfood → to-spec → to-tickets → implement → polish).
3. Domain docs are single-context: root `CONTEXT.md` + `docs/adr/`.

## Consequences

- No `gh issue` required until a remote exists.
- Agents must read `docs/agents/issue-tracker.md` before publishing tickets.
- v0 work tracks under `.scratch/design-playbook-v0/`.
