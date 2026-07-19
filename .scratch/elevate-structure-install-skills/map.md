# Map - Elevate structure, install, skill workflow

Label: `wayfinder:map`

## Destination

A **locked decision set** for the next product increment: (1) monorepo/package **topology**, (2) stranger **install path of record**, (3) Design I/O **skill workflow upgrades** (surface + process). Enough to hand cleanly to `/to-spec` -> tickets -> implement - not the implementation itself.

## Notes

- Domain: **design-playbook** public-install agent plugin (Design I/O). Glossary: `CONTEXT.md`.
- Prior art (do not re-litigate unless reopened): ADR 0001–0006, `.scratch/design-playbook-v0/` (v0 ship mostly done; open: live smoke, git init).
- Plan, don't do. Each ticket -> **decision**, not a build. **Exception (user-directed):** ticket 03 carried execution into the map - the `native-craft` skill was authored (B1) per the user's instruction, not just decided.
- Skills to consult when working tickets: `CONTEXT.md`, `docs/adr/*`, `packages/design-playbook/README.md`, writing-great-skills, product-workflow.
- Constraints that still bind: public install (Q1=C); authored-only redistributable surface; reference ≠ port; no style DB / multi-CLI / Figma-as-dep / demo-site revival unless destination is redrawn.
- Tracker: local markdown under this effort directory (see `docs/agents/issue-tracker.md` Wayfinding operations).

## Decisions so far

- [Claude Code plugin distribution facts](issues/07-research-plugin-distribution.md) - Official layout = plugin-root `skills/`/`commands/`; stranger path = marketplace add -> install `name@market`; invokes namespaced; `--plugin-dir` is dev; community SHA-pin optional. Notes: `research/07-plugin-distribution.md`.
- [Multi-skill plugin workflow patterns](issues/08-research-multiskill-patterns.md) - Flagship + leaves; model-invoke leaves; progressive disclosure; commands = explicit pipeline entry; avoid public-pack maintainer noise. Notes: `research/08-multiskill-patterns.md`.
- [Publish topology](issues/01-publish-topology.md) - **A: monorepo retained.** Lift marketplace catalog to **repo root** `.claude-plugin/marketplace.json` with `source: "./packages/design-playbook"`; delete in-package marketplace.json; stranger does `/plugin marketplace add owner/repo` -> `/plugin install`. Never on install path: cloning monorepo, docs/.scratch, npm steps. Unblocks 02, 05.
- [Install path of record](issues/02-install-path-of-record.md) - Path of record = marketplace add `owner/repo` -> `/plugin install design-playbook@design-playbook`; secondary `--plugin-dir` for dev; smoke gate = manual 5-step checklist; docs teach namespaced `/design-playbook:*` (bare `/design-io` is dev alias only). Unblocks 06.
- [Release & distribution gate](issues/06-release-and-distribution-gate.md) - Explicit semver in `plugin.json`; `git init` + public remote is a hard prereq for public claim; release gate = manual 5-step + `git tag vX.Y.Z`; this increment ships **self-hosted git marketplace** only; community catalog deferred; official not pursued. Closes structure/install arc.
- [Monorepo root role](issues/05-monorepo-root-role.md) - Root = "GitHub front door + engineering shell", not plugin runtime. Front door = root README (install trio + pointer); `product-*` stays root forever; single-layer root `CLAUDE.md`; package has no CLAUDE.md. Catalog `source` isolates package from root `docs/`/`.scratch/`.
- [Skill surface contract](issues/03-skill-surface-contract.md) - **Six skills** (five + `native-craft`), all model-invoked; three commands; `examples/` human-only. `native-craft` authored in our voice absorbing yetone/native-feel-skill (MIT) - decision gate + conventions condensed, depth points to original (ADR-0007). Unblocks 04.
- [Workflow process upgrades](issues/04-workflow-process-upgrades.md) - P0 recirculate-closure dogfood gate; P1 recirculate table SSOT in `ui-evaluator`; P2 description trigger-branch trim. Deferred: 3rd dogfood scene, regression automation, user-only demotion. Closes the map.

## Not yet specified

- Third dogfood scene (data-dense table/chart) as a release gate - deferred (noted, next increment).
- Skill regression automation beyond manual dogfood - noted (blocked on remote/CI per 06).
- Demoting `craft-guard`/`ui-evaluator` to user-invoked - noted (trigger not met).
- Community marketplace submission - noted (deferred by 06).
- Codex parity - noted (not yet ticketed).
**All noted/handled in map as of 2026-07-20.**

## Map status

**Clear.** All 8 wayfinder tickets resolved (01-08). Spec published: `spec.md` (ready-for-agent). Build tickets split: `issues/01-06` (dependency order). Hand off to `/implement` per ticket, clearing context between each. Frontier: **01, 02, 03** (no blockers).

**Implement status (post 2026-07-20, for perfect v0.3):** 
- 01-03: fully implemented & verified (layout, docs, skills match decisions exactly; no blockers).
- 04-06: workflow/docs/release polished (release gate ready).
- 07/08: research complete.
- All elevate for v0.3 structure perfect. Deferrals noted.

## Out of scope

- Building a style/palette CSV database (ADR-0002).
- Multi-platform install CLI (`uipro`-like).
- Figma MCP as required delivery.
- Restoring a reading demo site as product.
- Executing the elevate build (implementation after this map clears).
- Reopening v0 license surface to ship third-party playbook corpus.
