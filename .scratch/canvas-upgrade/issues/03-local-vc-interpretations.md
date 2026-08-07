# Ticket 03-local-vc-interpretations — 本地版本控制解释空间

Type: research
Status: resolved
Resolved: 2026-08-07

## Question

沉淀"本地版本控制"几种合理形状，作为后续目的地锁定的输入。"本地版本控制"是模糊词，需要落到具体形态 + 取舍。

至少覆盖以下五种形态，各附 1-2 段定义 + 适用场景 + 对本 effort 的契合度（高 / 中 / 低 + 一句理由）：

1. **Git 式**：本地 git 仓库 / git-annex / 自建 diff + branch + merge 引擎；二进制 / 文本双向 diff；语义合并 vs. 三路合并。
2. **快照式（snapshot list）**：每次保存一份 immutable 快照；列表展示 + 还原；不存 diff；简单 / 可读 / 不省空间。
3. **Figma 式版本（named versions + branches）**：命名版本 + 分支 + 可视化 diff + 合并 UI；UX 重；非纯本地（通常 sync 中心）。
4. **事件溯源（event sourcing）**：保存所有操作事件（command log），可重放 / fork / 派生；体积小；回放 UX 重。
5. **CRDT / 操作转换**：协作友好；本地版本是"我的 view"；合并自动；适合多人。

对每种形态补：

- **数据形态**：磁盘布局（单文件 / 目录 / 数据库）、可读性（人类可读 vs. 二进制）。
- **接入成本**：对当前 floating 批注画布的迁移难度。
- **G5 兼容**：与 Design I/O 流水线（round / decide / preview_prototype）的关系。
- **用户心智模型**：与"git / Figma / 时间机器"哪个最近。

## 资产

产出 `.scratch/canvas-upgrade/assets/local-vc-interpretations.md`（五种形态 × 多维对比表 + 一段建议倾向）。

## 来源

- Figma version history（公开产品页）
- Linear / Notion / Sketch 的版本机制（二手描述）
- git / pijul / jujutsu 的本地分支机制（一手）
- ProseMirror / Yjs / Automerge CRDT 文档（一手，CRDT 段）

## 约束

- 只用一手 + 公开二手；不臆造形态。
- 至少 5 种，不超过 7 种——避免无限展开。
- 每种形态必须有具体数据形态与适用场景，不能停在"高级 / 现代 / 协作友好"形容词。
- 给出"对当前画布 + Design I/O 流水线"的契合度初判（高 / 中 / 低），但**不锁定最终选型**——锁定是后续 grilling ticket 的工作。

## Answer

沉淀了 6 种形态（git 式 / pijul patch 式 / 快照列表式 / Figma 命名版本+分支 / 事件溯源 / CRDT-OT），资产在 `.scratch/canvas-upgrade/assets/local-vc-interpretations.md`。与当前 round 机制最接近的是**事件溯源**——`decision-round-N.json` 是不可变 append-only 事件、`log.md` 是重放投影，`round-N.html` 同时让它具备快照列表特征。契合度最高的两种：**事件溯源**（现状雏形 + 补 replay/fork 即升维，与 G5 不变量零冲突）与**快照列表式 + 命名版本**（现状 round-N.html 已是快照，补命名/浏览/非破坏性还原即达，心智模型最直观）。git/patch/CRDT 判断为低契合，Figma branch/merge UI 与 CRDT 留待方向 B/C 重估。初判明确但不锁定最终选型。