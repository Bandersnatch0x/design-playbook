# Point-back — 数据导出入口（P2 标准 run，含一轮 Recirculate）

Six-block report (final state after one repair round). Round 1: 1 条 a11y blocking（S3 事实类）→ Recirculate → R4 修复 + invalidated 登记 → 重采重评 → closure → Pass。L6.3 首轮采集 blocked（R5 证据计划修复后重采）。S3 扩展：交互轨七维标注（system-response 客观面 / task-organization 主观面各一条）、五态×页面采样矩阵（6 格采样 + 4 格显式未审）、manifest 方法语义五键（L6.1 附涉人 user-test 负例：ethics 缺失被隔离为 blocked 证据）。

## Evidence ledger

```text
criterion: L6.1
required:  Given 运营在主列表选定上周范围 When 触发行内批量导出 Then 30 秒内获得 CSV 且行数与选中范围一致（证据：交互记录）
observed:  evidence/L6.1-export-trace.json 14.2s 完成，214/214 行；单次触发（R4 修复后 busy 态防重复）
result:    pass
note:      method=runtime-observation; scope=单次运行, viewport 1280x800, 数据集 week-2026-32
```

```text
criterion: L6.2
required:  Given 选定范围超过 20 万行 When 确认导出 Then 提示剩余量与收窄建议（证据：错误态截图 capture seed）
observed:  evidence/L6.2-cap-error-r2.png 提示含「超出 200,000 行上限」与「按周导出」建议；重评基于 r2 证据
result:    pass
note:      assumes=export.row_cap；L6.2-a11y-tree-r2.json 印证 toast role=alert 与可读名称
```

```text
criterion: L6.3
required:  Given 导出进行中 When 用户离开并返回该页 Then 导出进度与结果仍可获知（证据：交互记录）
observed:  evidence/L6.3-return-trace.json 返回后 exporting 态可见、完成后结果可见（R5 修订 capture plan 后重采）
result:    pass
note:      method=runtime-observation；首轮 provider 跨导航 session 丢失记 blocked，见 invalidated 块
```

## Findings

```text
issue:    超限提示 toast 无可访问名称与 role=alert，屏幕阅读器用户无法感知导出失败原因
source:   spec L6.2 + components
fix:      toast 增加 role=alert 与可读名称（含超限数值）；组件语义入 components 声明
severity: S3
track:    cross-cutting
confidence: high
disposition: blocking
evidence:  evidence/L6.2-a11y-tree.json（toast 节点无名无 role）
rule:      A11Y-01@1
```

```text
issue:    导出进行中触发按钮无 busy/disabled 状态，可重复触发并发导出
source:   spec L4
fix:      导出进行中置 busy 并禁重复触发，完成后恢复；补 L4 状态行
severity: S2
track:    interaction
dimension: system-response
face:     objective
basis:    machine-reproducible
confidence: high
disposition: advisory
evidence:  evidence/L6.1-export-trace.json 首轮轨迹显示 2 次连续触发；src/Console/ExportButton.tsx:42
```

```text
issue:    导出选项「定界符/编码」术语疑超出运营角色的任务语言，或增加无谓决策负担
source:   spec L1（目标用户）+ L4
fix:      将高级选项折叠为「高级」默认收起；术语适配待用户研究确认（呈报用户三选一：改声明/接受风险/提交晋升队列）
severity: S2
track:    interaction
dimension: task-organization
face:     subjective
basis:    agent-judgment
confidence: low
disposition: advisory
evidence:  rendered 走查（agent-judgment, method=expert-review）；非用户证据——evidence/L6.1-usertest-notes.md 仅为合成 schema 示例，未登记到 Manifest，不能支持判断
```

## Positive findings

```text
issue:    主路径导出闭环在限时内完成且行数一致
source:   spec L6.1
fix:      无需修复——正向观察；AC 级正向即 ledger pass 行，此处汇总引用
severity: S0
track:    product
confidence: high
disposition: info
evidence:  evidence/L6.1-export-trace.json（跨层：交互轨迹 + 度量计时印证）
```

## Coverage statement

必审: 主路径 4/4 节点完成（P1 全程、P2 超限、P3 返回、导出错误态）；L6.3 首轮采集 blocked（覆盖缺口→R5，重采后完成）
采样: 边缘 2/2——空选择导出（发现：L5 未建模该边缘态，已按 R2 补五态行）；超时中断（通过，证据 evidence/edge-timeout.png，理由=高频中断风险）

采样矩阵:

- main-list/initial: evidence/L6.1-export-trace.json（上周数据默认视图入轨）
- main-list/loading: 未审（骨架态未单独采集——高频低风险，R2 待补采样）
- main-list/success: evidence/L6.1-export-trace.json（行选择 + 导出入口可用）
- main-list/failure: evidence/edge-timeout.png（超时中断采样通过）
- main-list/empty: 未审（空选择入口禁用由 L5 行声明覆盖——静态走查确认，未采运行时证据）
- export-dialog/initial: 未审（默认当前视图列与 main-list/initial 同源——未单独采集）
- export-dialog/loading: evidence/L6.1-export-trace.json（导出中 busy 禁重复，R4 修复后）
- export-dialog/success: evidence/L6.1-export-trace.json（下载完成提示）
- export-dialog/failure: evidence/L6.2-cap-error-r2.png（超限提示 role=alert，重评 r2 证据）
- export-dialog/empty: 未审（无选择时入口禁用、面板不打开——无采集面）

未审: 移动端视口（契约未声明目标视口——已立 finding 回流 D1/D2；未审项不产生 pass 贡献）
横切: a11y=applicable（1 条 blocking 已闭合）；响应式=applicable（1280x800 已采）；i18n=not-applicable（单语控制台，无 i18n 声明）；性能感知=blocked（provider 缺度量面，登记为 craft proof gap）；安全体验=not-applicable（无敏感操作新增）

## Limitations statement

- 判断类 advisory：术语适配（task-organization 主观面，agent-judgment 非用户证据，confidence=low，advisory 不阻 verdict）
- 用户代表性：本 run 无真实 user-test evidence；合成 notes 未登记到 Manifest，全部结论不构成任何「用户会」断言
- pass 范围：L6.1/L6.2/L6.3 pass 限单 viewport 1280x800 / 单数据集 week-2026-32 / 单次运行
- assumed 依赖：L6.2 pass 依赖 export.row_cap 假设成立
- 机器面证明声明与事实一致，不证明体验良好

invalidated:
  - criterion: L6.2
    artifacts: [evidence/L6.2-cap-error.png, evidence/L6.2-a11y-tree.json]
    reason: R4 修复 toast 后 observed UI 变化，重采 r2 证据（最新 manifest 条目胜）
  - criterion: L6.3
    artifacts: []
    reason: 首轮 provider 跨导航 session 丢失（blocked，非实现缺陷）；R5 修订 capture plan 后重采

## Verdict

**Pass.**

- closes: 超限提示 toast 无可访问名称与 role=alert，屏幕阅读器用户无法感知导出失败原因 -> recirculate -> fix -> re-eval -> 0 blocking
