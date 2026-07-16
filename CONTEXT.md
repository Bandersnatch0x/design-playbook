# CONTEXT — design-playbook

Domain glossary and product facts for agents. Updated by `/grill-with-docs` / `/domain-modeling`.

## Product

**design-playbook** — Claude Code / Codex **plugin** that runs **Design I/O**: declarations + contracts so UI generation is constrained, reviewable, and recirculatable.

No reading-demo app in-repo (removed). Product surface is the installable package only.

## Glossary

> Evidence exists only to satisfy a declared criterion.
> Providers never produce evidence directly; they produce artifacts that become evidence only when bound by a manifest to a criterion.

| Term | Meaning | Avoid |
| --- | --- | --- |
| **Design I/O** | Pipeline: `ux-spec? → plan? → (native-craft?) → ui-picker → (preview*) → fill → craft-guard → (observe*) → ui-evaluator` | “just prompt better” |
| **Declaration** | What good is: spec, domain, craft, design, components, template | “guidelines”, “vibes” |
| **Contract** | How work enters the pipeline: skill timing, evaluator acceptance | “prompt pack” alone |
| **Closed-loop run** | One Design I/O run that declares the outcome, proves each success criterion, points failures back to their owning declaration, recirculates blocking findings within a bounded retry policy, and stops with an explicit verdict | “generated a page” / “looks done” |
| **Run contract** | The five controls fixed before execution: Goal, Success, Evidence, Stop, Confirm | an open-ended task list |
| **Evidence ledger** | Criterion-shaped acceptance record: required proof, observed proof, and pass/fail/blocked/N/A result for every success criterion | an unstructured review summary |
| **Evidence** | Criterion-addressable artifact: a runtime capture bound by a manifest to an L6.<n>; no criterion → telemetry, not evidence | "observation", "screenshot", an unbound artifact |
| **Recirculate** | Send a failure back to the owning declaration, then resume | blind whole-page restyle |
| **Point-back** | Evaluator finding names `source` declaration + `fix` | “looks off”, “polish more” |
| **Decision report** | ui-picker output before code: scene, template, components, risks | coding from intuition |
| **plan (step)** | Orchestrator-only handoff (`.scratch/<run>/plan.md`): run scope pointers, description→spec map, ui-picker input pack; not a run-contract control and not a machine gate | host Plan Mode; pre-written decision report |
| **preview*** | Optional disposable HTML prototype loop via external MCP tool `preview_prototype`; skip when adapter absent | fill from prototype files; ui-picker step 5 |
| **observe*** | Optional post-Fill runtime-evidence loop via external MCP tool `execute_capture_plan`; provider produces artifacts, orchestrator binds them to L6 criteria via manifest; skip when provider absent | building a runtime/dev server; provider writing the manifest |
| **Capture Plan** | Derived, disposable: L6 Given/When → state+actions, Then → required; never a SSOT, never edited for intent; L6 wins on conflict | a standalone test script; a persisted plan file |
| **Manifest** | Execution-record SSOT (`.scratch/<run>/evidence/manifest.jsonl`, append-only): self-contained entries binding criterion ↔ artifact; the only seam between Contract and Runtime objects | provider output; an editable log |
| **Provider** | Runtime executor of a capture plan; produces artifacts, never evidence; probed via `tools/list` for `execute_capture_plan`; Playwright MCP / manual / future | collector; judge; a criterion-aware tool |
| **G5** | Conditional `validate_run.py` gate: if preview occurred, require `confirm-round-*.json` with `confirmed=true` and matching `report_ref` | always-on preview gate; scanning Fill source for confirm refs |
| **G6** | Conditional `validate_run.py` gate: if a ledger `observed` references an `evidence/` artifact, require the artifact to exist and a manifest entry to bind it to the matching L6.<n> | always-on evidence gate; scanning Fill source; judging pass/fail from the manifest |
| **Blocking** | Acceptance failure that must recirculate (L5/L6, unsafe ops, …) | optional polish |
| **Dogfood** | Run Design I/O on a real UI ask to test *process*, keep answer not demo code | shipping the throwaway page |
| **SSOT** | Single source of truth for a declaration snippet | dual-edit attachments + references |
| **Native-feel** | Desktop app indistinguishable from native; render-surface seam + native conventions; declared by `native-craft` | “theme Electron”, “web page in a window” |

## Decisions (grill)

- **First user (v0):** public install — strangers install via marketplace/documented path; distribution + license posture are in-scope for ship.
- **Success (v0 run):** L5/L6 `spec` → decision report before code → point-back accept → recirculate blocking; plus install docs strangers can follow.
- **Scope shape (v0):** cut style CSV DB, multi-platform CLI, Figma-as-dependency, demo redesign-as-delivery; **add** license boundary, copy-paste install, clean self-authored examples, stack-with-ecosystem README, craft-guard dogfood.
- **License surface (v0):** public plugin may redistribute **only** our authored skills/commands/workflow/install docs + **self-written** examples. Upstream manuscript, figures, ACD marks, demo chrome, and unre-written `public/attachments` are **not** the plugin ship claim (demo may stay local learning copy with rights notice).
- **SSOT (v0):** declaration snippets live only under `packages/design-playbook/skills/*/references/*`. **Reference ≠ port:** inspired by Design I/O ideas, not an overlay/migration of any upstream playbook corpus.
- **Repo shape (v0):** product package `packages/design-playbook/`; demo site removed; root holds docs/scratch/workflow only (ADR-0005).

## Non-goals (v0)

- Competing with ui-ux-pro-max style databases
- Multi-agent-platform install CLI
- Figma MCP as a required delivery path
- Treating demo-site visuals as the release artifact

## Layout

| Path | Role |
| --- | --- |
| `packages/design-playbook/` | Public plugin product |
| `packages/design-playbook-preview/` | Optional Preview MCP adapter (`preview_prototype`); independent install |
| `packages/design-playbook/skills/` | Skills SSOT |
| `docs/agents/` | Tracker + product workflow |
| `.scratch/` | Specs, tickets, dogfood logs |
| `docs/adr/` | Decisions |

## Active effort

- v0 polish: `.scratch/design-playbook-v0/phase.md` + `docs/agents/product-workflow.md`
- **Elevate (wayfinder):** `.scratch/elevate-structure-install-skills/map.md` — structure, install, skill workflow decisions (plan-only until map clears)
- **Pipeline plan+preview (implement):** `.scratch/pipeline-plan-preview/map.md` — map **Clear**；skill 序列 + G5 + optional `packages/design-playbook-preview/` landing in progress
- **Criterion-addressable evidence (wayfinder→implement):** `.scratch/criterion-addressable-evidence/map.md` — observe\* 缝 + G6 + manifest//provider 契约；map **Clear**（2026-07-16），转 implement（G6 代码 + step 8 文案 + 词汇）
- **Criterion-addressable evidence (wayfinder):** `.scratch/criterion-addressable-evidence/map.md` — post-Fill 运行取证契约：capture plan（derived）/ manifest（execution SSOT）/ provider 二分 / G6（plan-only until map clears）
