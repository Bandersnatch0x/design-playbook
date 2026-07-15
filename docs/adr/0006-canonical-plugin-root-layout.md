# ADR-0006: Canonical plugin-root layout

## Status

Accepted (implement, ticket 04)

## Context

Skills/commands were placed under `packages/design-playbook/.claude/` — the standalone (`.claude/`) convention, not the plugin convention. Claude Code plugin docs require component directories at the **plugin root**, with only `plugin.json` inside `.claude-plugin/`. For public install (Q1) the wrong layout would fail or require non-standard path overrides.

## Decision

1. Plugin root = `packages/design-playbook/`.
2. `skills/` and `commands/` live at the plugin root (moved out of `.claude/`).
3. Only `plugin.json` sits in `.claude-plugin/`. `marketplace.json` also under `.claude-plugin/` for the local marketplace, `source: "./"`.
4. Codex bridge moved to `codex/AGENTS.md` so it is not scanned as a skill.
5. `plugin.json` drops custom `skills`/`commands` path fields; default resolution is used.

## Consequences

- Skills invoke namespaced: `/design-playbook:<skill>`.
- Install: `claude --plugin-dir <path>/packages/design-playbook`, or local marketplace add + install.
- All docs reference `packages/design-playbook/skills|commands`, not `.claude/`.
- Live clean-session smoke test remains a manual step (documented in ticket 04).
