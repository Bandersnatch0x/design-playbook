# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` — never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` — the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.

## Active product effort

- v0 (mostly done): `.scratch/design-playbook-v0/` (see `docs/agents/product-workflow.md`).
- **Wayfinder elevate:** `.scratch/elevate-structure-install-skills/` — map `map.md`; structure/install/skill-workflow。决策 **Clear**；implement 01–05 landed，06 release gate 余 human 步骤（remote/tag/smoke）。
- **Wayfinder pipeline-plan-preview:** `.scratch/pipeline-plan-preview/` — map `map.md`; plan 前移 + preview 循环 + G5。**Clear** + implement handoff 落地（skill/G5/adapter/CONTEXT/dogfood）。
- **Wayfinder criterion-addressable-evidence:** `.scratch/criterion-addressable-evidence/` — map `map.md`; post-Fill 运行取证（capture plan / manifest / provider / G6）。决策 **Clear**（2026-07-16）；implement **Clear**（2026-07-17）：G6+fixtures+step 8+词汇 + optional `packages/design-playbook-evidence/`；dogfood 004/005。
- **Wayfinder dx-feedback-triage (2026-07-19):** `.scratch/dx-feedback-triage/` — map `map.md`; 外部 DX 反馈 6 项逐条核查（裁决表在 map Notes）+ 5 张决策票（README 冷启动 / 运行可见性 / 组合优先级 / showcase 扩量 / 契约版本 defer），01 README 冷启动 + 02 运行可见性 + 03 组合优先级 已 resolved（01 徽章随落 0.2.2；01 Q2/Q3 + 02 + 03 全 handoff implement；04 v0.3 仅前向声明、扩量 defer v0.4），05 契约版本 defer（+非-gate 法医标记）。**全 5 票 resolved，effort 收尾**（handoff v0.3 implement；徽章 0.2.2 已落）。
- **Architecture review (2026-07-17):** `.scratch/architecture-review-20260717/map.md` — run-seam architecture review; 4 候选（manifest schema / validate.py grep / report_ref 三处 / Gate Protocol）经三方辩论 + 代码核验 → 2 CUT、1 DEFER、1 可选小做；**净结论：预 release 零代码改动**，run-seam 现状是健康的有意契约边界。reopen 触发条件见 map.md。
