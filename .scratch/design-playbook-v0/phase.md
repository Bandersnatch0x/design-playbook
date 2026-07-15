# Phase pointer

**Current:** `6-polish` (review fixes applied)

| Phase | Status |
| --- | --- |
| 0-setup | done |
| 1-grill | done (Q1–Q6, ADR 0001–0005) |
| 2-dogfood | done (001, 002) |
| 3-to-spec | done |
| 4-to-tickets | done (01–05 resolved) |
| 5-implement | done (ADR-0006) |
| 6-polish | review fixes landed |

**Review fixes (done):**
- [x] Slash names namespaced in skill + README
- [x] `product-*` moved to monorepo `.claude/commands/` (not in package)
- [x] Self-authored examples (ops-list-spec, decision-report, point-back)
- [x] README layout truth (plugin.json + marketplace.json)
- [x] ADR-0003/0004 path language aligned with plugin-root layout

**Still open (human):**
1. Clean-session smoke: `claude --plugin-dir <abs>/packages/design-playbook` → `/design-playbook:design-io …`
2. `git init` + first commit

**Package commands (ship):** design-io · ux-spec · ui-review  
**Monorepo commands (maintain):** product-next · product-grill · product-dogfood
