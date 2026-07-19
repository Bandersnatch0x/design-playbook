# Phase pointer

**Current:** v0.3 grill — 4 决策 locked（Q3.1–Q3.4）+ ADR-0008 floor enforcement **已落地**（2026-07-18，6 sites + SEAM TEST PASSED）。Grill 可收尾,下一阶段 v0.3-to-spec。上一里程碑:v0.2.0 released（2026-07-17，PR #2 merged f641a1d + tag on main，全部 gate 闭合）。

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

## Still open (human, pre → formal release)

1. ~~Handoff #7: 真 provider 端到端 dogfood~~ ✅ 票 10 resolved（真 Claude Code MCP host 006 + 可移植复跑 007；日志 `dogfood/2026-07-17-006-real-provider-observe.md`）
2. ~~Handoff #8: manual provider dogfood 日志~~ ✅ 票 09 resolved（`dogfood/2026-07-17-005-manual-provider-observe.md`）
3. ~~门 5: 第二机/会话 install smoke（票 11）~~ ✅ 票 11 resolved（worker `term_1635c607` 干净会话走公开 install trio 全 4 步过；coordinator 独立核验 on-disk 6 skills + 3 commands；证据 `evidence/ticket-11-install-smoke/result.md`）
4. bump version + `git tag vX.Y.Z` + PR #2 merge（票 12，无 blockers；tag 不可逆，人裁决）

**Package commands (ship):** design-io · ux-spec · ui-review
**Monorepo commands (maintain):** product-next · product-grill · product-dogfood
