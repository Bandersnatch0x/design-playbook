# ADR-0002: v0 scope — cut bloat, add public-install necessities

## Status

Accepted (grill Q3)

## Context

First user is public install (Q1). Success criteria are Design I/O process gates (Q2). Temptation exists to build style libraries, CLIs, Figma integration, or polish the demo site as “progress.”

## Decision

**Out of v0 product scope**

- Style/palette CSV databases (compose with existing skills instead)
- Multi-platform install CLI
- Figma MCP as a delivery dependency
- Demo-site visual redesign as the release artifact

**In v0 because of public install**

- Explicit license/content boundary for what may be redistributed
- Stranger-safe copy-paste install documentation
- Self-authored clean examples for onboarding/dogfood
- README section: stacking with ui-ux-pro-max and frontend-design
- craft-guard quality proven by dogfood, not by a new style engine

## Consequences

- Engineering tickets prioritize docs, license, SSOT examples, skill process — not `src/` chrome.
- Optional one-liners in README (e.g. Figma later) are documentation, not features.
- If a style DB is later needed, it is a new ADR and a new effort, not silent scope creep.
