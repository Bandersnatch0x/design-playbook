# Phase pointer

**Current:** **v0.4.4 shipped**（2026-07-21，security-hardening：G5 iframe+token 信任边界隔离、forged-POST 修复、Codex marketplace install path）。**`secure-ship-0.4.4` 周期全部 9 票 resolved**（01-09）：02/03 G5 安全绕过修复（BYPASS-1/2 + TOCTOU + fail-closed，`da38edd`）+ 05/09 codex_exec smoke PASS（env_vars 透传运行时证实）+ 06 CI required gate（Preview/Evidence stdio + Playwright 策略，已落地全套件验证绿）。HEAD 领先 tag **10 个未发布 commit**（含 02/03 修复 + regression hotfix + ci 注释）→ 下一版按 semver 为 **v0.5.0**。frontend floor graduate 作为 follow-up（需 capture 组先在 CI ubuntu 验证绿）。3b community catalog 仍 **BLOCKED**（region + Claude 账号 on hold/`account_banned`；粘贴包见 `community-catalog-checklist.md`）。上一里程碑:v0.4.2（2026-07-21）。

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

## Still open（2026-07-22 刷新）

1. v0.5.0 发版：10 个未发布 commit（02/03 G5 修复、regression hotfix、reference-intake、ci 注释）；bump 一次改全 5 处版本位
2. frontend floor graduate（follow-up）：先 push 让 Evidence capture 组在 CI ubuntu 验证绿，再 graduate `test_floor_frontend.py`
3. 3b community catalog：人工阻塞（region + 账号）

**Package commands (ship):** design-io · ux-spec · ui-review
**Monorepo commands (maintain):** product-next · product-grill · product-dogfood
