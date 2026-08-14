# Decision report (导出升级为「全局数据任务中心」第一步)

P3 全量档。顶块 = Fill 消费面；DD 条目块记录 E 档探索、R3 重入修订与基线漂移复核（G10 校验）。

```text
design-baseline: DESIGN.md sha256:2d0728566b52e19c5fb5fd81cb7c8ef44dd51f63e83212154b4d954dc22425a3
scene: ops console data export (task-center step 1)
density: console-tight
template: toolbar + table + global status region
regions:
  toolbar: row-selection actions (batch export primary)
  table: last-week data with stable comparison columns
  status: global task feed — in-flight and recent export tasks (persistent across views)
  toast: page-level notices (cap limit, export done)
components:
  batch export -> Button (single primary; busy state while exporting)
  task entry -> status region item with progress; done state opens result
  cap notice -> toast with role=alert and readable name (includes cap value)
  list -> Table (not card wall)
baseline-changes: none
risks:
  - status region becomes dumping ground -> only export tasks this step; feed caps at 10 entries
  - persisted entries leak across sessions -> entries live for the run only (export.task_persist_ttl assumption)
```

Do not start implementation until this report exists (or the user explicitly skips).

## DD-0003 — 导出进行中的状态呈现构成

E 档：命中判据 2（region 集合/权重重组 = 构成变化）。两案比较 → preview round 1 用户确认选 B。后被 R3 挑战（见 DD-0004）。

```yaml
id: DD-0003
tier: explore
question: 导出进行中的状态呈现构成
status: invalidated
constraints:
  baseline: DESIGN.md sha256:3fda06eff9714a24e23f6b6b75443b449313d63675512bd848f618135b9f9a69
  spec: [l1.scenes, l6.c1]
  rules: [PERF-01@1, CRAFT-01@1]
candidates:
  - {id: A, source: agent, created_at: 2026-08-14T10:58:00Z, fidelity: description, summary: 行内进度条嵌入各选中行 + 工具列总进度（强化 action region）, deviations: none, assets: []}
  - {id: B, source: provider-adapter, adapter: provider-a, created_at: 2026-08-14T11:00:00Z, fidelity: sketch, summary: 启用全局 status region 收纳导出任务（主列表仅禁用 + 行内微标）, deviations: none, assets: [candidates/B.html sha256:95647183de6f57d15d959211b863d79e4722c5c2a5701f46cd9e5c9f8d2b09e8]}
comparison:
  axes:
    - {axis: 任务适配·导出中切页 (l1.scenes), A: 不利——切页后状态散在行内不可查, B: 支持——全局一处可查}
    - {axis: 感知反馈相称性 (PERF-01@1), A: 部分——短导出足够长导出无持续感, B: 支持——长导出有持续进度感}
    - {axis: 基线·布局段 (DESIGN.md), A: 遵循——不新增 region, B: 遵循——启用既有 status region 惯例}
  tradeoffs: "A 以上下文邻近换操作区占用与切页丢失；B 以全局可见换离上下文远"
selection:
  candidate: B
  rationale: 切页场景全局可查 + 长导出持续进度两轴支持面更大
  rejected:
    - {candidate: A, reason: 导出中切页后状态无处可查（l1.scenes 轴不利）}
confirmation:
  kind: user
  via: preview-round-1 decision_id:5f0c9a21d4e34b7f8a2c6d1e9b04f7a3
  confirmed_at: 2026-08-14T11:06:00Z
supersedes: null
stale: DESIGN.md 来源哈希漂移检出（2026-08-14T12:00:00Z）——条目引用旧绑定 sha256:3fda06eff971…
stale_review: {exit: keep, note: 新基线布局段未改 region 惯例——复核行：status region 惯例仍在；重绑 sha256:2d0728566b52e19c5fb5fd81cb7c8ef44dd51f63e83212154b4d954dc22425a3（stale 解除）}
```

## DD-0004 — 导出任务状态跨页保持修订（R3 重入）

R3 finding（dd: DD-0003）挑战 B 案「状态区条目跨页保持」假设。修订 = 新条目 supersedes DD-0003（旧条目 invalidated 保留可解析）；重入命中 E 判据 4 → 仍 E 档 → preview round 2 用户再确认。

```yaml
id: DD-0004
tier: explore
question: 导出任务状态跨页保持修订（R3 重入）
status: confirmed-user
constraints:
  baseline: DESIGN.md sha256:3fda06eff9714a24e23f6b6b75443b449313d63675512bd848f618135b9f9a69
  spec: [l1.scenes, l6.c1, l6.c2]
  rules: [CRAFT-01@1]
candidates:
  - {id: B2, source: agent, created_at: 2026-08-14T11:20:00Z, fidelity: description, summary: B 修订——全局状态区 + 任务条目持久化（返回恢复显示，含完成态入口）, deviations: none, assets: []}
  - {id: A2, source: agent, created_at: 2026-08-14T11:20:00Z, fidelity: description, summary: 回退行内进度 + 返回后锚点恢复, deviations: none, assets: []}
comparison:
  axes:
    - {axis: 跨视图状态闭环 (l6.c2), B2: 支持——任务条目持久化且完成态可获知, A2: 部分——锚点恢复依赖行仍在视图内}
    - {axis: 主行动唯一性 (CRAFT-01@1), B2: 遵循——状态区不争夺主行动, A2: 遵循——行内进度弱化处理}
  tradeoffs: "B2 以全局持久换状态区治理成本；A2 以上下文邻近换跨页风险"
selection:
  candidate: B2
  rationale: 跨视图状态闭环轴支持面大且与基线 status region 惯例一致
  rejected:
    - {candidate: A2, reason: 行滚动后锚点失效——同一失败模式（跨页/滚动丢状态）}
confirmation:
  kind: user
  via: preview-round-2 decision_id:c81b2e6047fa4d92b3e5c8a1f6d09b42
  confirmed_at: 2026-08-14T11:27:00Z
supersedes: DD-0003
stale: DESIGN.md 来源哈希漂移检出（2026-08-14T12:00:00Z）——条目引用旧绑定 sha256:3fda06eff971…
stale_review: {exit: keep, note: 新基线布局段未改 region 惯例——复核行：持久 feed 约定仍成立；重绑 sha256:2d0728566b52e19c5fb5fd81cb7c8ef44dd51f63e83212154b4d954dc22425a3（stale 解除）}
```
