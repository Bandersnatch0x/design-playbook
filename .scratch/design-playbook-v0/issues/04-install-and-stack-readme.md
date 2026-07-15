# 04 — Verify copy-paste install + stack README

**What to build:** A stranger can install from the package and knows how to combine with ecosystem skills; install commands are correct against the split layout.

**Blocked by:** 03

**Status:** resolved

**Fix found:** plugin layout was wrong — `skills/`/`commands/` were under `.claude/` (standalone style). Per Claude Code plugin docs they must sit at the **plugin root**. Moved to `skills/` + `commands/`; only `plugin.json` stays in `.claude-plugin/`. Codex bridge moved out of `skills/` to `codex/` so it isn’t scanned as a skill. Dropped custom `skills`/`commands` path fields from `plugin.json` (defaults now resolve).

- [x] `claude --plugin-dir <path>/packages/design-playbook` documented; layout matches docs (root `skills/`, `commands/`, `.claude-plugin/plugin.json`)
- [x] marketplace.json `source: "./"` resolves from the package dir
- [x] README has a “stack with ui-ux-pro-max / frontend-design” section
- [x] Commands list matches actual files under `commands/` (pipeline only; product-* removed from package)
