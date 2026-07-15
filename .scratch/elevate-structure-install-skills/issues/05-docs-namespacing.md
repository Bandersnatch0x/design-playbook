# 05 - Docs namespacing + marketplace-add lead

**What to build:** All install/usage docs lead with the namespaced marketplace-add path; bare `/design-io` is documented as a dev-time alias only. Root README is the "install this plugin" front door.

**Blocked by:** 01 (resolved)

**Status:** implemented (pending commit)

- [x] Root README leads with `/plugin marketplace add <owner>/<repo>` -> `/plugin install design-playbook@design-playbook`
- [x] Package README and skill bodies use namespaced `/design-playbook:*` invokes
- [x] Bare `/design-io` explicitly marked as `--plugin-dir` dev alias only, nowhere as the installed name
- [x] Root README is a front door (install + pointer to package README), no skill detail sprawl at root
- [x] `product-*` commands documented as monorepo-root-only, not in package

## Implementation notes

- Root README install section reordered: path of record (marketplace add `owner/repo` -> install) first; `--plugin-dir` + local-marketplace as secondary dev/self-test.
- Fixed post-01 staleness: all `marketplace add` commands now point at the **repo root** (or `owner/repo`), not `packages/design-playbook` (the catalog moved to repo root in 01). Verified zero `marketplace add .../packages/design-playbook` remain.
- Package README install section rewritten: path of record = `owner/repo`; local dev = `--plugin-dir` at package + local marketplace at repo root.
- CLAUDE.md self-test section aligned.
- Verified: no bare `/design-io` as installed name anywhere; all invokes namespaced.
- `product-*` already documented as monorepo-root-only (root README + package "What ships").

## Review (standards + spec, inline; no git)

- **Spec:** matches 02 (path of record) + 05 (front door) decisions.
- **Standards:** ADR-0006 (catalog at repo root) reflected in docs; no stale package-catalog paths.
- **Commit:** deferred to ticket 06.

Unblocks: **06** (release + tag).
