# Decision report (数据导出入口)

ui-picker output before code. R/C 档决策以顶块记录结论；DD 条目块（S2 起）追加在顶块之后，记录各档义务（G10 校验）。

```text
scene: ops console data export
density: console-tight
template: toolbar + table + bounded dialog
regions:
  toolbar: row-selection actions (batch export primary)
  table: last-week data with stable comparison columns
  dialog: export options (column scope, format)
  toast: page-level notices (cap limit, export done)
components:
  batch export -> Button (single primary; busy state while exporting)
  column scope -> Checkbox group inside dialog
  cap notice -> toast with role=alert and readable name (includes cap value)
  list -> Table (not card wall)
risks:
  - repeated trigger during export -> busy + disabled while in flight
  - cap-limit notice invisible to screen readers -> role=alert + name (fixed this run)
  - hidden sensitive columns -> export.column_scope assumption acknowledged
```

Do not start implementation until this report exists (or the user explicitly skips).

## DD-0001 — 导出触发控件形态

R 档直录：单一合理选择，不比较、不问用户（基线内小选择永不触发完整探索）。

```yaml
id: DD-0001
tier: record
question: 导出触发控件形态
status: confirmed-agent
constraints:
  baseline: waived: 本 run 未绑定 DESIGN.md（示例项目无基线）
  spec: [l4.export-trigger]
selection: {candidate: Button (icon + label), rationale: 组件角色表「批量主行动」唯一合理形态；密度跟随 console-tight 段}
confirmation:
  kind: agent
  via: agent-record
  confirmed_at: 2026-08-14T10:16:00Z
supersedes: null
```

## DD-0002 — 导出文件命名模式

C 档轻量比较：基线内两案，代理自主 + 记录取舍（Q7 决策权表第 4 行，不问用户）。

```yaml
id: DD-0002
tier: compare
question: 导出文件命名模式
status: confirmed-agent
constraints:
  baseline: waived: 本 run 未绑定 DESIGN.md（示例项目无基线）
  spec: [l1.target_user]
  rules: [CRAFT-01@1]
candidates:
  - {id: A, source: agent, created_at: 2026-08-14T10:20:00Z, fidelity: description, summary: export-<时间范围>.csv（按周归档可读）, deviations: none, assets: []}
  - {id: B, source: agent, created_at: 2026-08-14T10:20:00Z, fidelity: description, summary: export-<固定名>-<时间戳>.csv（通用）, deviations: none, assets: []}
comparison:
  axes:
    - {axis: 周报归档检索 (l1.target_user), A: 支持——按周命名直接归档, B: 不利——归档前需重命名}
    - {axis: 主行动唯一性 (CRAFT-01@1), A: 遵循——命名不触碰界面层级, B: 遵循——命名不触碰界面层级}
  tradeoffs: "A 以命名约束换归档可读；B 以通用性换检索成本"
selection:
  candidate: A
  rationale: 周频归档场景下检索是主任务，轴 1 支持面更大
  rejected:
    - {candidate: B, reason: 周报场景每次归档需二次重命名}
confirmation:
  kind: agent
  via: agent-record
  confirmed_at: 2026-08-14T10:22:00Z
supersedes: null
```
