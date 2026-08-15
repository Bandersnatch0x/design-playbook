<!-- run-profile: v1 -->

```yaml
tier: P2
criteria:
  - decided-fields: add-only (l6.c1-c3, l2.entry_choice; existing decided untouched)
  - spec-touch: full six-layer draft with L2-L5 structured fields
  - blocking: not bounded at intake
  - routes: R1 additions legal (new criteria class)
  - decision-tier: R/C (current decision-report top block; DD entries land in a later slice)
  - shaping: full S0-S6 session (new ask, not a repeat run)
confirmed_by: user + 2026-08-14T09:30:00Z
skipped:
  - preview: adapter absent, no E-tier decisions (G5 not triggered; enable via packages/design-playbook/mcp/preview/ or host MCP)
upgrades: []
```

# 数据导出入口 — plan

## 本次 run 范围

- L2：main-list / export-dialog 两页职责；入口选择已确认（`l2.entry_choice` = B 行内批量）。
- 场景：运营周报导出（`l1.scenes` 假设已 ack）。
- 非目标：不做调度、不做全量历史（`l1.non_goals` decided）。

## 用户描述 → spec 映射

- 「给控制台加一个数据导出入口」→ `l1.goal` / `l1.target_user`（D-0001/D-0002）。
- 「CSV 就行，别做定时任务」→ `l6.c1` 表述 + `l1.non_goals`（D-0003/D-0004）。
- 规模上限未答 → `export.row_cap` 显式风险假设（CP-C 改写 20 万行）。

## ui-picker 输入包

- scene hints: console-tight 运营主列表 + 行内批量操作条。
- constraints: 复用既有表格组件；不新增全局工具栏。
- exclusions: 不引入卡片墙；不做营销式 hero。
