# Gap 分析 — 当前画布 vs Figma/Stitch 目标 + 本地版本控制

> Ticket 01-03 的综合产物。输入：`current-canvas-matrix.md`（01）、`figma-stitch-target-baseline.md`（02）、`local-vc-interpretations.md`（03）。
> 用途：04 grilling 票锁定目的地的依据。本表不下结论——只摆事实 + 标 gap 大小 + 标方向影响。

## 1. 必须能力 gap（02 的"必须 11 项" × 01 当前实现）

| # | 目标能力（02） | 当前实现（01 来源） | gap | 涉及版本控制（03） | 方向影响 |
| --- | --- | --- | --- | --- | --- |
| C1 | 可视化编辑：点选/拖拽/resize/recolor/文本编辑 | 无 drag/resize/recolor/text 编辑；仅 pin 选择 + 批注文本（control.js:512-547） | **巨大**（核心缺口） | — | A 拿不到（批注层无编辑语义）；B/C 必须从零建编辑表面 |
| C2 | 图层面板：层级树/选择/命名/显隐/锁定 | 无图层树；anchor 是扁平列表（control.js:52-56） | **无** | — | A 可做"锚点列表→伪图层"但非真图层；B/C 需建 AST 才有图层 |
| C3 | 组件与实例：可复用定义+引用+覆盖 | 画布层无组件概念（SSOT components.md 有语义但非画布能力） | **无**（画布层） | — | A 拿不到；B/C 需把 SSOT 组件语义升级为画布实例模型 |
| C4 | 自动布局：响应式容器（flow/padding/gap） | 无；原型自身响应式由 HTML 决定（browser.py:572-573） | **无** | — | A 不适用；B/C 需建布局引擎 |
| C5 | 画框与页面：文档分块（frame/page/section） | 无 frame/page；round 是时间维度非空间分块 | **无** | 快照列表式（round 即页面的时间切片） | A 可做"round 时间线"非空间 frame；B/C 需真 frame/page |
| C6 | 设计令牌：可复用值+别名+模式 | 画布层无令牌；SSOT design.md 的 `var(--*)` 是给 Fill 的，非画布编辑 | **无**（画布层） | — | A 不适用；B/C 需把 SSOT 令牌升级为画布可编辑变量 |
| S1 | 命名版本历史（snapshot） | 部分：round 序号 + prototype HTML 的 SHA-256（transaction.py:290）；无命名版本（transaction.py:280-290） | **部分**（round 是雏形） | **高契合**：事件溯源 §5 + 快照列表式 §3 | A 能直接拿（补命名/浏览/还原）；B/C 同样需要 |
| S3 | 文档 AST/节点树/引用图 | 无 AST；anchor 用 cssPath（DOM 路径，非 AST），原型变更即失效（control.js:73-107） | **无** | 事件溯源依赖 S3 做 replay/fork | A 可做"锚点 AST 化"（cssPath→node id）作为局部改进；B/C 需全文档 AST |
| S4 | Dev handoff：导出 CSS/Tailwind/JSON | 无导出；preview 是反馈面，handoff 是 Fill 的事（design-playbook 别处） | **无**（preview 面） | — | A 不适用（handoff 不在 preview）；B/C 若做编辑画布则 handoff 是其产物 |
| S5 | 组件 props/variants | 无 | **无** | — | A 不适用；B/C 需建组件属性模型（对齐 SSOT components.md 变体） |

**必须 11 项 gap 汇总**：当前画布**仅 S1 有部分雏形**（round），其余 10 项基本"无"。

## 2. 版本控制 gap（03 的形态空间 × 当前 round 机制）

| 03 形态 | 与当前 round 机制关系 | 接入成本 | G5 兼容 | 契合度 |
| --- | --- | --- | --- | --- |
| 事件溯源（§5） | `decision-round-N.json`=事件、`log.md`=投影、`round-N.html`=快照——已是雏形 | 中（补 replay `state_at(N)` + fork） | 高 | **高** |
| 快照列表式+命名版本（§3） | `round-N.html` 已是快照 | 低（补命名/浏览/还原） | 高 | **高** |
| Figma 式 branch/merge（§4） | round 线性递增，无分支 | 中–高（branch UI 与单线程 G5 冲突） | 中 | 中（仅 named versions 一半契合） |
| Git 式（§1）/ Patch 式（§2）/ CRDT（§6） | 无 merge 场景 | 高 | 弱 | 低 |

**版本控制 gap 汇总**：当前已是"事件日志+快照+投影"雏形；**两高契合方向（事件溯源 + 快照列表式）可叠加**，迁移成本最低、与 G5 不变量零冲突。

## 3. 关键洞察（供 04 grilling 裁决）

1. **scope 跨度极大**：从批注层到"Figma/Stitch 级别"需补 10/11 项必须能力——这是**新产品的量级**，不是插件 minor。当前画布连"可视化编辑"（C1）这一底线都没有。
2. **版本控制是唯一已有雏形且迁移成本最低的能力**：S1（命名版本）+ 03 的两高契合方向，是**任何方向都能拿到、且方向 A（厚化批注）能拿到的最大增量**。
3. **方向与 gap 的对应**：
   - **A 厚化批注画布**（minor，feature/canvas-thickening）：能拿 S1（命名版本）+ 部分 S3（锚点 AST 化）+ 交互改进（多选/框选/undo/draft 持久化）。**拿不到 C1-C6 编辑能力**——所以 A 达不到"Figma/Stitch 级别"，但能把反馈循环做厚到"准画布评审"。
   - **B 新增可视化编辑画布**（major，需先 lift ADR-0015 + 解分发）：能拿全 11 项，但需从零建编辑表面 + AST + 布局引擎 + 令牌系统——是 v2.x 量级。
   - **C 拆独立产品**：完整 Figma 级别，但脱离插件定义，需新 repo/包/分发通路。
4. **"Figma/Stitch 级别"在插件内不可达**：插件角色是"Design I/O 流水线 + 验收"（CONTEXT.md），preview 是 G5 反馈门。把 preview 升级成 Figma 级编辑器，等于改变产品性质（从"agent 写码+人评审"变"人也能画"）。这是**产品定义问题**，不是 feature 问题。
5. **stable-main 冻结 + 分发暂停是硬约束**（ADR-0015）：方向 B/C 在冻结解除前不可走 release transaction；方向 A 可走 `feature/canvas-thickening` 分支但不入 main。

## 4. 04 grilling 需裁决的决策点

- **D1 目的方向**：A / B / C / 组合（如"A 先做版本控制增量，B/C 留远期"）？
- **D2 "Figma/Stitch 级别"是否重新定义**：接受"A 达不到 Figma 级但做厚反馈循环"为本次目的地？还是必须 B/C 才算？
- **D3 版本控制形态**：03 两高契合方向选哪个/组合？粒度（round 级 / 操作级）？
- **D4 stable-main 时序**：方向 B 是否本 effort 内 lift ADR-0015，还是留外部依赖？
- **D5 跨包影响**：方向 C 下 `packages/design-playbook-preview` 重新定位？

> 本表到此为止。裁决归 04 grilling 票（HITL，需与用户一问一答）。