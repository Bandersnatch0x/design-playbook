# 06 — Release and distribution gate

**Type:** grilling  
**Status:** resolved  
**Blocked by:** 02 (resolved)

## Question

What is the **release gate** and distribution stance for elevate?

Decide:

1. Minimum bar to tag a version (smoke: `--plugin-dir` session? marketplace install? dogfood count?).
2. Version field strategy: explicit `plugin.json` version vs git SHA only.
3. Hosting: private path-only vs public git marketplace vs submit to community catalog — **in this effort or later?**
4. Whether `git init` + remote is a prerequisite task before any public claim.

Output: a release checklist + “not yet” list for distribution channels.

## Answer

**Decision: default accepted.**

1. **Versioning = explicit semver.** `plugin.json` carries `"version"`; bump patch per release. Not git-SHA-only - public install needs stable, readable, pinnable versions.
2. **`git init` + public remote is a hard prerequisite for any public claim.** Without a remote, `/plugin marketplace add owner/repo` has nothing to point at, so the product is limited to `--plugin-dir` private use. Two tiers:
   - Private/self-use: no remote needed; `--plugin-dir`.
   - Public ship: `git init` + push to public GitHub, then add repo-root `marketplace.json` (per 01).
3. **Release gate = manual 5-step checklist (carried from 02):** `--plugin-dir` session + clean `/reload-plugins`; `/design-playbook:design-io` real-ask five gates; `claude plugin validate` if present; package `rg` clean of upstream residue; README install trio copy-paste works. Then `git tag vX.Y.Z && git push --tags`.
4. **Distribution channels:**
   - This increment: **self-hosted git marketplace** (`/plugin marketplace add owner/repo`) + `--plugin-dir` secondary. Target.
   - Deferred (later release): **community catalog** `@claude-community` - needs review + SHA pin; moved to Not-yet-specified.
   - Not pursuing: **official catalog** (Anthropic-curated, no application).

**"Not yet" list:** no remote yet; no `claude plugin validate` confirmed available; no automated/smoke CI; no CHANGELOG; no community submission.

Unblocks: nothing further in the structure/install branch - that arc (01→02→06) is closed except for execution (spec/tickets/implement).
