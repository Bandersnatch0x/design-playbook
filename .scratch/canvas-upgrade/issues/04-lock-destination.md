# Ticket 04-lock-destination — 锁定目的地

Type: grilling
Status: resolved
Resolved: 2026-08-07

## Question

基于 gap 表（`assets/gap-analysis.md`）锁定本 effort 的真实目的地。

**gap 表关键事实**：
- 必须能力 11 项里，当前画布**仅 S1（命名版本）有部分雏形**，其余 10 项基本"无"。
- "Figma/Stitch 级别"在插件内不可达——需补可视化编辑（C1）等 6 项核心能力，是**新产品量级**，改变产品性质（从"agent 写码+人评审"变"人也能画"）。
- **版本控制是唯一已有雏形且迁移成本最低的能力**（03 两高契合：事件溯源 + 快照列表式），与 G5 不变量零冲突。
- stable-main 冻结 + 分发暂停是硬约束（ADR-0015），方向 B/C 在解除前不可走 release transaction。

## 需裁决的决策点

- **D1 目的方向**：A / B / C / 组合（"A 先行 + B/C 远期"）？—— 最关键，D2-D5 依赖它
- **D2 "Figma/Stitch 级别"是否重新定义**：接受"A 达不到 Figma 级但做厚反馈循环"为本次目的地？还是必须 B/C 才算？
- **D3 版本控制形态**：03 两高契合（事件溯源 + 快照列表式）选哪个/组合？粒度（round 级 / 操作级）？
- **D4 stable-main 时序**：方向 B 是否本 effort 内 lift ADR-0015，还是留外部依赖？
- **D5 跨包影响**：方向 C 下 `packages/design-playbook-preview` 重新定位？

## 方式

grilling（HITL），一问一答。先问 D1。

## Answer

grilling 2026-08-07，与用户一问一答（D1 → D3）：

- **D1 = 纯 A**：厚化批注画布（feature/canvas-thickening，minor）。B/C 不在本 effort 考虑。
- **D2 = 目的地重定义**：本次目的地是"做厚 G5 反馈循环到准画布评审"，**不追 Figma/Stitch 级别**（该级别在插件内不可达——需 10/11 项必须能力，是新产品量级，改变产品性质）。
- **D3 = 事件溯源 + 命名快照叠加，round 级粒度**：`decision-round-N.json` 链 = 事件（补 replay `state_at(N)` + fork 对比替代方案）；`round-N.html` = 命名快照（补命名 / 时间线浏览 / 非破坏性还原）。与 G5 不变量零冲突，迁移最小。
- **D4/D5 作废**（B/C 不选——stable-main 解除时序与 `design-playbook-preview` 跨包影响不适用本 effort）。

由此锁定的本 effort 能力面（方向 A 可达的最大增量）：S1 命名版本（来自 02）+ 事件溯源/命名快照（来自 03）+ 锚点 AST 化（cssPath → node id，S3 的局部）+ 交互改进（多选 / 框选 / undo / draft 持久化）。