# ADR-0001: Local markdown tracker + product workflow

## Status

Accepted historically. The documentation and tracking choices below are
superseded by the 2026-09-24 amendment; the single-context domain model remains.

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

## Amendment (2026-09-24): separate shared docs from personal planning

The [contribution guide](../../.github/CONTRIBUTING.md) now owns documentation
and delivery requirements. Specs, plans, research and independent work tickets
stay local and untracked, outside `docs/`; contributors choose their own methods
and local layout. GitHub now serves user reports and feedback only; internal
work stays local. The explicitly authorized one-time historical issue migration
does not authorize deletion of future reports; see the
[issue policy](../agents/issue-tracker.md). The product workflow document explains
the installed product, not a required contributor process. Historical v0 logs and
checklists are not current authority or prerequisites.
