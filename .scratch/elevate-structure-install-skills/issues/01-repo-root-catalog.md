# 01 - Repo-root marketplace catalog

**What to build:** A stranger can `/plugin marketplace add <owner>/<repo>` and resolve the plugin, because the marketplace catalog sits at the repo root pointing at the package. The in-package catalog is removed.

**Blocked by:** None - can start immediately

**Status:** ready-for-agent -> implemented (pending code-review + commit)

- [x] Repo root has `.claude-plugin/marketplace.json` with one plugin entry, `source` pointing at the package subdirectory
- [x] `packages/design-playbook/.claude-plugin/marketplace.json` deleted; `plugin.json` remains
- [x] `plugin.json` manifest JSON valid; layout still plugin-root (`skills/`, `commands/` at root)
- [x] A local `--plugin-dir` self-test still loads (no regression from catalog move) - structural: plugin.json intact, layout unchanged; catalog not required for `--plugin-dir`
- [x] No doc claims "clone whole monorepo = install"

## Implementation notes

- Created repo-root `.claude-plugin/marketplace.json` with `source: "./packages/design-playbook"`.
- Deleted in-package `packages/design-playbook/.claude-plugin/marketplace.json`.
- Fixed stale package README Layout line (marketplace.json no longer in package `.claude-plugin/`).
- JSON validated; source resolves to a dir containing `plugin.json`; six skills + three commands still at plugin root.

## Review (standards + spec, no git so inline)

- **Spec:** matches 01/05 decisions (catalog at repo root, source -> package); no clone-to-install claims.
- **Standards:** ADR-0006 layout preserved; ADR-0003 redistributable surface unchanged (catalog is metadata, still authored).
- **Commit:** deferred to ticket 06 (`git init` does not exist yet).
