# Ticket 05-vc-data-model — 版本控制数据模型

Type: research
Status: resolved
Resolved: 2026-08-07

## Question

为"事件溯源 + 命名快照叠加（round 级）"设计数据模型与 API 形状。04 已锁定 D3（事件溯源+命名快照叠加），本票回答"具体怎么建模"。

**输入**：
- 03 资产 `assets/local-vc-interpretations.md` §5（事件溯源：append-only log + replay + fork）与 §3（快照列表式 + 命名版本）
- 01 资产 `assets/current-canvas-matrix.md` §3（状态维度：`decision-round-N.json` / `confirm-round-N.json` / `log.md` / `round-N.html` / lock）+ §4（版本能力）
- 代码：`packages/design-playbook/mcp/preview/transaction.py`（当前事务层）

**需回答**：
- **事件 schema**：decision entry 如何泛化为事件？事件类型（`round_confirmed` / `round_revised` / `anchor_added` / `named_version` 等）？事件字段？时间戳 / 顺序？
- **快照与命名版本**：`round-N.html` 如何打命名版本？命名信息放哪（事件字段？独立 index？）？时间线浏览的数据源？
- **replay API**：`state_at(N)` 形状（返回什么——原型 + 反馈组合？）？重放的语义边界（跨 round 冲突？）
- **fork API**：从某 round 派生替代方案（新 binding？新目录？）？与 G5 "use next round" 冲突如何解决？
- **与 transaction.py 的关系**：新 schema 是扩展现有 entry 还是新文件？向后兼容 v0.10 产物？
- **锚点 AST 化**（随本票或另票）：cssPath → node id 的最小实现（node id 怎么生成 / 存哪 / 跨轮稳定性）？

**方式**：AFK research + 设计。产出 `assets/vc-data-model.md`（schema 草案 + API 签名 + 兼容性分析）。不实现。

**约束**：
- 只读现有代码；schema 草案落到 `assets/`。
- 向后兼容：不得破坏现有 `decision-round-N.json` / `confirm-round-N.json` 的读侧（`validate_run.py` 依赖）。
- 粒度 round 级（非操作级），与 G5 不变量零冲突。

## Answer

设计草案落 `assets/vc-data-model.md`（2026-08-07）：

- **事件溯源不建新存储**：现有 `decision-round-N.json` 就是事件（append-only、不可变）；补 `state_at(N)`（replay，只读）+ `fork`（新 preview 目录内独立链，round 从 1 重计，`fork.json` 记来源）即可。
- **命名快照 = 元事件**：新权威文件 `version-<seq>.json`（append-only、原子写、不可变；约束：round 必须存在、name 非空 ≤80、重命名=新事件）；时间线 = decision ∪ version 按 timestamp 合并排序。
- **锚点 AST 化（局部）**：anchor schema v2 加可选 `node_id`（round 内稳定哈希）+ `features`（跨轮重连特征）；不做全文档 AST；读侧（validate_run/floor）忽略未知字段。
- **兼容性**：纯新增——新模块 `versions.py`（import 复用 `_atomic_write`/`_load_entry`/`_valid_entries`），不改 entry schema（保持 v1）、不改 lock / round 递增 / "use next round"。G5 不变量零冲突。
- **落地拆票**：05a versions.py 实现 + 05b anchor v2 + 06 原型（现 unblocked）+ v0.11.x release。