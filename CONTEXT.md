# CONTEXT — design-playbook

Domain glossary and product facts for agents. Updated by `/grill-with-docs` / `/domain-modeling`.

## Product

**design-playbook** — Claude Code / Codex **plugin** that runs **Design I/O**: declarations + contracts so UI generation is constrained, reviewable, and recirculatable.

No reading-demo app in-repo (removed). Product surface is the installable package only.

## Glossary

| Term | Meaning | Avoid |
| --- | --- | --- |
| **Design I/O** | Pipeline: plan → shell → fill → craft → accept, with inject/check/recirculate | “just prompt better” |
| **Declaration** | What good is: spec, domain, craft, design, components, template | “guidelines”, “vibes” |
| **Contract** | How work enters the pipeline: skill timing, evaluator acceptance | “prompt pack” alone |
| **Recirculate** | Send a failure back to the owning declaration, then resume | blind whole-page restyle |
| **Point-back** | Evaluator finding names `source` declaration + `fix` | “looks off”, “polish more” |
| **Decision report** | ui-picker output before code: scene, template, components, risks | coding from intuition |
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
| `packages/design-playbook/skills/` | Skills SSOT |
| `docs/agents/` | Tracker + product workflow |
| `.scratch/` | Specs, tickets, dogfood logs |
| `docs/adr/` | Decisions |

## Active effort

- v0 polish: `.scratch/design-playbook-v0/phase.md` + `docs/agents/product-workflow.md`
- **Elevate (wayfinder):** `.scratch/elevate-structure-install-skills/map.md` — structure, install, skill workflow decisions (plan-only until map clears)
