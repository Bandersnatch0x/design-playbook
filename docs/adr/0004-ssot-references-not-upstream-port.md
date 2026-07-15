# ADR-0004: SSOT in skills; reference is not a port

## Status

Accepted (grill Q5 + user clarification)

## Context

Declaration-like material exists in skill `references/`, demo `public/attachments/`, and (historically) playbook manuscript. Public install requires a clear redistributable surface. User clarified the project **references** upstream playbook as inspiration — it is not superimposing or relocating that corpus into this product.

## Decision

1. **SSOT** for declaration snippets used by the agent is `packages/design-playbook/skills/*/references/*` (and skill bodies).
2. **No sync pipeline** from `public/attachments/*` or upstream manuscript into the plugin.
3. **Hygiene rule:** any reference content that is playbook-specific lift (vendor product voice, upstream case prose, brand-bound samples) must be **removed or rewritten** into generic Design I/O language before public ship.
4. Demo attachments are not SSOT and are not part of the plugin redistributable pack (ADR-0003).

## Consequences

- A v0 ticket exists to audit/strip/rewrite references for playbook lift.
- Onboarding examples are authored under skills (e.g. `references/` or `examples/`), not copied from attachments.
- Agents must not “content:sync” or otherwise pull manuscript into `packages/design-playbook/skills/`.
