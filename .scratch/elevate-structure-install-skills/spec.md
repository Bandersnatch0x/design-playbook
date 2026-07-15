# Spec - Elevate structure, install, skill workflow

**Triage:** ready-for-agent  
**Source:** collapses `.scratch/elevate-structure-install-skills/map.md` (tickets 01-08, all resolved) + ADRs 0001-0007.

## Problem Statement

design-playbook v0 is a working six-skill plugin, but a stranger cannot install it cleanly: the marketplace catalog lives *inside* the package (so `/plugin marketplace add owner/repo` does not resolve from a repo root), install docs teach bare `/design-io` (invalid after namespaced install), and the recirculate sell - the core differentiator - is only soft-verified (dogfood lists blocking findings without a closure trail). The maintainer polish loop also leaks monorepo-only commands into the public package surface.

## Solution

A public-installable monorepo where the marketplace catalog sits at the repo root pointing at the package, install docs lead with the namespaced marketplace-add path, the recirculate contract has a single owner and a closure gate, and the public package ships only authored runtime content. A stranger runs two commands and gets a predictable Design I/O pass.

## User Stories

1. As a stranger, I want to install with `/plugin marketplace add <owner>/<repo>` then `/plugin install design-playbook@design-playbook`, so that I don't clone or build anything.
2. As an installed user, I want to invoke `/design-playbook:design-io <ask>`, so that the namespaced command works the first time.
3. As an installed user, I want the orchestrator to route a native-desktop ask through `native-craft` before `ui-picker`, so that native-feel is declared before any web shell is picked.
4. As an installed user, I want a failed review to recirculate to the owning declaration and be re-checked, so that "blocking" always has a closure trail.
5. As a reviewer, I want one recirculate table owned by the acceptance skill, so that editing acceptance does not drift from the orchestrator's map.
6. As a maintainer, I want `product-*` commands to stay out of the public package, so that strangers never see monorepo-internal workflow.
7. As a maintainer, I want a manual release gate I can run before tagging, so that a version is only shipped when install + dogfood + static checks pass.
8. As a reader of the GitHub repo, I want the root README to lead with install, so that the front door is "install this plugin", not engineering docs.
9. As an attribution-aware reader, I want README + NOTICE to credit native-feel (MIT) and the upstream playbook (inspired), so that the license boundary is honest.
10. As a maintainer, I want semver on the plugin manifest, so that installed users get stable, pinnable updates.

## Implementation Decisions

- **Topology (01/05):** Repo root gains a `.claude-plugin/marketplace.json` catalog with one plugin entry whose `source` points at the package subdirectory. The in-package `marketplace.json` is removed; the in-package `plugin.json` stays (plugin root unchanged). Root is "front door + engineering shell"; package is the only runtime surface.
- **Install path of record (02):** Lead docs with marketplace-add + install; `--plugin-dir` is secondary (dev/self-test). All slash references in docs and skill bodies are namespaced (`/design-playbook:*`); bare `/design-io` is documented as a dev-time alias only.
- **Skill surface (03, ADR-0007):** Six model-invoked skills - `design-playbook` (orchestrator), `ux-spec`, `ui-picker`, `craft-guard`, `native-craft`, `ui-evaluator`. `native-craft` already authored (decision gate + native conventions condensed in our voice; depth points to the original MIT skill). Three commands only: `design-io`, `ux-spec`, `ui-review`.
- **Recirculate SSOT (04-P1):** The recirculate map is owned by `ui-evaluator`; the orchestrator keeps a one-line pointer, not a duplicated table.
- **Recirculate closure gate (04-P0):** Dogfood gains a sixth gate: blocking findings must show a `recirculate -> fix -> re-eval -> 0 blocking` trail (or explicit acceptance). Skill `Done when` criteria updated to match.
- **Description trim (04-P2):** Light writing-great-skills pass on the six descriptions - leading word + one trigger branch + reach clause; drop synonym branches. Bodies untouched.
- **Release gate (06):** Manual five-step checklist (plugin-dir session + clean reload; namespaced design-io real-ask six gates; `claude plugin validate` if present; package `rg` clean; README install trio copy-paste) + `git tag vX.Y.Z`. Explicit semver in the plugin manifest.
- **Public-claim prerequisite (06):** `git init` + public remote is a hard prerequisite for any public install claim; without it the product is `--plugin-dir`-only.
- **Maintainer loop (05):** `product-*` commands remain at the monorepo root only; the public package never ships them. Root `CLAUDE.md` is single-layer and points at the workflow.

## Testing Decisions

- **One primary seam:** a clean Claude session loads the plugin and runs `/design-playbook:design-io` on a real product UI ask; the run is judged by the six dogfood gates (L5/L6 before UI, decision report before code, point-back findings, no Done-when skip, generality, recirculate closure). Pass = all six green.
- **Static gates (same seam, low cost):** manifest JSON valid; plugin-root layout (`skills/`+`commands/` at root, only `plugin.json` in `.claude-plugin/`); package `rg` clean of upstream residue and bare-slash install claims; README install trio resolves.
- **Good test = external behavior:** the plugin is tested as an installed user experiences it (invoke + gates), not by asserting skill prose internals.
- **Prior art:** dogfood logs 001/002 under `.scratch/design-playbook-v0/dogfood/` define the gate format; this spec adds the sixth gate and promotes the seam to the release checklist.
- **No new automated CI** this increment (deferred per 06); the seam is manual until a remote + CI exist.

## Out of Scope

- Community marketplace submission (`@claude-community`) - later release (06).
- Multi-platform install CLI; style/palette DB; Figma MCP dependency; demo-site revival (ADR-0002).
- Third dogfood scene (data-dense table/chart) as a release gate - next increment (04).
- Skill regression automation / CI (06 "not yet").
- Demoting skills to user-invoked (04 deferred).
- Rewriting skill bodies beyond the description trim (sprawl risk).

## Further Notes

- `native-craft` is already implemented (execution carried into the map per user direction, ADR-0007); it is NOT build work for this spec - only its description trim (P2) is.
- Decisions 01-08 are closed; this spec only converts them into buildable work. Reopening any decision requires a new ADR.
- Hand off next to `/to-tickets` to split into tracer-bullet tickets (frontier: repo-root catalog + delete in-package catalog; recirculate SSOT move; sixth dogfood gate; description trim; docs namespaming; git init + tag).
