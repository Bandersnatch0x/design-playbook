# Phase pointer

**Current:** **v0.12.0 release prep ready (local, untagged)** — 2026-08-08. Versions bumped to **0.12.0** across plugin/npm/marketplace/README; `COMMAND_INVENTORY` has `(0, 12)`; release notes `docs/releases/v0.12.0.md`. Includes vNext (ADR-0016–0020, contract v1, G7, `run-status`/`doctor`) + preview Scheme A′ control interaction. Live dogfood `2026-08-08-vnext-live` **pass**. Local gates green. **Next:** commit(s) → `python scripts/release.py` dry-run → `--apply` tag only when user asks → push atomic + install smoke. **渠道决策（ADR-0015）：main = stable channel**；community catalog 仍为 **PAUSED BY USER**.

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
| v0.9.1 release | done (v0.9.1, 2026-08-03; patch cut from `a3d754c` on `release/v0.9.1` excluding v0.10 run-review; Fixed: run-root WARNING narrowed + wait_for_state guidance; release gate PASSED; tag + GitHub Release + npm 0.9.1; isolated second-session tag marketplace install + public npm artifact smoke PASS: plugin 0.9.1, 8 skills, 3 commands, 2 MCP servers, strict validate + both `tools/list` green; public main marketplace had remained 0.9.0 pre-ADR-0015 — see channel-restore row) |
| channel-restore (ADR-0015) | done (2026-08-03; stable main + gate-then-merge + stable docs 决策; main corrective commit 恢复 v0.9.1 inventory: 版本 0.9.1、3 commands、回补 release note; v0.10 run-review → `feature/v0.10-run-review`; OPP-01/OPP-21 tickets 落盘) |
| v0.9.2 release | done (v0.9.2, 2026-08-04; release-identity marker: 零可安装面变更（与 v0.9.1 逐字节一致，仅版本字段），标记 channel-restore + OPP-01/OPP-21 gate 硬化; release gate PASSED + 全套本地 suites 绿; tag `4cfda8a` + GitHub Release + npm 0.9.2 (shasum `c4150e9`); 二次会话 install smoke PASS，证据见 `evidence/gate5-install-smoke-v0.9.2-2026-08-04/result.md`) |
| v0.10.0 release | done (v0.10.0, 2026-08-04; fourth command `run-review` + `run-review/v1` markdown contract + normalize lockstep; explicit HTTPS install path; release commit/tag `aed0e87`; GitHub Release + npm latest 0.10.0 (shasum `b4b9b3b`); release gate + CI-equivalent suites + second-session public marketplace/npm smoke PASS，证据见 `evidence/gate5-install-smoke-v0.10.0-2026-08-04/result.md`) |
| v0.11.0 release | done (v0.11.0, 2026-08-07; local canvas named versions + `timeline()` / `state_at()` / `fork()` + anchor v2; hardened cross-process preview transactions and canvas undo; release commit/tag `34ef294`; CI run `31177155507` green; GitHub Release + npm latest 0.11.0 (shasum `04e2b75`); public marketplace/npm smoke PASS，证据见 `evidence/gate5-install-smoke-v0.11.0-2026-08-07/result.md`) |
| install smoke automation | done (2026-08-07; `scripts/install_smoke.py`: isolated Claude install + exact inventory + strict validate + real MCP handshakes + clean npm consumer; JSON/Markdown evidence; Windows console output encoding-safe; 12 deterministic tests + live smoke PASS, temporary cleanup verified) |
| v0.11.1 release | done (v0.11.1, 2026-08-07; canvas anchor focus fix; tag + npm + marketplace smoke) |
| vNext grill → tickets | done (2026-08-08; 5 open questions locked; ADR-0016–0020; `.scratch/design-playbook-vnext/` spec + 12 tickets) |
| vNext implement | done (2026-08-08; 12 tickets resolved on main; 5 feature commits after `0990250`; see Current) |
| vNext surface dogfood | done-partial (2026-08-08; packaged contract/G7/capture-parse/status/doctor/validate; log `dogfood/2026-08-08-vnext-surfaces.md`; live HITL/observe still open) |
| vNext live dogfood | done (2026-08-08; run `dogfood/2026-08-08-vnext-live`; real HITL confirm-round-2 + HTTP fill-host observe v1; G5/G6/G7 verify green; log `2026-08-08-vnext-live.md` verdict **pass**) |
| preview control A′ | done (2026-08-08; abort popover + clamp/trap/cancel, pill revise submit, quick feedback, Ctrl+Enter floor, Esc/outside disarm pill arm; floor S1–S25 + control markup tests green) |
| v0.12.0 release prep | in-progress (version surfaces + notes + inventory; tag/publish/smoke only on explicit ask) |

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

- 圆桌决议落地并随 v0.10.0 发布：新 command `run-review`（第四 command，`.scratch/v0.10-run-review/` 四票全 resolved）。实现经 Orca 委托 grok worker（run `run_5bf575c510d8`），产物：`commands/run-review.md`（run-review/v1 契约 + 条件式 validate_run seam + repeat blocker 频次表 + 禁止块）、doctor GATE1 3→4、README/checklist/CI 同步、orchestrator pointer、`tests/test_normalize_lockstep.py`（shipped 文案 SSOT，aggregate_runs follower）。release commit/tag `aed0e87`；GitHub Release + npm + second-session install smoke 全绿。Fixed 素材已先行随 v0.9.1 patch 发出（2026-08-03）。

## Still open（2026-08-04 刷新）

1. 3b community catalog：v0.10.0 提交包已刷新（`v0.4-cycle/community-catalog-checklist.md`），用户于 2026-08-04 暂停分发线；恢复时用可用认证账号提交并回填 ticket ID。

**Package commands (ship):** design-io · ux-spec · ui-review · run-review
**Monorepo commands (maintain):** product-next · product-grill · product-dogfood
