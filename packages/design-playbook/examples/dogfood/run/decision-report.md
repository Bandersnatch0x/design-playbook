# Decision report (队列监控升级为「全局模拟运行中心」第一步)

P3 全量档（S6 dogfood，目标面 = showcase SwarSight 队列监控页）。顶块 = Fill 消费面；DD 条目块记录 E 档探索、R3 重入修订与基线漂移复核（G10 校验）。

```text
design-baseline: DESIGN.md sha256:2c7e9f3ab5d1e04c6a8f0b2d4e6c9a1f3b5d7e9c1a3f5b7d9e1c3a5f7b9d1e3f
scene: ops console simulation queue (run-center step 1)
density: console-tight
template: global run console + table + side trends
regions:
  console: global run summary (running/paused/failed) + run feed (in-flight and recent, persistent across views) + global pause/resume
  table: simulation run list (status, scenario, owner, duration, resources, actions)
  side: failure trends, queue pressure, recent failure causes
  toast: page-level notices (global-pause failure, retry queued)
components:
  global pause -> Button with accessible name and role; busy state while applying
  run feed entry -> console item with progress; done state opens result
  batch retry -> selection-floating action bar (explicit text on destructive actions)
  list -> Table (not card wall)
baseline-changes: topbar counts replaced by global run console region
risks:
  - console becomes dumping ground -> only simulation run feed this step; feed caps at 12 entries
  - persisted feed leaks across sessions -> entries live for the run only (sim.control_scope assumption bounds the pause scope)
```

Do not start implementation until this report exists (or the user explicitly skips).

## DD-0001 — 顶栏计数区升级的呈现构成

E 档：命中判据 2（region 集合/权重重组 = 构成变化）。两案比较 → preview round 1 用户确认选 B。后被 R3 挑战（见 DD-0002）。

```yaml
id: DD-0001
tier: explore
question: 顶栏计数区升级的呈现构成
status: invalidated
constraints:
  baseline: DESIGN.md sha256:8f4d2b61c7a3e95d0f8c2a1b6e9d4c7f3a5b8d1e0c2f4a6b8d0e2c4f6a8b0d2f
  spec: [l1.scenes, l6.c4]
  rules: [PERF-01@1, CRAFT-01@1]
candidates:
  - {id: A, source: agent, created_at: 2026-08-14T09:22:00Z, fidelity: description, summary: 顶栏轻量计数增强（计数 + 最近 3 条 toast 式通知，强化既有 topbar）, deviations: none, assets: []}
  - {id: B, source: provider-adapter, adapter: provider-a, created_at: 2026-08-14T09:24:00Z, fidelity: sketch, summary: 启用全局 run console region（汇总 + feed + 全局控制；主列表仅禁用 + 行内微标）, deviations: none, assets: [candidates/console-region.html sha256:547cbb919d2124c2536942df8eca134e8bfcbad8ebd03c8086c7d025e0902da8]}
comparison:
  axes:
    - {axis: 任务适配·运行中切页 (l1.scenes), A: 不利——切页后计数无条目可续读, B: 支持——全局一处可续读}
    - {axis: 感知反馈相称性 (PERF-01@1), A: 部分——长运行无持续进度感, B: 支持——feed 条目级进度持续}
    - {axis: 基线·布局段 (DESIGN.md), A: 遵循——不新增 region, B: 突破——顶栏不承载任务级数据惯例被 region 取代（呈报用户裁决）}
  tradeoffs: "A 以轻量换跨页不可续读；B 以新 region 换全局可查（需基线漂移复核）"
selection:
  candidate: B
  rationale: 切页续读 + 长运行持续进度两轴支持面更大；布局段突破经用户确认接受
  rejected:
    - {candidate: A, reason: 运行中切页后状态无处可续读（l1.scenes 轴不利）}
confirmation:
  kind: user
  via: preview-round-1 decision_id:7c3a91e4d2b6f80a5c7e9d1b3f5a8c0e
  confirmed_at: 2026-08-14T09:32:00Z
supersedes: null
stale: DESIGN.md 来源哈希漂移检出（2026-08-14T09:40:00Z）——条目引用旧绑定 sha256:8f4d2b61…
stale_review: {exit: keep, note: 新基线布局段未改 region 惯例的其余部分——复核行：console region 约定成立且其余布局段未动；重绑 sha256:2c7e9f3ab5d1e04c6a8f0b2d4e6c9a1f3b5d7e9c1a3f5b7d9e1c3a5f7b9d1e3f（stale 解除）}
```

## DD-0002 — 运行 feed 跨页保持修订（R3 重入）

R3 finding（dd: DD-0001）挑战 B 案「控制台 feed 跨页保持」假设。修订 = 新条目 supersedes DD-0001（旧条目 invalidated 保留可解析）；重入命中 E 判据 4 → 仍 E 档 → preview round 2 用户再确认。

```yaml
id: DD-0002
tier: explore
question: 运行 feed 跨页保持修订（R3 重入）
status: confirmed-user
constraints:
  baseline: DESIGN.md sha256:8f4d2b61c7a3e95d0f8c2a1b6e9d4c7f3a5b8d1e0c2f4a6b8d0e2c4f6a8b0d2f
  spec: [l1.scenes, l6.c4, l6.c5]
  rules: [CRAFT-01@1]
candidates:
  - {id: B2, source: agent, created_at: 2026-08-14T09:44:00Z, fidelity: description, summary: B 修订——全局控制台 + feed 条目持久化（返回恢复显示，含完成态入口与上限治理）, deviations: none, assets: []}
  - {id: A2, source: agent, created_at: 2026-08-14T09:44:00Z, fidelity: description, summary: 回退顶栏计数 + 返回后锚点定位恢复, deviations: none, assets: []}
comparison:
  axes:
    - {axis: 跨视图状态闭环 (l6.c4), B2: 支持——feed 条目持久化且状态可续读, A2: 部分——锚点恢复依赖行仍在视图内}
    - {axis: 主行动唯一性 (CRAFT-01@1), B2: 遵循——控制台不争夺主行动, A2: 遵循——顶栏计数弱化处理}
  tradeoffs: "B2 以全局持久换控制台治理成本（上限 12 条 + 让位规则）；A2 以上下文邻近换跨页风险"
selection:
  candidate: B2
  rationale: 跨视图状态闭环轴支持面大且与运行中心第一步的方向一致
  rejected:
    - {candidate: A2, reason: 行滚动后锚点失效——同一失败模式（跨页/滚动丢状态）}
confirmation:
  kind: user
  via: preview-round-2 decision_id:9d5b2f70c4e6a8d0b2f4a6c8e0d2b4f6
  confirmed_at: 2026-08-14T09:52:00Z
supersedes: DD-0001
stale: DESIGN.md 来源哈希漂移检出（2026-08-14T09:40:00Z）——条目引用旧绑定 sha256:8f4d2b61…
stale_review: {exit: keep, note: 新基线布局段未改 region 惯例的其余部分——复核行：持久 feed 约定仍成立；重绑 sha256:2c7e9f3ab5d1e04c6a8f0b2d4e6c9a1f3b5d7e9c1a3f5b7d9e1c3a5f7b9d1e3f（stale 解除）}
```
