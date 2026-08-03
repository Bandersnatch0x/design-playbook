# Wayfinder map — v0.10 run review（跨 run 复盘能力回流进包）

Label: wayfinder:map

## Destination

让**插件用户**能对自己项目里的多次 Design I/O run（`.scratch/<run>/`）做跨 run 复盘。最小起步 = skill/command 指引 + 输出格式约定；**不搬 `scripts/aggregate_runs.py` 实现进包**（v0.9 圆桌决议，2026-08-02，`.scratch/v0.9-cycle/roundtable-synthesis.md`）。

## Notes

- 来源：v0.9 范围圆桌 Q4 决议——主线取"回流进包"，同时满足 tarball-diff 发版判据（发布工程）与"停止自产自销"（YAGNI）。
- 域纪律沿用：repeat blocker = 纯统计不下判断，"学习"仅以频次表存在；不新建 run ledger；不自动回流 baseline。
- 用户侧已有件：shipped `scripts/validate_run.py`（per-run seam）、`.scratch/<run>/` 产物约定（plan / spec / point-back / preview/ / evidence/manifest.jsonl）。
- 内部参照（不搬码）：`scripts/aggregate_runs.py` 的 JSON 形状（runs_total / rollup.by_result / repeat_blockers）与 normalized `observed` 归一化。
- 本主题构成 v0.10.0 的 minor 素材；随发时搭车带上已修的 run-root WARNING 收窄 + wait_for_state skill 指引（Fixed 段）。

## Decisions so far

<!-- One linked gist per resolved ticket. The full answer lives in that ticket. -->

- [01 落点](issues/01-surface-落点.md) — 纯 command：新建 `commands/run-review.md`，不新增 skill；orchestrator 一行 pointer；doctor 3→4。resolved 2026-08-03
- [02 输出契约](issues/02-contract-输出契约.md) — markdown 表 + `run-review/v1` 抬头，不发 JSON schema；point-back 逐字引用无行号。resolved 2026-08-03
- [03 计算主体](issues/03-compute-计算主体.md) — 保留 repeat blocker（用户拍板）；条件式 validate_run seam（`not checked` 兜底）；shipped 文案 SSOT + `test_normalize_lockstep.py` 锁 follower。resolved 2026-08-03
- [04 词汇](issues/04-vocabulary-对外词汇.md) — 对外 `run review`；`repeat blocker` 保留带定义；集中 `禁止:` 块四条。resolved 2026-08-03

## Frontier

四票全 resolved，实现已落地（grok worker，Orca run `run_5bf575c510d8`，2026-08-03）：`commands/run-review.md` + doctor/README/checklist/CI 枚举同步 + orchestrator pointer + `tests/test_normalize_lockstep.py`。本地 gate 复核全绿（59 pytest + validate + doctor）。剩余：随 v0.10.0 发布（连同 Fixed 段：run-root WARNING 收窄、wait_for_state 指引），发版走 release-checklist（7 版本位点 + npm publish）。

## Out of scope

- 不把 aggregate_runs.py 或其子集打进 tarball（决议明确"不搬实现"）。
- 不做跨 run 的 criterion 语义对齐（L6.n 编号 per-run/per-spec，v0.9 Q3 事实修正）。
- 不做自动"学习"/prose lessons/baseline 自动回写。
