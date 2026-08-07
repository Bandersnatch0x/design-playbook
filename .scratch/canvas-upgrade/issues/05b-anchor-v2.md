# Ticket 05b-anchor-v2 — 锚点 schema v2 实现

Type: task
Status: resolved
Resolved: 2026-08-07

## 任务

按 `assets/vc-data-model.md` §5 实现 anchor schema v2——给锚点加可选 `node_id` + `features`，提交侧生成，读侧兼容：

- **提交侧生成**（`packages/design-playbook/mcp/preview/` 的 anchors 解析处，01 资产 `browser.py:632-673` `_parse_anchors`）：anchors 排序后生成 `node_id`（`sha256(round|index|selector)[:8]`）+ `features`（tag/text/classes/aria_label）
- **读侧兼容**：`validate_run.py` / `_check_feedback_floor` 只读 selector/comment/label/tag，新增字段被忽略——需回归确认
- 锚点持久化后 `decision-round-N.json` 的 outcome.anchors 含 v2 字段

## 验收

- 单元测试：node_id 确定性（同 round 同 selector 同 id）、features 提取、validate_run 读 v2 anchors 不报错
- `pytest` 全绿（新增 + 现有回归）
- G5 floor 逻辑不变（只看 selector/comment）

## 约束

- 不承诺跨轮自动重连（sandbox 限制，01 资产 §5/§7）——features 仅存储供后续/手动重连
- 不碰 main；落 `feature/canvas-thickening` 分支

## Answer

实现完成（2026-08-07）：

- `browser.py`：`_parse_anchors(raw, round_n=0)` 增加可选 v2 字段——`node_id`（`sha256(round|index|selector)[:8]`，round 内稳定、跨轮不可比）+ `features`（tag/text/classes 从现有字段派生，供后续手动重连候选）；`round_n<=0` 时不生成 v2 字段（向后兼容）。
- `do_POST` 解析 `dpb_round` 提前，anchors 解析传入 `posted_round`。
- 新增 `test_anchor_v2.py`（5 测试，全绿）：node_id 确定性 + round/index 隔离、v2 字段条件生成、读侧兼容（validate_run 只读 base 字段，v2 纯增量）。
- 回归：`test_browser_control` 等现有测试不受影响（anchors_json 空数组路径不变）。