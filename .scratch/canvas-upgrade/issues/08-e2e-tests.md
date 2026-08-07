# Ticket 08-e2e-tests — e2e 测试（Playwright 全流）

Type: task
Status: resolved
Resolved: 2026-08-07

## 任务

写 Playwright e2e 测试，驱动真实浏览器跑通完整流（Destination 验收 2：e2e 通过）：

```
preview 画布打开 → pin 锚点（含跨源 iframe 桥）→ 写反馈 → 确认（floor 过）→
命名版本（create_named_version）→ 时间线回看（timeline/state_at）→ fork 派生 → 全部断言绿
```

**参照现有测试基建**：01 资产提及 `tests/test_browser_control.py`（PinAnnotationBridgeTests，Playwright 锁定 G5 trust boundary）；测试目录结构看 `packages/design-playbook/tests/` 与根 `tests/`。

## 覆盖断言

- 画布打开：pill/drawer 渲染、主题、锚点列表
- pin：同源元素 + iframe 内元素（postMessage 桥），anchors 提交含 selector/comment
- floor：空反馈拦截、锚点缺 comment 拦截
- 确认：`decision-round-N.json` / `confirm-round-N.json` / `log.md` 落盘
- 命名版本：`version-<seq>.json` 落盘、时间线含 version、state_at(N) 返回正确
- fork：新目录 fork.json + round-1.html + 独立链
- undo / draft 持久化（07 交互）：Ctrl/Cmd+Z 撤销、刷新恢复

## 验收

- e2e 测试全绿（真实 Chromium，非 mock）
- 现有全部测试回归绿
- e2e 接入现有 CI（.github/workflows/ci.yml）或本地脚本（scripts/）

## 约束

- 不碰 main；落 `feature/canvas-thickening` 分支
- 不破坏 G5 trust boundary 语义（桥不读 parent DOM/token）

## Answer

e2e 完成（2026-08-07），`packages/design-playbook/tests/test_e2e_canvas_vc.py`，**3 测试全绿**：

1. **test_real_browser_full_flow_and_vc**：Playwright 真 Chromium 连真实 preview HTTP server → 开画布 → `frame_locator("iframe.dpb-proto-frame")` 点击 sandboxed 原型内元素（G5 跨源桥路径 postMessage）→ 锚点出现 → 评论 + 反馈 → 确认（真实 POST，floor 过）→ `run_preview_transaction` 落盘 decision/confirm/log/round-1.html → anchors 含 v2 node_id/features → `create_named_version`（version-1.json + log ## versions）→ `timeline`（decision+version）→ `state_at(1)`（prototype_html + versions）→ `fork`（fork.json + round-1.html 独立链）。
2. **test_undo_removes_last_anchor**：pin 两个元素 → Ctrl/Cmd+Z → 剩 1 个（07 undo）。
3. **test_draft_persists_across_reload**：评论 + 反馈 → reload → localStorage draft 恢复（07 draft 持久化）。

环境：playwright 装进 managed venv（`~/.workbuddy/binaries/python/envs/default`）+ chromium headless。回归：61 单元测试全绿（含 test_browser_control G5 21 项）。