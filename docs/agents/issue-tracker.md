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

- v0 (mostly done): `.scratch/design-playbook-v0/` (see `docs/agents/product-workflow.md`). v0.3-to-spec done. Perfect v0.3.0: button flows, tests, wayfinder clean.
- **Wayfinder elevate:** `.scratch/elevate-structure-install-skills/` — map `map.md`; structure/install/skill-workflow。决策 **Clear**；implement 01–03 + partial 04-06 landed (verified layout/docs match; map updated). 06 human steps noted. All handled.
- **Wayfinder pipeline-plan-preview:** `.scratch/pipeline-plan-preview/` — map `map.md`; plan 前移 + preview 循环 + G5。**Clear** + implement handoff 落地（skill/G5/adapter/CONTEXT/dogfood）。
- **Wayfinder criterion-addressable-evidence:** `.scratch/criterion-addressable-evidence/` — map `map.md`; post-Fill 运行取证（capture plan / manifest / provider / G6）。决策 **Clear**（2026-07-16）；implement **Clear**（2026-07-17）：G6+fixtures+step 8+词汇 + optional `packages/design-playbook-evidence/`；dogfood 004/005。
- **Wayfinder dx-feedback-triage (2026-07-19):** `.scratch/dx-feedback-triage/` — map `map.md`; 外部 DX 反馈 6 项逐条核查 + 5 张决策票。**全 resolved + implement landed (preview control bar button flows, draft, direct-confirm, S10-S15b tests; ticket 01 Try-it/adapters/micro-fixes; ticket 02 skip narration/artifact pointers/G1-G4 prefixes)。Effort closed 2026-07-20.**
- **Wayfinder dedup-single-source (2026-07-20):** `.scratch/dedup-single-source/` — map `map.md`; v0.3.0 硬化/bundled MCP（ADR-0009）遗留的 5 项去重/单源判断题。**全 5 票 resolved + implement landed，v0.3.1 shipped：01 抽 `mcp/_transport.py`、02 边界成文（release-checklist Validation surfaces）、03 run_status↔SKILL 双向指针、04 sibling README MCP 配置→指针、05 launcher 时间盒政策（v0.5 评估）。Effort closed 2026-07-20。**
- **Wayfinder v0.4-cycle (2026-07-20):** `.scratch/v0.4-cycle/` — map `map.md`; v0.4 四主题范围（完整链路演示 + input/navigation 扩展(ADR-0010 P1/P2) + 基础设施/分发 + launcher 评估提前）。**in progress，frontier 主题 1（演示）优先——堵 dx-feedback 04 缺口 + 无依赖。**
- **Wayfinder secure-ship-0.4.4 (2026-07-21):** `.scratch/secure-ship-0.4.4/` — map `map.md`; 复审报告(`cdd12f9`)判定 Recirculate，destination=安全发 0.4.4，scope=A+B 桶全修(C/D 延后)。9 票：01-07 代码层全实现（commits 09efda0 主体 / 072f259 MEDIUM-1 真修复 / bef9f3a bump 不 tag）+ 最终评审（code-review WARN 无 CRITICAL、security APPROVE WITH CHANGES）。**05 实测推翻"删 RUN_ROOT 充分"假设**（codex `cwd:"."` 锚 plugin cache root）-> 05 blocked、开 08 research（codex MCP roots 支持？，**已 resolved：不支持**，源码+二进制双重证伪）+ 09 实现（**改 env 变量方向**，08 已解 unblocked）。**0.4.4 代码完成但不发版**，等 09 + smoke 通过才 apply tag。
- **Architecture review (2026-07-17):** `.scratch/architecture-review-20260717/map.md` — run-seam architecture review; 4 候选（manifest schema / validate.py grep / report_ref 三处 / Gate Protocol）经三方辩论 + 代码核验 → 2 CUT、1 DEFER、1 可选小做；**净结论：预 release 零代码改动**，run-seam 现状是健康的有意契约边界。reopen 触发条件见 map.md。
