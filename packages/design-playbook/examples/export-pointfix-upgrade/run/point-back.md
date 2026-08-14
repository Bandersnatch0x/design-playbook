# Point-back — 空数据集导出修复 + 列范围升档（P1 定档，E5/E1 升档 P2 重走）

Six-block report (final state). Intake P1 (single R4 blocking, zero expected declaration touch). Round 1: R4 修复空数据集防护 + invalidated 重采 → closure。评审走查同时出现无主发现（用户「只导出选中列」请求，R1/E1）→ 用户裁决新增判据 `l6.c4` → 契约 diff（bind 后新增判据）越出 P1 面（E5）→ 升档 P2（run-profile upgrades 记录）：补开增量成形会话（G9）、补 R 档决策 DD-0101（G10）、已产工件保留。S4 演示：G12 越界发现 + E1/E5 纠偏信号 + 升档重走叙述。

## Evidence ledger

```text
criterion: L6.1
required:  Given 运营在主列表选定上周范围 When 触发行内批量导出 Then 30 秒内获得 CSV 且行数与选中范围一致（证据：交互记录）
observed:  evidence/L6.1-export-trace.json 14.2s 完成，214/214 行；空数据集防护修复后 evidence/L6.1-empty-r2.png 前置校验提示明确
result:    pass
note:      method=runtime-observation; scope=单次运行, viewport 1280x800, 数据集 week-2026-32
```

```text
criterion: L6.2
required:  Given 选定范围超过 20 万行 When 确认导出 Then 提示剩余量与收窄建议（证据：错误态截图 capture seed）
observed:  evidence/L6.2-cap-error.png 提示含「超出 200,000 行上限」与「按周导出」建议（上轮 r2 证据保持，本轮未触碰）
result:    pass
note:      assumes=export.row_cap
```

```text
criterion: L6.3
required:  Given 导出进行中 When 用户离开并返回该页 Then 导出进度与结果仍可获知（证据：交互记录）
observed:  evidence/L6.3-return-trace.json 返回后 exporting 态可见、完成后结果可见（上轮证据保持，本轮未触碰）
result:    pass
note:      method=runtime-observation
```

```text
criterion: L6.4
required:  Given 运营在主列表圈选 2 列 When 触发行内导出 Then CSV 仅含圈选列且顺序与列表一致（证据：交互记录）
observed:  evidence/L6.4-column-trace.json CSV 仅含圈选 2 列且顺序一致（升档 P2 后新增判据首评）
result:    pass
note:      method=runtime-observation; scope=单次运行, viewport 1280x800；判据经 D-0101 用户确认
```

## Findings

```text
issue:    空数据集导出无反馈且不产出文件
source:   spec L6.1 + components
fix:      空选择/空数据集导出前置校验：提示「无可选行」并禁用触发；补 L5 空态行
severity: S3
track:    product
confidence: high
disposition: blocking
route:    R4
rounds:   1
evidence:  evidence/L6.1-empty-r1.png（首轮：点击导出后无任何反馈、无文件产出）
```

```text
issue:    导出面板空数据集行为未声明（L5 空态行缺失）
source:   spec L5
fix:      L5 行级补行：export-dialog/empty 空数据集前置校验提示（已声明段内，无新增 L6 顶层项）
severity: S1
track:    interaction
confidence: high
disposition: advisory
route:    R2-line
evidence:  evidence/L6.1-empty-r2.png（补行后行为与声明一致）
```

```text
issue:    「只导出选中列」用户请求为无主发现——契约/spec 无对应声明
source:   spec L1（无对应声明可指）
fix:      不在评审现场发明产品要求：呈报用户裁决 → 新增判据 l6.c4（D-0101）；E1 复核 + E5 越界 → 升档 P2 重走（W10）
severity: S2
track:    product
confidence: high
disposition: advisory
route:    R1
evidence:  走查记录（用户请求原文）+ decisions.jsonl D-0101
```

## Positive findings

```text
issue:    空数据集防护与列范围导出闭环在评审面内全部通过
source:   spec L6.1 + L6.4
fix:      无需修复——正向观察；AC 级正向即 ledger pass 行，此处汇总引用
severity: S0
track:    product
confidence: high
disposition: info
evidence:  evidence/L6.1-empty-r2.png + evidence/L6.4-column-trace.json
```

## Coverage statement

必审: 失效集（L6.1 空态防护 + 相邻主路径节点）+ 新判据 L6.4 首评 4/4 完成
采样: 空数据集导出（R4 修复项，r2 证据通过）
未审: 移动端视口（契约未声明目标视口）；超大数据集中断重试（本轮无修复面）

## Limitations statement

- 用户代表性：本 run 无 user-test 证据，全部结论不构成任何「用户会」断言
- pass 范围：L6.1-L6.4 pass 限单 viewport 1280x800 / 单数据集 week-2026-32 / 单次运行
- assumed 依赖：L6.2 pass 依赖 export.row_cap 假设成立
- 升档记录：E1/E5 -> P2（run-profile upgrades；增量成形会话与 R 档决策已补走，已产工件保留）
- 机器面证明声明与事实一致，不证明体验良好

invalidated:
  - criterion: L6.1
    artifacts: [evidence/L6.1-empty-r1.png]
    reason: R4 修复空数据集防护后 observed UI 变化，重采 r2 空态证据（最新 manifest 条目胜）
    round: 1

## Verdict

**Pass.**

- closes: 空数据集导出无反馈且不产出文件 -> recirculate -> fix -> re-eval -> 0 blocking

close_reason: pass
