# Ticket 05a-versions-py-implementation — versions.py 实现

Type: task
Status: resolved
Resolved: 2026-08-07

## 任务

按 `assets/vc-data-model.md` 实现版本控制模块 `packages/design-playbook/mcp/preview/versions.py`（纯新增，不改 transaction.py 现有逻辑）：

- `state_at(preview_dir, round_n)` — replay 到 round N（读 entry + round-N.html + confirm + ≤N 的命名版本；N 无 entry 报错；只读）
- `fork(source_dir, *, branch, from_round, new_dir, report_ref, summary)` — 派生新链（新目录 + `fork.json` + 复制原型到 round-1.html）
- `create_named_version(preview_dir, *, round_n, name, kind, note)` — 写 `version-<seq>.json`（append-only 原子写；校验 round 存在、name 非空 ≤80；seq 扫描递增）
- `timeline(preview_dir)` — decision ∪ version 按 timestamp 合并排序
- `list_versions(preview_dir)` — 仅命名版本

复用 transaction.py 的 `_atomic_write` / `_json_text` / `_load_entry` / `_valid_entries` / `_now_iso`（import）。`log.md` 的 `## versions` 投影段（05 资产 §3.3）随本票。

## 验收

- 单元测试：state_at（存在/缺失/aborted 标注）、fork（round 从 1 重计、fork.json 权威）、create_named_version（round 校验、name 校验、seq 递增、不可变）、timeline 排序
- `pytest` 全绿（新增测试 + 现有回归）
- 不改 entry schema v1；validate_run 读侧回归绿

## 约束

- 不碰 main；落 `feature/canvas-thickening` 分支（本 effort 开发态可先在本仓工作树实现）
- 与 G5 不变量零冲突（不触碰 lock / round 递增 / "use next round" 语义）

## Answer

实现完成（2026-08-07）：

- 新模块 `packages/design-playbook/mcp/preview/versions.py`：`create_named_version` / `state_at` / `fork` / `timeline` / `list_versions` + `_render_versions_log` / `_refresh_log`。schema_version=1，name ≤80，kind ∈ {confirmed,revised,custom}，seq 扫描递增，append-only 原子写。
- `transaction.py::_commit_projections` 改一行（lazy import `_render_versions_log`）：log.md 投影现含 `## versions` 段；无 version 文件时输出与原来逐字节一致（兼容）。
- 新增 `test_versions.py`（10 测试，全绿）：round 校验 / append-only / log 投影 / name+kind 校验 / note 截断 / state_at（含 aborted 标注、versions 截断）/ fork（round 重计、fork.json、path 模式拒绝）/ timeline 合并。
- 回归：`test_transaction` + `test_server_stdio` 共 25 测试全绿（含 G5 stdio e2e）。entry schema v1 未改，validate_run 读侧不受影响。