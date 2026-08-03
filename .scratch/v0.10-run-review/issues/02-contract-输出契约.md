# Ticket 02-contract — 输出格式约定

Type: decision
Status: resolved
Resolved: 2026-08-03 (roundtable synthesis)

markdown 表为主、不发 JSON schema；抬头 `run-review/v1`（一行溯源标签，`design-baseline/v1` 先例；不承诺可执行契约）。与 aggregate_runs 只对齐列名/键名不对齐结构。逐 run 行强制 run-path 列；repeat blocker 段纯频次表 `count | runs | observed text`，无"分析/建议"格子；point-back = 路径 + `observed:` 逐字引用、不写行号。
