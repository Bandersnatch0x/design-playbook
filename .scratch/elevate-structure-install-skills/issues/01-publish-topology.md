# 01 — Publish topology

**Type:** grilling  
**Status:** resolved  
**Blocked by:** None — can start immediately

## Question

For public install of design-playbook, what is the **canonical publish topology**?

Options to decide among (or refine):

- **A.** Keep monorepo: root = engineering shell (docs/ADR/scratch); product = `packages/design-playbook` only; marketplace points at package path (or package published alone later).
- **B.** Split: public git repo is **package-only**; monorepo docs move or become private.
- **C.** Hybrid: monorepo stays, but release artifact is always a **zip/subtree** of the package (never “clone whole monorepo = install”).

What do strangers clone/add, and what must never be required on the install path?

## Answer

**Decision: A (monorepo retained), refined so the stranger path is one-step.**

- **Marketplace catalog lifts to repo root**: `.claude-plugin/marketplace.json` at the git repo root, with a plugin entry `source: "./packages/design-playbook"`. This is what makes `/plugin marketplace add <owner>/<repo>` resolve directly (research 07: catalog must sit at the added repo root).
- **Plugin manifest stays in the package**: `packages/design-playbook/.claude-plugin/plugin.json` unchanged; component dirs (`skills/`, `commands/`) stay at the package root (plugin root).
- **Remove the in-package `marketplace.json`** (`packages/design-playbook/.claude-plugin/marketplace.json`) — it becomes redundant; `--plugin-dir` needs only `plugin.json`, not a catalog.
- **Stranger install path**: `/plugin marketplace add <owner>/<repo>` → `/plugin install design-playbook@<marketplace-name>`.
- **Never required on the install path**: cloning/building the whole monorepo, presence of `docs/` / `.scratch/`, any Node/npm step, or the removed demo site.

Root now holds two hats: engineering shell (docs/adr/scratch) **and** a thin repo-root `.claude-plugin/` catalog. Root README stays the GitHub front door but must lead with the marketplace-add install.

**Consequences (for the eventual implement spec, not done here):**
1. Create repo-root `.claude-plugin/marketplace.json` (name TBD in ticket 06; `source: "./packages/design-playbook"`).
2. Delete `packages/design-playbook/.claude-plugin/marketplace.json`.
3. Update all install docs to `owner/repo` add form; keep `--plugin-dir` as the dev/self-test path.
4. Requires a git remote to exist (feeds ticket 06 `git init` + host prerequisite).

Unblocks: **02** (install path of record), **05** (monorepo root role).
