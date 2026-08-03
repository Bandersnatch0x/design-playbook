# Phase pointer

**Current:** **v0.9.1 released**（2026-08-03，patch，tag `779630a` on `release/v0.9.1`（cut from `a3d754c`，不含 v0.10 run-review）；GitHub Release：https://github.com/Bandersnatch0x/design-playbook/releases/tag/v0.9.1；npm `latest=0.9.1`）。本版 Fixed：evidence run-root WARNING 收窄（出厂默认恒触发假阳性 → 仅无 run 标记时、每进程一次）+ orchestrator step 9.2 `wait_for_state` async-init 指引。**渠道决策（ADR-0015，2026-08-03）：main = stable channel**——版本与可安装 inventory 恒等于最新正式发布；未发布能力留在 feature/release branch，经 release transaction（gate 全过 → 同一 commit 合 main + tag + 发布）才进 main。main 已由 corrective commit 恢复为 v0.9.1 inventory（3 commands、无 run-review）；v0.10 run-review 素材在 `feature/v0.10-run-review`（含 `.scratch/v0.10-run-review/` 决策记录）。v0.9 范围圆桌决议（2026-08-02，`.scratch/v0.9-cycle/roundtable-synthesis.md`）：repeat_blockers 不断言化（入场券 = 首次真实 repeat>0 并闭环，届时落 release.py）；doctor 与 aggregate 保持独立。3b community catalog 仍 **BLOCKED**（region + 账号）。

| Phase | Status |
| --- | --- |
| 0-setup | done |
| 1-grill | done (Q1–Q6, ADR 0001–0007) |
| 2-dogfood | done (001–006) |
| 3-to-spec | done |
| 4-to-tickets | done (01–08 全 resolved) |
| 5-implement | done (ADR-0006 + run seam: G5 preview* + G6 evidence*) |
| 6-polish | done (review fixes + run-seam product-surface sync) |
| 7-release | done (v0.2.0, 2026-07-17) |
| v0.3-grill | done (2026-07-18, 4 决策 + ADR-0008 floor enforcement 落地, SEAM TEST PASSED) |
| v0.3-to-spec | done (2026-07-20: Q3.1-Q3.4 + preview polish landed; v0.3.0 perfect release prep complete) |
| v0.3.1 | done (2026-07-20: dedup-single-source 5 票 + ADR-0010, shipped, tag v0.3.1) |
| v0.4-grill | done (2026-07-21: 决策 01-04 全 resolved, wayfinder `.scratch/v0.4-cycle/`) |
| v0.4-implement | done (2026-07-21: 按钮修复 d46682d + 007b 六 gate 全绿 + 3a/3c 落地 + pill 两步 arm 0a1dd33) |
| v0.4-release | done (v0.4.0–v0.4.2, 2026-07-21; gate5 install smoke PASS; 3b form region-blocked, paste pack ready) |
| v0.4.3–v0.4.4 | done (2026-07-21: preview P1/P2 polish + security-hardening G5 隔离/forged-POST 修复 + Codex install path; RUN_ROOT opt-in + known limitations) |
| secure-ship-0.4.4 | done (01-09 全 resolved; 02/03 G5 修复 da38edd; 05/09 codex_exec smoke PASS; 06 CI gate 落地; frontend floor follow-up) |
| v0.5.0 release | done (v0.5.0, 2026-07-22; pushed + GitHub Release) |
| v0.6.0 release | done (v0.6.0, 2026-07-24; design-baseline ADR-0012 + G5 LF hash; tag a065e7b pushed + GitHub Release) |
| frontend floor graduate | done (2026-07-25; required CI gate `29c80f3`; Ubuntu run `30165226282` green) |
| v0.6.0 gate 5 smoke | done (2026-07-25; isolated second-session marketplace install; plugin v0.6.0 + 2 MCP servers resolved) |
| Preview decision transaction | done (2026-07-26; tickets `01`-`04` resolved; implementation `94b2e64`; Ubuntu run `30183789524` green incl. exact frontend marker) |
| validate.py phrase table | done (2026-07-26; ticket `14` resolved; implementation `5d3733b`; Ubuntu run `30206845177` green) |
| craft detectors | done (2026-07-27; tickets `01`-`04` resolved; implementation `0d40450`; Ubuntu run `30210795805` green) |
| v0.7.0 release | done (v0.7.0, 2026-07-27; ADR-0013 preview transaction + ADR-0014 craft detectors + npm/pi surface; tag 1a3efba pushed + GitHub Release; npm publish design-playbook@0.7.0) |
| v0.8.0 release | done (v0.8.0, 2026-07-31; G5 hardening + Preview control resource split/adaptive theme + validation lockstep; tag 38d70fd pushed + GitHub Release; npm latest 0.8.0; isolated second-session install smoke PASS) |
| v0.9.0 release | done (v0.9.0, 2026-08-01; cross-run aggregate `run aggregate`/`repeat blocker` + architecture review landed (confirm cluster collapse + shared confirm-record parsing); tag `v0.9.0` pushed; tests 46+8+56 green; GitHub Release + npm publish 0.9.0; isolated second-session marketplace add + install smoke PASS (plugin 0.9.0, 8 skills, 3 commands, 2 MCP servers, 3 control resources, `claude plugin validate` green)) |
| v0.9.1 release | done (v0.9.1, 2026-08-03; patch cut from `a3d754c` on `release/v0.9.1` excluding v0.10 run-review; Fixed: run-root WARNING narrowed + wait_for_state guidance; release gate PASSED; tag + GitHub Release + npm 0.9.1; isolated second-session tag marketplace install + public npm artifact smoke PASS: plugin 0.9.1, 8 skills, 3 commands, 2 MCP servers, strict validate + both `tools/list` green; public main marketplace intentionally remains 0.9.0) |
| channel-restore (ADR-0015) | done (2026-08-03; stable main + gate-then-merge + stable docs 决策; main corrective commit 恢复 v0.9.1 inventory: 版本 0.9.1、3 commands、回补 release note; v0.10 run-review → `feature/v0.10-run-review`; OPP-01/OPP-21 tickets 落盘) |

