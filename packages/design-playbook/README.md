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
| **design-playbook** | Spec? → plan? → shell → optional preview* → fill → craft → optional observe* → evaluate / recirculate |
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

## Contract vs enforcement

Evidence exists only to satisfy a declared criterion — an observation without a binding to an L6 acceptance item is telemetry, not evidence. Runtime capture is done by external providers; design-playbook owns the binding (manifest) and the verdict (ledger), never the runtime.

The Design I/O run is a **declared, host-neutral contract** over plain-Markdown artifacts (spec, decision report, point-back ledger). Any coding agent that emits that shape can be checked; Claude Code and Codex are adapters over the same artifacts, and every generator, bridge, or design-system gate is an optional input, never a dependency.

Optional sibling package [`design-playbook-preview`](../design-playbook-preview/) is a stdio MCP adapter (`preview_prototype`) for disposable HTML prototypes; the orchestrator **probes** for it and skips preview when absent. design-playbook does not package-depend on it.

Optional sibling package [`design-playbook-evidence`](../design-playbook-evidence/) is a stdio MCP adapter (`execute_capture_plan`) for post-Fill runtime capture (screenshot / a11y tree / interaction trace via Playwright); the orchestrator **probes** for it and skips observe when absent. Provider writes artifacts only — never the manifest. design-playbook does not package-depend on it.

What is **deterministically enforced** today: plugin install/structure (`scripts/validate.py --strict`) and the run-artifact shape (`scripts/validate_run.py` — L1–L6 present; every top-level L6 item ordered `Given -> When -> Then`; one non-empty four-field evidence ledger row per `L6.<n>` with allowed results; four non-empty finding fields with non-empty source; exactly one explicit `## Verdict` of `Pass` or `Recirculate`; Pass requires every evidence result to be `pass` and exactly one issue-linked `0 blocking` closure per blocking finding; exit 0/`RUN OK`, exit 1/`RUN INVALID`, exit 2/`RUN ERROR`; regression-tested by `tests/test_validate_run.py`, which also validates the showcase artifacts directly; **G5** is a *conditional* preview-confirm gate — enforced only when preview artifacts exist / `--preview-dir` is used; **G6** is a *conditional* evidence-binding gate — enforced only when a ledger `observed` references an `evidence/` artifact / `--evidence-dir` is used). The `observe*` step probes an external MCP tool `execute_capture_plan` (e.g. Playwright MCP) and is skipped when absent. Everything else in the pipeline is agent-executed craft judgment, not a machine gate.

## Codex

See `codex/AGENTS.md`.
