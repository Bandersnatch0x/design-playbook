<div align="center">

<img src="packages/design-playbook/showcase/screenshots/hero.png" alt="design-playbook — Design I/O for coding agents" width="100%" />

# 🎴 design-playbook

### *Design I/O for coding agents — declarations + contracts that make UI generation constrained, reviewable, and recirculatable.*

[![Version](https://img.shields.io/badge/Version-0.4.1-2DD4BF?style=flat-square&logo=semver&logoColor=black)](.#)
[![License](https://img.shields.io/badge/License-MIT-2DD4BF?style=flat-square&logo=opensourceinitiative&logoColor=black)](./packages/design-playbook/LICENSE)
[![Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-2DD4BF?style=flat-square&logo=claude&logoColor=black)](.#)
[![Skills](https://img.shields.io/badge/Skills-6-2DD4BF?style=flat-square)](.#)
[![Commands](https://img.shields.io/badge/Commands-3-2DD4BF?style=flat-square)](.#)
[![Codex](https://img.shields.io/badge/Codex-ready-2DD4BF?style=flat-square)](./packages/design-playbook/codex/AGENTS.md)

*Not another style/palette pack. Compose with `ui-ux-pro-max` + `frontend-design`; this plugin owns the **pipeline and acceptance**.*

</div>

---

## ✨ What it is

A Claude Code / Codex plugin. One predictable pass per run — **Design I/O**: `ux-spec? → plan? → (native-craft?) → ui-picker → (preview*) → fill → craft-guard → (observe*) → ui-evaluator`, where acceptance **points back** to the declaration that owns each failure, and blocking findings **recirculate** until closed. `?` = conditional entry; `preview*`/`observe*` run only when their optional MCP adapter is present (`preview_prototype` before Fill, `execute_capture_plan` after craft) — otherwise skipped. `preview*` is a human-in-the-loop confirm gate (G5); `observe*` captures criterion-addressable runtime evidence into a manifest the evaluator binds to a criterion (G6).

- **Declarations** *(what good is)*: `spec` · `domain` · `craft` · `design` · `components` · `template`
- **Contracts** *(how work enters the pipeline)*: `skill` (timing) · `evaluator` (acceptance + recirculate)

> 🎬 **Try it:** `/design-playbook:design-io <your ask>` — one pass lands `spec.md`, a decision report, and a point-back ledger under `.scratch/<run>/` (artifact shape: [`showcase/01-spec.md`](./packages/design-playbook/showcase/01-spec.md)). **See it run on a real project:** the [`showcase/`](./packages/design-playbook/showcase) folder is a full Design I/O pass against SwarSight — spec, decision report, and point-back critique with a closed recirculate trail.

## 📦 Install

```text
/plugin marketplace add <owner>/<repo>
/plugin install design-playbook@design-playbook
```

<details>
<summary>Local dev / self-test</summary>

The marketplace catalog lives at the **repo root** (not the package):

```text
claude --plugin-dir <abs>/packages/design-playbook          # dev load, no install
/plugin marketplace add <abs-to-repo-root>                 # local marketplace
/plugin install design-playbook@design-playbook
```

</details>

Invoke **namespaced**: `/design-playbook:design-io <ask>`. Bare `/design-io` is a `--plugin-dir` dev alias only.

## 🧩 Skills & commands

Six model-invoked skills (`/design-playbook:<name>`):

| Skill | Role |
| :--- | :--- |
| `design-playbook` | 🎯 Orchestrator (full pipeline) |
| `ux-spec` | 📋 Six-layer spec declaration |
| `ui-picker` | 🧱 Shell + component semantics |
| `craft-guard` | 🛡️ Craft / anti-AI-slop |
| `native-craft` | 🖥️ Native-feel desktop declaration |
| `ui-evaluator` | ✅ Point-back acceptance + recirculate |

**Commands:** `design-io` (full pipeline) · `ux-spec` (spec only) · `ui-review` (accept only)

## 🔗 Stack with ecosystem

| Package | Use for |
| :--- | :--- |
| **design-playbook** | Spec? → plan? → shell → optional preview* → fill → craft → optional observe* → point-back |
| [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Style / palette / type search |
| `frontend-design` | Anti-template visual direction |
| [native-feel-skill](https://github.com/yetone/native-feel-skill) | Full native-feel depth (WebView, IPC, memory) |

## 🔌 Adapters (bundled in v0.3+)

Preview and Evidence MCP runtimes ship **inside** the main plugin
(`packages/design-playbook/mcp/` + `.mcp.json` with `${CLAUDE_PLUGIN_ROOT}`).
Marketplace install therefore registers both tools without a second package.
The orchestrator still **probes** and skips steps when a host has no MCP tools.

| Adapter | MCP tool | Enables | Notes |
| :--- | :--- | :--- | :--- |
| `design-playbook-preview` | `preview_prototype` | `preview*` human confirm gate (G5) | Bundled; sibling dir is a compatibility launcher |
| `design-playbook-evidence` | `execute_capture_plan` | `observe*` runtime evidence (G6) — needs Playwright + Chromium | Bundled; capture still optional at runtime |

Docs: [preview](./packages/design-playbook-preview/#install--mcp-config) · [evidence](./packages/design-playbook-evidence/#install--mcp-config)

## 🗂️ Layout

```text
.claude-plugin/marketplace.json   ← repo-root catalog (source: ./packages/design-playbook)
packages/design-playbook/         ← public plugin (skills, commands, mcp/, examples, showcase)
packages/design-playbook/mcp/     ← bundled Preview + Evidence MCP runtimes
packages/design-playbook-preview/ ← compatibility launcher + docs (G5)
packages/design-playbook-evidence/← compatibility launcher + docs (G6)
docs/agents/  docs/adr/           ← engineering shell (tracker, workflow, decisions)
CONTEXT.md  .scratch/             ← glossary, specs, tickets, dogfood logs
```

Runs land their artifacts under `.scratch/<run>/` in your project — see the [package README](./packages/design-playbook/README.md) and `SKILL.md` steps 3, 5, 8.

**Maintainer helpers (repo root, not a product CLI):** `scripts/doctor.py` (install health), `scripts/run_status.py` (derive status/resume from run artifacts), `scripts/release.py` (tag gate), `scripts/validate.py` (static plugin surface).

Root = GitHub front door + engineering shell · Package = only runtime surface · `product-*` maintainer commands stay at root, never in the package.

## 📄 License

MIT (authored content). See [`LICENSE`](./packages/design-playbook/LICENSE) + [`NOTICE`](./packages/design-playbook/NOTICE). No rights claimed over any third-party playbook corpus.

---

<div align="center">

[中文说明](README-zh.md) · [Showcase](./packages/design-playbook/showcase) · [Workflow](./docs/agents/product-workflow.md)

</div>
