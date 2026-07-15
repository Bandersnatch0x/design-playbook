# ADR-0003: Plugin redistributable surface

## Status

Accepted (grill Q4)

## Context

Upstream playbook content has no declared open-source license. v0 targets public install (Q1). Shipping the whole monorepo as “the product” risks redistributing third-party text/art.

## Decision

**May ship as the public plugin (marketplace / installable pack)**

- Authored plugin-root `skills/**`, `commands/**` (pipeline only), `.claude-plugin/**` (see **ADR-0006** for layout; paths below are historical if they say `.claude/`)
- Authored install documentation (package README)
- **Self-authored** declaration examples under `examples/` (written for this plugin; not copies of third-party attachments)

**Must not be claimed or bundled as redistributable plugin content without separate clearance**

- Upstream manuscript, figures, brand marks, hero assets
- Demo-site implementation as the product artifact
- Third-party attachment corpora
- Monorepo-only maintainer workflow commands (live at repo `.claude/commands/product-*`, not in the package)

Demo/learning material outside the package retains its own rights; it is not the public install artifact.

## Consequences

- Packaging/docs must define a **plugin root** (skills + commands + metadata + clean examples), not “clone whole repo = install.”
- Tickets will include rewrite or drop of attachment examples for onboarding.
- LICENSE/NOTICE on the plugin surface is a v0 deliverable; do not imply rights over upstream playbook body.
