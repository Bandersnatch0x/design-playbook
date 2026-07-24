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

## Install (Codex)

Same GitHub repo / monorepo root catalog. Codex-native manifest lives at `.codex-plugin/` (MCP uses relative paths).

```bash
codex plugin marketplace add Bandersnatch0x/design-playbook
codex plugin add design-playbook@design-playbook
```

Local monorepo:

```bash
codex plugin marketplace add <abs-path-to-repo-root>
codex plugin add design-playbook@design-playbook
```

Details + skills-only fallback: [`codex/AGENTS.md`](codex/AGENTS.md).

After install, skills and commands are **namespaced** by the plugin name:

| Invoke | Role |
| --- | --- |
| `/design-playbook:design-playbook` | Orchestrator skill (model-invoked) |
| `/design-playbook:design-baseline` | Discover/validate/draft the project `DESIGN.md` baseline |
| `/design-playbook:reference-intake` | Reference contract skill (screenshot/URL/analogy) |
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
| **design-playbook** | Baseline? → Reference? → Spec? → plan? → shell → optional preview* → fill → craft → optional observe* → evaluate / recirculate |
| ui-ux-pro-max | Style / palette / type search |
| frontend-design | Anti-template visual direction |

## Layout

```text
.claude-plugin/
  plugin.json          ← plugin manifest (the marketplace catalog lives at the repo root)
.mcp.json              ← bundled MCP servers, launched via ${CLAUDE_PLUGIN_ROOT} (ADR-0009)
mcp/{preview,evidence}/← MCP adapter runtimes (preview_prototype / execute_capture_plan)
skills/<name>/SKILL.md ← model-invoked skills
commands/<name>.md     ← slash commands (design-io, ux-spec, ui-review only)
codex/AGENTS.md        ← Codex bridge notes
examples/              ← self-authored onboarding samples
LICENSE · NOTICE       ← authored-only scope
```

## What ships

Only authored content in this package (skills, pipeline commands, metadata, self-written examples, self-authored bundled MCP adapters). See `NOTICE` and repo ADRs 0003–0006, 0009. Repo-maintainer polish commands live in the monorepo root `.claude/commands/`, not in this package.

## Contract vs enforcement

Evidence exists only to satisfy a declared criterion — an observation without a binding to an L6 acceptance item is telemetry, not evidence. Runtime capture is done by external providers; design-playbook owns the binding (manifest) and the verdict (ledger), never the runtime.

The Design I/O run is a **declared, host-neutral contract** over plain-Markdown artifacts (`DESIGN.md`, spec, decision report, point-back ledger). Any coding agent that emits that shape can be checked; Claude Code and Codex are adapters over the same artifacts. Generators and bridges remain optional; existing-product UI work must bind a valid/accepted project baseline or record an explicit waiver.

Run artifacts land under `.scratch/<run>/` (`design-baseline/`, `plan.md`, `preview/`, `evidence/manifest.jsonl`, `point-back.md`); see the orchestrator skill for what lands when. That is where to look — and manually intervene — when a run stalls.

**Bundled MCP (v0.3+):** Preview (`mcp/preview/`) and Evidence (`mcp/evidence/`) runtimes ship inside this package and are registered by `.mcp.json` (`${CLAUDE_PLUGIN_ROOT}`). Sibling monorepo dirs remain compatibility launchers/docs. The orchestrator still **probes** MCP `tools/list` and skips `preview*` / `observe*` when tools are absent. Evidence provider writes artifacts only — never the manifest. **`DESIGN_PLAYBOOK_RUN_ROOT`:** default `"."` in `.mcp.json` is the **MCP process cwd**, not the chat workspace — for a host-app dogfood, set an **absolute** path to `.scratch/<run>/` (see [`mcp/evidence/README.md`](mcp/evidence/README.md)). Capture responses include `written_path` (absolute) so mis-rooted writes are visible without a filesystem search.

What is **deterministically enforced** today: plugin install/structure (`scripts/validate.py`) and the run-artifact shape (`scripts/validate_run.py` — L1–L6 present; every top-level L6 item ordered `Given -> When -> Then`; one non-empty four-field evidence ledger row per `L6.<n>` with allowed results; four non-empty finding fields with non-empty source; exactly one explicit `## Verdict` of `Pass` or `Recirculate`; Pass requires every evidence result to be `pass` and exactly one issue-linked `0 blocking` closure per blocking finding; exit 0/`RUN OK`, exit 1/`RUN INVALID`, exit 2/`RUN ERROR`; regression-tested by `tests/test_validate_run.py`, which also validates the showcase artifacts directly; **G5** is a *conditional* preview-confirm gate — enforced only when preview artifacts exist / `--preview-dir` is used; **G6** is a *conditional* evidence-binding gate — enforced only when a ledger `observed` references an `evidence/` artifact / `--evidence-dir` is used; opt-in **strict mode** via `--require-preview` / `--require-evidence` / `--strict`). The `observe*` step probes MCP tool `execute_capture_plan` and is skipped when absent. Everything else in the pipeline is agent-executed craft judgment, not a machine gate.

## Codex

See `codex/AGENTS.md`.
