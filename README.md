<div align="center">

<img src="packages/design-playbook/showcase/screenshots/hero.png" alt="design-playbook — evidence-backed UI delivery for coding agents" width="100%" />

# 🎴 design-playbook

### *Evidence-backed UI delivery for coding agents.*

[![Version](https://img.shields.io/badge/Version-0.25.0-2DD4BF?style=flat-square&logo=semver&logoColor=black)](https://www.npmjs.com/package/design-playbook)
[![License](https://img.shields.io/badge/License-MIT-2DD4BF?style=flat-square&logo=opensourceinitiative&logoColor=black)](./packages/design-playbook/LICENSE)
[![Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-2DD4BF?style=flat-square&logo=claude&logoColor=black)](#-try-it)
[![Skills](https://img.shields.io/badge/Skills-9-2DD4BF?style=flat-square)](#-skills--commands)
[![Commands](https://img.shields.io/badge/Commands-8-2DD4BF?style=flat-square)](#-skills--commands)
[![Codex](https://img.shields.io/badge/Codex-ready-2DD4BF?style=flat-square)](./packages/design-playbook/codex/AGENTS.md)

</div>

---

## ✅ Review UI against declared criteria and evidence

For a frontend or product engineer changing an existing Web UI with a coding agent, design-playbook connects the request, acceptance criteria, evidence, and repair owner. Required evidence that is missing leaves the criterion `blocked`. Explicitly skipping the evaluator produces an `audited: false` skeleton, not an audited Pass. Findings point back to their owning declarations and blocking findings recirculate for repair. Evaluator review does not replace the named human's semantic approval or guarantee independent judgment.

Two surfaces carry this:

1. **Acceptance with proof** — `ui-evaluator` + the point-back ledger: findings must cite criterion-bound evidence, and the closure trail is part of the run, not a chat summary.
2. **Existing-product UI work** — `design-baseline` discovers, validates, or drafts the project's `DESIGN.md` *before* changing a live product, so the change stays consistent with what already shipped.

### Current stage

As of 2026-09-24, this project is in **maintainer self-use and maintenance**.
Catalog submissions and participant recruitment are paused. Existing install
paths remain available; internal dogfood, historical examples, and automated
replays are not evidence of external adoption or repeat use. New capability
specs are proposals, not implementation or release commitments. Resumption
requires an explicit maintainer decision, not a date or passing internal tests.

## ⚡ One command, three artifacts

The mechanism behind that proof is one pass:

```text
/design-playbook:design-io <your UI ask>
```

A Design I/O run uses bundled MCP configuration, subject to host support and runtime prerequisites, and records three core artifacts under `.scratch/<run>/`:

1. **`spec.md`** — the six-layer declaration of what good is (intent → acceptance), written *before* any UI
2. **Decision report** — shell + component semantics, written *before* any code
3. **Point-back ledger** — every acceptance finding states which declaration it violates, plus the closure trail

## 🎬 Try it

**Claude Code**

```text
/plugin marketplace add https://github.com/Bandersnatch0x/design-playbook.git
/plugin install design-playbook@design-playbook
```

**Codex**

```bash
codex plugin marketplace add Bandersnatch0x/design-playbook
codex plugin add design-playbook@design-playbook
```

Then, namespaced (bare `/design-io` is a `--plugin-dir` dev alias only):

```text
/design-playbook:design-io <your UI ask>
```

On Cursor, Windsurf, Gemini CLI, Zed, or any of 30 supported agents: see [🌐 Install on other agents](#-install-on-other-agents). Honest degradation: 22 of the 30 are the generated `AGENTS.md` floor (orchestrator contract + MCP install guide, commands as prompt docs) — the tier table says exactly what each tier gets.

Codex install notes, the `[mcp_servers.*]` fallback when a marketplace is unavailable, and preview prerequisites: [`packages/design-playbook/codex/AGENTS.md`](./packages/design-playbook/codex/AGENTS.md).

**Runtime prerequisites:** a supported host with the relevant MCP tools
registered, Python 3 for the bundled runtimes, and a local browser for Preview.
Runtime capture additionally needs Playwright with Chromium and a reachable
application with the required test data and login state. See the
[capture setup](./packages/design-playbook-evidence/README.md#install--mcp-config).
An unavailable optional adapter is disclosed; required proof still cannot be
treated as passed merely because capture was skipped.

<details>
<summary>Local dev / self-test</summary>

The marketplace catalog lives at the **repo root** (not the package):

```text
claude --plugin-dir <abs>/packages/design-playbook          # dev load, no install
/plugin marketplace add <abs-to-repo-root>                 # local marketplace
/plugin install design-playbook@design-playbook

codex plugin marketplace add <abs-to-repo-root>
codex plugin add design-playbook@design-playbook
```

Version SSOT: `packages/design-playbook/package.json` and
`packages/design-playbook/.claude-plugin/plugin.json` stay version-locked; the
sibling bundle, root catalog, README badges, and generated Codex snapshot follow them.

</details>

## 📸 Evidence, not promises

Acceptance records keep their evidence limits visible:

- **Point-back** — every acceptance finding names the spec, domain, or craft declaration that owns it. No free-floating "looks good".
- **Recirculate** — blocking findings flow back to the owning stage until they close; the closure trail is part of the run artifacts.
- **No silent skip** — skip the audit and the result still carries the point-back skeleton, but marked `audited: false`, which strict validation refuses as a final result.
- **Missing is not inapplicable** - missing required proof is `blocked`; `not-applicable` needs an unmet applicability condition and a reason, not an unavailable capture tool.

[Historical cases and journey coverage](./packages/design-playbook/showcase/README.md#user-journey): three independent requests, plus one [complete current live run](./packages/design-playbook/showcase/case-reader/index.html) (case reader) that packages the whole chain — spec, real preview confirmations, Fill, craft audit, captured evidence, review, static handoff — with a [cross-run review report](./packages/design-playbook/showcase/run-review-2026-09-08.md). The SwarSight queue case retains its specification, design decisions, and review / repair record; it predates the current plan and capture requirements.

The images below are illustrated summaries of that historical case, not raw execution captures:

| | |
| :---: | :---: |
| **1 · ux-spec** — six-layer spec before any UI | **2 · ui-picker** — decision report before code |
| ![Six-layer spec](packages/design-playbook/showcase/screenshots/01-spec.png) | ![Decision report](packages/design-playbook/showcase/screenshots/02-decision-report.png) |
| **3 · ui-evaluator** — point-back + recirculate closure | **Historical result** — six case checks, not the current gate matrix |
| ![Point-back findings](packages/design-playbook/showcase/screenshots/03-point-back.png) | ![Historical case checklist](packages/design-playbook/showcase/screenshots/04-gates.png) |

**Preview review workbench** — inspect a design, anchor feedback, then confirm or revise. The [packaged human-confirmation record](./packages/design-playbook/showcase/README.md#case-b) belongs to a separate onboarding-form task; it is not confirmation of the queue case or of production acceptance:

![Preview confirm workbench — annotate, then confirm or revise](packages/design-playbook/showcase/screenshots/05-preview-confirm.png)

Browse [the three cases and their boundaries](./packages/design-playbook/showcase/README.md), or the [complete current run](./packages/design-playbook/showcase/case-reader/index.html) for an end-to-end record that includes a resume pause point and a generated static handoff. The retry interface is another task with local mock data, not a plugin execution.

## 🔁 The one-pass pipeline

Declare what good is *before* the code exists, generate against that declaration, then accept the result against the same declaration. Every run executes the same predictable **Design I/O** pass:

```text
design-baseline? → reference-intake? → ux-spec? → plan? → (native-craft?)
  → ui-picker → (preview*) → fill → craft-guard† → (observe*†) → ui-evaluator†
                              ▲                                       │
                              └────────────── recirculate ───────────┘
```

Six **declarations** own what good is (`spec` · `domain` · `craft` · `design` · `components` · `template`); two **contracts** govern how work enters the pipeline (`skill` for timing, `evaluator` for acceptance + recirculate).

<details>
<summary>Marker legend (<code>?</code> / <code>*</code> / <code>†</code>)</summary>

| Marker | Meaning |
| :--- | :--- |
| `?` | Conditional entry — `design-baseline?` for UI work in an existing product; `reference-intake?` when the ask carries a screenshot / URL / analogy |
| `*` | Adapter stage — runs only when its bundled MCP tool is registered; otherwise skipped, never a hard error |
| `†` | user-selectable audit stage (decision record [ADR-0033](./docs/adr/0033-audit-acceptance-user-preferences.md)) — asked once on first run, remembered in `.design-playbook/preferences.yaml` (version-controlled; per-machine overrides in gitignored `preferences.local.yaml`) |

</details>

## 🧩 Skills & commands

Nine skills in the package (`/design-playbook:<name>`):

| Skill | Role |
| :--- | :--- |
| `design-playbook` | 🎯 Orchestrator (full pipeline, run-profile tiering P1/P2/P3) |
| `design-baseline` | 🧭 Discover, validate, or draft project `DESIGN.md` before existing-product UI work |
| `reference-intake` | 📎 Reference contract (screenshot/URL/analogy → Keep/Change/Do not copy) |
| `ux-spec` | 📋 Six-layer spec declaration via the S0-S6 shaping session (question/assumption/confirmation batches + session artifacts) |
| `ui-picker` | 🧱 Shell + component semantics + design-decision entries (record / compare / explore tiers) |
| `craft-guard` | 🛡️ Detail-craft check — spacing, hierarchy, motion (anti-AI-slop) against the built-in rule registry |
| `native-craft` | 🖥️ Native-feel desktop declaration |
| `ui-evaluator` | ✅ Acceptance — every finding points back to its declaration; blocking ones recirculate |
| `component-distill` | Existing cross-run, report-only component/token promotion proposals; durable promotion requires a user decision. Not a single-run pipeline step |

**Eight commands:** `design-io` (full pipeline) · `ux-spec` (spec only) · `ui-review` (accept only) · `run-review` (cross-run) · `run-status` (phase + resume narration) · `run-handoff` (static delivery package for a reviewed run) · `doctor` (install health) · `component-distill` (cross-run proposals, no automatic promotion)

## 🎚️ Run profiles (P1/P2/P3)

Every run declares a tier in the `plan.md` **run-profile** block — process weight stays proportional to change consequence. Upgrades are automatic the moment a correction signal appears; downgrades need the user.

<details>
<summary>Tier matrix</summary>

| Tier | Scope | Gate face |
| :--- | :--- | :--- |
| **P1** point-fix | Single-owning-layer point-back repair, no decided-field touch | Registry subset evaluation; R4/R5 (+R2 line) routes |
| **P2** standard | In-baseline feature change (new criteria, R/C decisions) | Full predicate evaluation; shaping session + G9/G10 |
| **P3** full | Decided-field revision (supersedes), structural re-composition, E-tier decisions | G1-G12 full spectrum + sampling matrix fully executed |

</details>

Run-profile and re-entry decisions: [ADR-0029](./docs/adr/0029-vnext-closed-loop-final-state.md). Maintainer documentation: [Chinese documentation index](./docs/README.md).

## 🔌 Adapters (bundled)

Preview and Evidence MCP runtimes ship **inside** the main plugin
(`packages/design-playbook/mcp/` + `.mcp.json` with `${CLAUDE_PLUGIN_ROOT}`).
Marketplace install registers both tools with no second package; the
orchestrator still **probes** and skips steps when a host has no MCP tools.

| Adapter | MCP tool | Enables | Notes |
| :--- | :--- | :--- | :--- |
| `design-playbook-preview` | `preview_prototype` | `preview*` human confirm gate (G5) | Bundled; needs system Edge/Chrome for the popup (falls back to default browser) |
| `design-playbook-evidence` | `execute_capture_plan` | `observe*` runtime evidence (G6) — needs Playwright + Chromium | Bundled; capture still optional at runtime |

Docs: [preview](./packages/design-playbook-preview/#install--mcp-config) · [evidence](./packages/design-playbook-evidence/#install--mcp-config)

## 🌐 Install on other agents

```bash
npx design-playbook init <agent>
# or: python packages/design-playbook/scripts/generate_adapter.py <agent>
```

| Tier | Agents | What you get |
| :--- | :--- | :--- |
| **Tier 1** (native) | Claude Code, Codex | Full fidelity — skills, commands, MCP, drift-gated snapshots |
| **Tier 2** (generated) | Cursor, Gemini CLI, OpenCode, Windsurf, GitHub Copilot, Zed | Skills as platform rules + project-level MCP config; commands degrade to prompt docs. Zed: `.rules` (first-match aware — skipped if a competing rules file exists without one) + `.zed/settings.json` context_servers |
| **Tier 3** (floor) | 22 total, including Kiro, Amp, Jules, Qwen Code — `npx design-playbook --list` | `AGENTS.md` with orchestrator contract + MCP install guide |

Claude Code is the native surface. Tier-2/3 outputs are generated adapters with honest degradation. Current inventory: [adapter matrix](./packages/design-playbook/scripts/adapter_matrix.py); tier semantics: [ADR-0042](./docs/adr/0042-multi-platform-adapter-generator.md).

## 🔗 Stack with ecosystem

Not another style/palette pack — this plugin owns the **delivery pipeline, evidence semantics, and acceptance loop**, and composes with the rest:

| Package | Use for |
| :--- | :--- |
| **design-playbook** | Baseline? → Reference? → Spec? → plan? → shell → optional preview* → fill → craft → optional observe* → point-back |
| [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Style / palette / type search |
| `frontend-design` | Anti-template visual direction |
| [native-feel-skill](https://github.com/yetone/native-feel-skill) | Full native-feel depth (WebView, IPC, memory) |

## 🪞 Honest limits

- **Multimodality** — understanding screenshot content depends on the **host model's vision capability**. The plugin only *registers* images (locator + SHA-256 + metadata); a host without vision rides your text description instead.
- **Run Console** — shipped and **experimental**: a local, single-run console projecting existing run artifacts so an operator can see intent, source verdict, blocker source, and next owner without opening raw files — including a derived Repair Packet and an explicit `open-console` continuation from `run-status`. It stays **local and trial-gated** (no external authorization yet), is not a cloud Workspace, and never becomes a second run-state authority.
- **Packaging MCP config** — marketplace path includes package-local MCP runtime config; published registry packages may omit a root MCP config and need explicit host registration.
- **Console loopback on Windows** — local Console open uses loopback transport; dogfood saw a transport abort there, so do not treat loopback as a fixed-platform guarantee.
- **Proof vs. shape** — `scripts/validate_run.py` machine-checks the run-artifact *shape* and the closure trail; it does not claim every future run is automatically high-quality UI. Historical verdicts apply only to their recorded cases, not a current end-to-end run or a statistical guarantee.

## 📄 License

MIT (authored content). See [`LICENSE`](./packages/design-playbook/LICENSE) + [`NOTICE`](./packages/design-playbook/NOTICE). No rights claimed over any third-party playbook corpus.

Repo layout, maintainer scripts, and the engineering shell live behind the front door: [package README](./packages/design-playbook/README.md) · [docs/agents](./docs/agents) · [Contributing](./.github/CONTRIBUTING.md).

GitHub Issues are for user reports and feedback. Internal specs, plans, research,
and work tickets stay local and untracked; see the [issue policy](./docs/agents/issue-tracker.md).

Maintainers: [automated acceptance](./docs/agents/automated-acceptance.md) covers the required matrix and an extra-project operator replay. Its simulated review inputs are regression fixtures, not external trial evidence.

---

<div align="center">

[中文说明](README-zh.md) · [Showcase](./packages/design-playbook/showcase) · [Releases](./docs/releases) · [Workflow](./docs/agents/product-workflow.md)

</div>