## v0 ship checklist (5/5 pass)

- [x] CONTEXT + ADR 覆盖范围/许可/SSOT/仓形态（ADR 0001–0007）
- [x] package README 安装路径可复制
- [x] references 无上游特化残留（issue 01 resolved，rg 零命中）
- [x] ≥2 次 dogfood 过程门通过（004 + manual-provider G6 dry-run）
- [x] issues 全 resolved（01–08）

## Run seam (shipped, feat/design-io-run-seam)

- **G5** preview* — pre-Fill decision confirm, HITL, conditional on `preview_prototype` MCP adapter
- **G6** observe* — post-Fill criterion-addressable evidence, AFK, conditional on `execute_capture_plan` provider; manifest = only Contract/Runtime seam; capture ≠ judge
- 两套测试：`VALIDATION PASSED` + `SEAM TEST PASSED`
- PR #2：https://github.com/Bandersnatch0x/design-playbook/pull/2

## Architecture review (2026-07-17, archived)

`.scratch/architecture-review-20260717/map.md` — 4 候选经三方辩论 + 代码核验：#3 report_ref 三处（CUT，Explore 误判，server.py 无路径解析）、#4 Gate Protocol（CUT，issue 04 明文禁 G7 + 六 gate 签名不齐）、#1 manifest schema（DEFER post-v1，字段有意 prose-only 属 capture≠judge 边界）、#2 validate.py phrase-table（可选小做，bool guard 已防静默 false-pass）。**净结论：预 release 零代码改动**，run-seam 现状是健康的有意契约边界。

## Architecture review (2026-08-01, Preview 决策路径)

三候选全落地：`3514ccb` confirm 集群折叠（confirm.py 删除，helpers 归主）+ digest lockstep 测试（`tests/test_digest_lockstep.py`）；`ae8f294` 共享确认记录解析（`read_confirm_record` + `_g5_no_valid_reason` 入 `_preview_integrity`，validate_run 820→788 行）。`_transport.py` lockstep 审计：共享代码非复制，无风险。G6 证据路径复查（08-01）：净干净；**M6 containment parity 测试 CUT**——读侧（validate_run）与写侧（evidence/server.py `_resolve_artifact_path`）各自独立测试充分（写：test_provider_rejects_*_paths；读：g6-symlink-escape fixture），差异后果仅为诊断不对称非完整性违约，跳过与 07-17 先例一致。

## Dogfood (2026-08-01)

- tarot embossed card page: full Design I/O run in-session (ux-spec → ui-picker → preview* real HITL via Playwright → fill → craft-guard → observe* live-host captures → ui-evaluator). `validate_run` RUN OK, `run_status` Pass, aggregate gate ok. 3 findings all fixed (reduced-motion / live-host re-capture / run-root stderr warning in evidence server). Commits `ea7958d` + `08fd295`.
- event-stream monitor page + settings page: two more full Design I/O runs (`c2c92b9` + `16caf54`), both RUN OK, preview* real HITL (Playwright), observe* live-host captures. Settings run lesson: capture landed in the 700ms skeleton window — added `wait_for_state` async-init guidance to the orchestrator skill step 9.2 (`0fb50ab` + skill edit). Aggregate gate added to `validate.py` (`6944213`): 20 runs, repeat_blockers=0, rollup {blocked:3, pass:109}.

## v0.10 run review (2026-08-03)

- 圆桌决议落地：新 command `run-review`（第四 command，`.scratch/v0.10-run-review/` 四票全 resolved）。实现经 Orca 委托 grok worker（run `run_5bf575c510d8`），产物：`commands/run-review.md`（run-review/v1 契约 + 条件式 validate_run seam + repeat blocker 频次表 + 禁止块）、doctor GATE1 3→4、README/checklist/CI 同步、orchestrator pointer、`tests/test_normalize_lockstep.py`（shipped 文案 SSOT，aggregate_runs follower）。gate 独立复核全绿。待发 v0.10.0（Fixed 素材已先行随 v0.9.1 patch 发出，2026-08-03）。

## Still open（2026-07-25 刷新）

1. 3b community catalog：人工阻塞（region + 账号）

**Package commands (ship):** design-io · ux-spec · ui-review
**Monorepo commands (maintain):** product-next · product-grill · product-dogfood
