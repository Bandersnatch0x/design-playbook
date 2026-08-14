# Decision report (数据导出入口)

ui-picker output before code. R/C 档决策以现行顶块记录（DD 条目块属后续切片）。

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
