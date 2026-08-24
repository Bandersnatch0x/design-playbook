# Phase pointer

**Current:** **v0.20.2 released + three unreleased workstreams in flight** — 上次发布 2026-08-16（tag `v0.20.2`；npm `latest` = `design-playbook@0.20.2` / `dsh-design-playbook@0.20.2`；[GitHub Release](https://github.com/Bandersnatch0x/design-playbook/releases/tag/v0.20.2)）。此后有三条并行工作流尚未发布，见下表末三行。**渠道决策（ADR-0015）：main = stable channel**；community catalog 仍为 **PAUSED BY USER**.

> 登记规则：v0.20.2 之后的每条工作流都必须在下表有一行，否则本文件无法用于判定范围内外（CLAUDE.md 第 4 条把本文件定为阶段权威）。

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
| vNext ui/ux closed loop | done (map #23 十票全关 → S1-S6 六切片 PR #42 → 双轨评审 Pass 0 blocking → v0.20.0 released, 2026-08-15; spec: docs/specs/ui-ux-vnext/) |
| adaptive routing + reference sources (#80) | shipped-unreleased (2026-08-21, `4bb7fda`; ADR-0032; spec `docs/specs/2026-08-17-adaptive-routing-reference-inputs-design.md`; `7ff2546` 为其孤儿资产回滚补丁) |
| audit preferences (#81) | shipped-unreleased (2026-08-19, `d82f111`; ADR-0033; issues #65/#67/#69; `scripts/audit_preferences.py` + validate_run AUDIT.* + 4 测试文件) |
| Stage 6/9 interactive review + static handoff (#36) | in-progress (spec `docs/specs/2026-08-22-...-implementation-plan.md`；分支 `feature/preview-skip-dock`，工作树未提交；Stage 6 约 85% 落地，Stage 9 挂错生命周期 → **ADR-0034** 定归属，解耦为 follow-up；两轴评审结论见下节) |

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

## Two-axis review of #36 (2026-08-24)

Standards 轴 + Spec 轴对 v0.20.2..工作树全量变更（83 文件）各跑一遍。**已修**（本轮，全量 pytest 绿 + `VALIDATION PASSED`）：

- 交付凭证自建 confirm 判定，绕过 ADR-0008 floor —— 空反馈确认时 `transaction.py` 记 `confirmed=false` 而凭证发 `Pass`/`confirmed-user`。改为读 `confirm-round-*.json`（ADR-0034 §3），读不到即 fail-closed 并写明 `confirmationSource`。
- `.gitignore` 的 `.stitch` 反选失效（`!.stitch/` 把整目录重新纳入），20 个设计草稿会被提交；`.agents/` 整目录忽略压住了 ADR-0009 发布面。两处规则改为逐级排除/反选。
- `resolved` 标记在提交瞬间蒸发：`anchorSnapshot()` 保留而 `syncHidden()` 丢弃，服务端也不解析。
- E2E 全套挂死 30 分钟：v9 onboarding 全屏遮罩吞掉 `frame_locator` 点击且不报错，driver 永不 POST → `done.wait(1800)`。三处 dismissal 合并为 `tests/preview_e2e_helpers.py` 单一副本。
- `test_floor_frontend.py` / `test_pin_bridge_frontend.py` 是 main() 风格、无 `test_*`，**从未被 pytest 收集**（后者的 v9 改写从未验证过）。已补入口 + `validate.py` 新增 "test executability" 门禁防复发。
- 其余：`SKIP_LABELS` 前端硬编码（违反 ADR-0008 单一标签源）、`profile` 硬编码 `P2-Standard` 谎报运行档位、ZIP 缺 spec §4.1 承诺的原型代码、`DESIGN_PLAYBOOK_RUN_ROOT` 压过原型实际位置、iframe 内涂鸦描边与 token/虚线不符、`validate.py` 漏检 `control.review.js`、7 个新测试未接入 CI、ADR-0022 引用错配。

**ADR-0034 follow-up（2026-08-24 落地，issue #85–#93）**：Stage 9 已从 Preview 解耦到 Evidence 侧构建器 `mcp/evidence/handoff.py`（`build_static_handoff`），生命周期与审查轮次无关，产物落 run 树 `evidence/static-handoff/`；`review_session.py` 2079 → 1192 行，只剩 Stage 6；截图目标改为 Stage 7 交付物 `filled-ui.html`（#87）；交付页改为包内自有零 CDN 内容 `mcp/evidence/static_handoff_page.html`（#88）；条件门禁引入第四态 `not-applicable`，`gatesPassed` 只计「已求值且通过」，G6 前置条件以 `evidence/manifest.jsonl`（而非裸 `evidence/` 目录）为准并在写产物前采样，避免构建器自造前置条件（#89）；新增构建器测试套件 `mcp/evidence/test_handoff.py`（20 用例全绿）。spec #36 的 7 处偏离记入该文档新增 §0 实施修订记录（A1–A7，含 #90 confirm 契约回改 spec、#92 Stage 10 归档收窄、#93 文本纠错含 G8 标签）。

**收尾**：`review_session.py` 2079 → 503 行，按内聚度拆为 `review_session.py`(503，会话状态机+页面装配+HTTP handler) / `owned_browser.py`(278，`BrowserInteraction` seam + 进程回收) / `pin_bridge.py`(450，注入的 `BRIDGE_SCRIPT` 及其 G5 信任边界契约)，旧导入路径经 re-export 全部保留；`capture_runtime.py` 两条重复 Playwright 路径并入私有 `_capture_page(..., probe: bool)`，`capture()` / `capture_and_probe()` 退化为薄包装且签名不变（#91 + 标准轴 M2）。产品内入口补为 orchestrator step 11「Static run handoff」（可选、按需，不参与验收判定）。

**验收**：全量 `pytest packages/design-playbook` = **353 passed + 97 subtests**（含此前排除的 `test_e2e_canvas_vc.py` 7 项）· `scripts/validate.py` = **VALIDATION PASSED** · `test_handoff.py` 20/20 · 真实 Playwright 端到端冒烟在无 confirm 记录的 run 上诚实输出 `Pending` / `unsubstantiated` / 4 项 `not-applicable`。issue #85–#93 全部关闭。

> ~~在上述 follow-up 落地前~~ `disclosure-review.json` 的 `gatesPassed` / `verdict` 现已可采信：确认状态由 `authority` / `verdict` / `confirmationSource` 承载，`gatesPassed` 只反映已求值通过数，交付判定看 `gatesResolved`（全部 `pass` 或 `not-applicable`）。

## Still open（2026-08-04 刷新）


1. 3b community catalog：v0.10.0 提交包已刷新（`v0.4-cycle/community-catalog-checklist.md`），用户于 2026-08-04 暂停分发线；恢复时用可用认证账号提交并回填 ticket ID。

**Package commands (ship):** design-io · ux-spec · ui-review · run-review
**Monorepo commands (maintain):** product-next · product-grill · product-dogfood
