# Wayfinder map — v0.9 cross-run aggregate

Label: wayfinder:map

## Destination

`scripts/aggregate_runs.py` — deterministic cross-run aggregate over `.scratch/**/dogfood/*/` runs: per-run rollup (artifact completeness + G5/G6 gate status) + repeat-blocker detection (normalized `observed` text frequency). JSON contract surface + markdown view. Grill Q1–Q5 locked (2026-08-01, `.scratch/design-playbook-v0/grill-notes.md`).

## Notes

- Domain vocabulary: `run aggregate` + `repeat blocker` (CONTEXT.md glossary, committed `ddb9740`).
- 不新建 run ledger；复用现有 enforce 产物（plan.md / point-back.md / evidence/manifest.jsonl / preview/）。
- Repeat blocker = 纯统计，不下判断；不得散文化（"学习"仅以频次表存在）。
- criterion `L6.<n>` 编号 per-run/per-spec → 跨 run 语义对齐不做（Q3 fact correction）。
- 落点 repo-root `scripts/`（run_status 同族，维护工具非发布面）；validate_run 子进程供 G5/G6 门状态。

## Decisions so far

<!-- One linked gist per resolved ticket. The full answer lives in that ticket. -->

- [01 run discovery + skeleton](issues/01-run-discovery.md) — default scan `.scratch/**/dogfood/*/` with `point-back.md` marker; `--runs` override. resolved 2026-08-01 (`2987c88`)
- 02–05 (rollup / repeat-blocker / JSON / markdown) + 06 (fixture + real-scan tests) all resolved 2026-08-01 (`2987c88`). Real scan: 17 runs, 88 pass / 3 blocked ledger rows, repeat blockers = 0 (no systemic defect pattern — healthy seam signal).
