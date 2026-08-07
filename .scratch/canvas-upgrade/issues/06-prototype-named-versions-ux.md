# Ticket 06-prototype-named-versions-ux — 命名版本 + 回放 UX 原型

Type: prototype
Status: resolved
Resolved: 2026-08-07

## Question

做一份 rough prototype 验证"命名版本 + 时间线浏览 + replay/fork"在 G5 反馈画布上的交互形态，给用户反应（04 锁定的 D3 落地 UX）。

**输入**：
- 05 数据模型票（blocked by）——schema 定了才做
- 03 资产 `assets/local-vc-interpretations.md` §3（快照列表式 + 命名版本）与 §5（事件溯源 replay/fork）
- 01 资产 `assets/current-canvas-matrix.md` §1（现有 drawer/pill 结构与交互）

**原型范围**（rough，非完整实现）：
- **命名版本**：round 通过后如何打标签（已确认 / 已修订 / 自定义名）？入口放哪（drawer 头部？时间线项）？
- **时间线浏览**：历史列表（round 1..N + 命名版本）放哪（drawer 侧栏？新增面板？）；点击回看（加载历史 `round-N.html`？）
- **replay/fork 示意**：非破坏性还原 + 派生替代方案的最小交互示意（不真实现 replay 引擎，仅示意入口 / 流程）

**方式**：prototype（HITL）——做 cheap rough artifact（HTML / 示意图），链接到票。用户反应后迭代。

**约束**：
- 不实现产品代码；只做原型资产（`assets/` 或票内）。
- 复用现有 drawer/pill 结构（01 资产），不做全新 UI 框架。

## Answer

原型已做：`assets/prototype-named-versions-ux.html`（可交互 HTML mock，2026-08-07），已展示给用户（用户指令"完成所有票"授权执行模式）。

**UX 形态（基于 05 数据模型）**：
- **入口**：drawer 新增"版本"tab（与"评审"tab 并列），pill 确认按钮直接跳命名输入。
- **命名版本**：命名输入行（round 通过后打标签，kind=confirmed/revised/custom，≤80 字）；保存 = `version-<seq>.json` 写入示意。
- **时间线**：decision ∪ version ∪ fork 按时间合并列表，命名版本 ✦ 图标、fork ⑂ 图标、类型徽章（已确认/已修订/分支）。
- **回看**：点 round 项 → `state_at(N)` 只读回放，overlay 提示"非破坏性回看，当前链未变"。
- **fork**：从某 round "派生分支" → `preview/fork-<branch>/` 独立链（round 重计，fork.json 记来源）示意。
- **交互改进联动**：undo toast 示意（07 票的 Ctrl/Cmd+Z）。

**UX 微调待吸收点**（08 e2e 阶段）：
- 时间线项太多时的折叠/过滤（kind 过滤）。
- 命名入口在"确认后自动弹" vs "手动点"——原型用手动 + pill 快捷，实现时按 e2e 反馈定。