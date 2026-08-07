# Ticket 07-interaction-improvements — 交互改进（draft 持久化 + undo）

Type: task
Status: resolved
Resolved: 2026-08-07

## 任务

改进 `packages/design-playbook/mcp/preview/control.js` 的交互（01 资产 §1 已知痛点）：

- **draft 持久化**：feedback + anchors 存 `localStorage`（key 按 round/run 隔离），刷新不丢（现状 01 资产 §3"客户端状态零持久化，刷新即丢" control.js:129-133）
- **undo**：anchors 操作（add / remove / comment 编辑）可撤销——维护轻量 undo 栈（Ctrl/Cmd+Z），remove/clear 不再不可恢复
- **裁剪（不做）**：多选 / 框选——批注场景每个锚点独立评论，框选价值低；如用户要求再补

## 验收

- draft 持久化：刷新后 feedback/anchors 恢复
- undo：add/remove/comment 可 Ctrl/Cmd+Z 撤销，状态与 hidden input 同步
- 现有行为回归：pin / floor / ready / arm 状态机不变（I1/I2/I4/I8/I13/I18/P1.x 语义）
- 前端 marker（`--self-check` / playwright 锁定）不破坏

## 约束

- 不碰 main；落 `feature/canvas-thickening` 分支
- localStorage 隔离：不得污染宿主页其它 run 的数据

## Answer

实现完成（2026-08-07）：

- **draft 持久化**：control.py 注入 `window.DPB_DRAFT_KEY`（`dpb.draft.<sha256(round|summary)>[:16]`，per-run 隔离）；control.js `saveDraft`/`loadDraft`/`clearDraft`——feedback + anchors 存 localStorage，刷新恢复（锚点按 selector 重建 el + 高亮），提交/abort 后清除。
- **undo**：`pushHistory`（add/remove/comment-commit 入栈，≤50）+ `undo()`（Ctrl/Cmd+Z，恢复 anchors + 重渲染 + 存 draft）；comment 用 change 事件（commit 点）入栈避免每键入。
- **裁剪（不做）**：多选/框选——批注场景每锚点独立评论，框选价值低（07 票原文已声明）。
- **测试**：e2e `test_undo_removes_last_anchor` + `test_draft_persists_across_reload` 绿；`test_floor_frontend` 20 场景适配（行为变化：同 run draft 恢复是预期——场景间 goto 前显式清 localStorage，因 playwright init-script 对同 URL 重复 goto 不执行）后全绿。
- **回归**：61 单元 + 3 e2e + floor 20 + pin bridge 全绿。