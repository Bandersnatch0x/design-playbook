# Point-back — 导出升级（P3 全量档，含 R3 重入 + 基线漂移复核）

Six-block report (final state). Round 1: 1 条 R3 blocking（interaction 轨，dd: DD-0003 挑战方向假设）→ Recirculate → DD-0004 supersedes 修订 → Re-Fill → 失效集重采重评 → closure → Pass。基线漂移（W8）在终局前复核：DD-0003/0004 标 stale → 三出口「保持」（复核行重绑新 sha）。S6 补齐 P3 全量档义务：注册表适用谓词全目录求值（craft-guard.md 13 行）+ 五态×页面采样矩阵完整执行（10/10 格全采样，无一格未审）。

## Evidence ledger

```text
criterion: L6.1
required:  Given 导出进行中 When 查看全局状态区 Then 进行中任务有持续进度反馈（证据：交互记录）
observed:  evidence/L6.1-status-trace.json 状态区条目持续更新（30s 窗口 5 次采样）
result:    pass
note:      method=runtime-observation; scope=单次运行, viewport 1280x800
```

```text
criterion: L6.2
required:  Given 导出进行中 When 离开并返回主列表 Then 任务条目恢复显示且完成后结果可获知（证据：交互记录）
observed:  evidence/L6.2-return-trace.json 返回后条目恢复显示；完成态含结果入口（r2 重采）
result:    pass
note:      首轮 evidence/L6.2-return-first.json 失败（R3 finding），修订后重采；见 invalidated 块
```

```text
criterion: L6.3
required:  Given 导出完成 When 从状态区打开完成态条目 Then 可获得导出结果入口（证据：交互记录）
observed:  evidence/L6.3-done-entry.json 完成态条目打开结果入口
result:    pass
note:      method=runtime-observation
```

## Findings

```text
issue:    切页返回后全局状态区清空，导出结果不可获知
source:   design
fix:      DD-0004 supersedes DD-0003——任务条目持久化（返回恢复显示，含完成态入口）；Re-Fill 后失效集重评
severity: S3
track:    interaction
confidence: high
disposition: blocking
evidence:  evidence/L6.2-return-first.json（首轮返回后状态区为空）
dd:       DD-0003
```

## Positive findings

```text
issue:    全局状态区与主行动不冲突且遵循基线布局段惯例
source:   design
fix:      无需修复——正向观察（DD-0004 比较轴 2 印证）
severity: S0
track:    interaction
confidence: high
disposition: info
evidence:  evidence/L6.1-status-trace.json
```

## Coverage statement

必审: 失效集（L6.2 + 相邻主路径 L6.1/L6.3）3/3 完成；E 档两轮确认记录可溯（preview round 1/2）
采样: 状态区条目上限（10 条封顶行为）1/1 通过
采样矩阵:

- main-list/initial: evidence/L6.1-status-trace.json（上周数据默认视图入轨；状态区不渲染）
- main-list/loading: evidence/L6.1-status-trace.json（条目级进度 + 主按钮 busy——30s 窗口 5 次采样）
- main-list/success: evidence/L6.3-done-entry.json（完成态条目含结果入口）
- main-list/failure: evidence/L6.2-return-trace.json（返回后条目恢复含错误态重试出口——r2 重采）
- main-list/empty: evidence/L6.1-status-trace.json（空选择入口禁用；列表空态非白屏）
- export-dialog/initial: evidence/L6.2-return-trace.json（默认当前视图列与状态区同期入轨）
- export-dialog/loading: evidence/L6.1-status-trace.json（导出中 busy 禁重复）
- export-dialog/success: evidence/L6.3-done-entry.json（下载完成提示与状态区同步）
- export-dialog/failure: evidence/L6.2-return-first.json（首轮失败实证保留——R3 修订前后对照采样）
- export-dialog/empty: evidence/L6.1-status-trace.json（无选择时入口禁用、面板不打开）

未审: 移动端视口（契约未声明目标视口）；多任务并发（本轮单任务）
横切: a11y=applicable（role/label 已核）；响应式=applicable（1280x800）；i18n=not-applicable（单语控制台）；性能感知=applicable（进度反馈持续）；安全体验=not-applicable（无敏感操作新增）

## Limitations statement

- 判断类 advisory：无（本 run 唯一 blocking 为事实类）
- 用户代表性：无 user-test 证据，不构成「用户会」断言
- pass 范围：限单 viewport 1280x800 / 单任务 / run 内持久假设（export.task_persist_ttl）
- 机器面证明声明与事实一致，不证明体验良好

invalidated:
  - dd: DD-0003
    artifacts: [evidence/L6.2-return-first.json]
    reason: R3 挑战「状态区条目跨页保持」假设失效——DD-0004 supersedes 修订；失效集 = DD-0003 + Fill 状态区实现面 + L6.2 首轮证据；重评只跑失效集 + 相邻主路径

## Verdict

**Pass.**

- closes: 切页返回后全局状态区清空，导出结果不可获知 -> recirculate -> DD-0004 supersedes DD-0003 -> Re-Fill + 失效集重评 -> 0 blocking
