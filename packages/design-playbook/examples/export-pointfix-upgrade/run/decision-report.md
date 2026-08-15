# Decision report (空数据集导出修复 + 列范围升档)

ui-picker output before code. 顶块为上轮记录的逐字保留（Fill 消费面不动）；升档 P2 后追加 R 档 DD-0101（G10 校验）。

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
  - empty dataset export gives no feedback and no file -> guarded this run (empty-blocked pre-check)
  - repeated trigger during export -> busy + disabled while in flight
  - hidden sensitive columns -> export.column_scope assumption acknowledged
```

Do not start implementation until this report exists (or the user explicitly skips).

## DD-0101 — 列圈选导出的判据落位

R 档直录（升档 P2 后补走）：单一合理选择——列圈选复用既有列范围开关交互；判据表述本身经增量成形会话 CP-A 用户确认（D-0101，shaping-log 可溯），控件落位是代理决定。

```yaml
id: DD-0101
tier: record
question: 列圈选导出的判据落位
status: confirmed-agent
constraints:
  baseline: waived: 本 run 未绑定 DESIGN.md（示例项目无基线）
  spec: [l6.c4]
selection: {candidate: 复用导出面板列圈选开关（Checkbox group）, rationale: 组件角色表已有列范围声明，圈选即其选择面；不新增控件形态}
confirmation:
  kind: agent
  via: agent-record
  confirmed_at: 2026-08-14T12:44:00Z
supersedes: null
```
