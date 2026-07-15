# design-playbook

Agent plugin: **Design I/O** for product UI (Claude Code / Codex).

Declarations + contracts — not a style CSV pack. Compose with [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) and Anthropic `frontend-design` for aesthetics; this package owns pipeline and acceptance.

## Install (Claude Code)

Path of record (published) - the marketplace catalog lives at the **repo root**, not in this package:

```text
/plugin marketplace add <owner>/<repo>
/plugin install design-playbook@design-playbook
```

Local dev / self-test:

```bash
claude --plugin-dir <abs-path>/packages/design-playbook      # dev load, no install
# or local marketplace (point at the repo root, where the catalog lives)
/plugin marketplace add <abs-path-to-repo-root>
/plugin install design-playbook@design-playbook
```

After install, skills and commands are **namespaced** by the plugin name:

| Invoke | Role |
| --- | --- |
| `/design-playbook:design-playbook` | Orchestrator skill (model-invoked) |
| `/design-playbook:ux-spec` | Six-layer spec skill |
| `/design-playbook:ui-picker` | Shell + components skill |
| `/design-playbook:craft-guard` | Craft / anti-slop skill |
| `/design-playbook:native-craft` | Native-feel desktop declaration skill |
| `/design-playbook:ui-evaluator` | Point-back acceptance skill |
| `/design-playbook:design-io` | Full pipeline command |
| `/design-playbook:ux-spec` | Spec-only command |
| `/design-playbook:ui-review` | Review command |

Bare `/design-io` is **not** the installed name — always use the `design-playbook:` prefix.

## Stack with other skills

| Package | Use for |
| --- | --- |
| **design-playbook** | Spec → shell → fill → craft → evaluate / recirculate |
| ui-ux-pro-max | Style / palette / type search |
| frontend-design | Anti-template visual direction |

## Layout

```text
.claude-plugin/
  plugin.json          ← plugin manifest (the marketplace catalog lives at the repo root)
skills/<name>/SKILL.md ← model-invoked skills
commands/<name>.md     ← slash commands (design-io, ux-spec, ui-review only)
codex/AGENTS.md        ← Codex bridge notes
examples/              ← self-authored onboarding samples
LICENSE · NOTICE       ← authored-only scope
```

## What ships

Only authored content in this package (skills, pipeline commands, metadata, self-written examples). See `NOTICE` and repo ADRs 0003–0006. Repo-maintainer polish commands live in the monorepo root `.claude/commands/`, not in this package.

## Codex

See `codex/AGENTS.md`.
