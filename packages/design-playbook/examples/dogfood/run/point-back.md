# Point-back — 队列监控升级（P3 全量档 dogfood，R3 重入 + R4 回流 + 基线漂移复核）

Six-block report (final state). Round 1: 2 条 blocking——R3（interaction 轨，dd: DD-0001 挑战「feed 跨页保持」假设）与 R4（a11y 事实类：全局暂停按钮无名无 role）→ Recirculate → DD-0002 supersedes 修订 + a11y 修复 → Re-Fill → 失效集重采重评 → closure → Pass。基线漂移（W8）在终局前复核：DD-0001/0002 标 stale → 三出口「保持」（复核行重绑新 sha）。P3 全量档义务：注册表适用谓词全目录求值（craft-guard.md 13 行）+ 五态×页面采样矩阵完整执行（10/10 格全采样）+ 方法语义五键入 manifest。

## Evidence ledger

```text
criterion: L6.1
required:  Given 模拟运行进行中 When 离开并返回队列页 Then 全局控制台运行 feed 恢复显示且状态可续读（证据：交互记录）
observed:  evidence/L6.1-return-trace.json 返回后 feed 恢复显示（sim-0042 running 74%）；完成态含结果入口（r2 重采）
result:    pass
note:      method=runtime-observation; scope=单次运行, viewport 1280x800; 首轮 evidence/L6.1-return-first.json 失败（R3 finding），修订后重采；见 invalidated 块
```

```text
criterion: L6.2
required:  Given 多运行并发 When 在全局控制台触发全局暂停 Then 进行中运行进入 paused 且控制台持续反馈（证据：交互记录）
observed:  evidence/L6.2-pause-trace.json 3 条 running 转 paused；计数持续更新；按钮 role=button + 可访问名（r2 重采，R4 修复后）
result:    pass
note:      method=runtime-observation; 首轮 a11y 缺口见 R4 finding，已闭合
```

```text
criterion: L6.3
required:  Given 控制台 feed 达到上限 When 新运行入队 Then 最旧完成条目让位且失败项不静默丢失（证据：交互记录）
observed:  evidence/L6.3-cap-trace.json 最旧完成条目让位；失败项保留；完成态结果入口可打开
result:    pass
note:      method=runtime-observation
```

## Findings

```text
issue:    切页返回后全局控制台 feed 清空，运行状态不可续读
source:   design
fix:      DD-0002 supersedes DD-0001——feed 条目持久化（返回恢复显示，含完成态入口与上限治理）；Re-Fill 后失效集重评
severity: S3
track:    interaction
confidence: high
disposition: blocking
route:     R3
evidence:  evidence/L6.1-return-first.json（首轮返回后 feed 为空）
dd:       DD-0001
```

```text
issue:    全局暂停按钮无可访问名称与 role，辅助技术不可操作
source:   filled-ui
fix:      补 role=button 与可访问名称「全局暂停所有进行中模拟」；busy 态禁重复；修复后 a11y 复走查重采
severity: S3
track:    product
confidence: high
disposition: blocking
route:     R4
evidence:  evidence/L6.2-pause-first.json（首轮 a11y 树节点无名无 role）
```

```text
issue:    控制台汇总计数或增加巡检时的扫读负担，疑与侧区失败趋势信息重复
source:   spec L2
fix:      呈报用户三选一（改声明/接受风险/提交晋升队列）；本轮按显式未审记录，不产生 pass 贡献
severity: S2
track:    interaction
dimension: task-organization
face:     subjective
basis:    agent-judgment
confidence: low
disposition: advisory
evidence:  rendered 走查（agent-judgment, method=expert-review）；非用户证据
```

## Positive findings

```text
issue:    全局控制台与主列表不冲突且遵循基线布局段其余惯例（分区无框/层级令牌）
source:   design
fix:      无需修复——正向观察（DD-0002 比较轴 2 印证）
severity: S0
track:    interaction
confidence: high
disposition: info
evidence:  evidence/L6.1-return-trace.json
```

## Coverage statement

必审: 失效集（L6.1 + L6.2）+ 相邻主路径（L6.3）3/3 完成；E 档两轮确认记录可溯（preview round 1/2）
采样: feed 上限让位行为（12 条封顶）1/1 通过
采样矩阵:

- run-queue/initial: evidence/L6.1-return-trace.json（返回后按持久化状态恢复入轨）
- run-queue/loading: evidence/L6.2-pause-trace.json（feed 条目级进度 + 全局暂停 busy）
- run-queue/success: evidence/L6.3-cap-trace.json（完成态条目含结果入口）
- run-queue/failure: evidence/L6.2-pause-trace.json（暂停失败 toast role=alert 负路径 + 条目错误态重试）
- run-queue/empty: evidence/L6.1-return-trace.json（无运行时 feed 不渲染——空轨确认）
- sim-detail/initial: evidence/L6.3-cap-trace.json（运行明细默认入轨）
- sim-detail/loading: evidence/L6.2-pause-trace.json（明细条目级进度）
- sim-detail/success: evidence/L6.3-cap-trace.json（资源占用图表呈现）
- sim-detail/failure: evidence/L6.2-pause-first.json（失败原因 + 重试/中止——首轮轨含失败条目）
- sim-detail/empty: evidence/L6.1-return-trace.json（无该运行：返回入口）

未审: 移动端视口（契约未声明目标视口）；多工作台并发（本轮单工作台）；控制台计数与侧区趋势的信息重复度（判断类 S2 advisory——呈报用户，不产生 pass 贡献）
横切: a11y=applicable（role/label 已核，R4 闭合）；响应式=applicable（1280x800）；i18n=not-applicable（单语控制台，无 i18n 声明）；性能感知=applicable（feed 进度 + 暂停 busy 持续反馈）；安全体验=not-applicable（敏感参数脱敏沿用，无敏感操作新增）

## Limitations statement

- 判断类 advisory：1 条（task-organization 主观面，agent-judgment 低置信）——不构成 blocking，已呈报
- 用户代表性：无 user-test 证据，不构成「用户会」断言
- pass 范围：限单 viewport 1280x800 / 单工作台 / run 内持久假设（sim.control_scope、sim.max_parallel）
- 机器面证明声明与事实一致，不证明体验良好

invalidated:
  - dd: DD-0001
    artifacts: [evidence/L6.1-return-first.json, evidence/L6.2-pause-first.json]
    reason: R3 挑战「控制台 feed 跨页保持」假设失效——DD-0002 supersedes 修订；失效集 = DD-0001 + Fill 控制台实现面 + L6.1 首轮证据（a11y 首轮证据由 R4 修复路径重采）；重评只跑失效集 + 相邻主路径

## Verdict

**Pass.**

- closes: 切页返回后全局控制台 feed 清空，运行状态不可续读 -> recirculate -> DD-0002 supersedes DD-0001 -> Re-Fill + 失效集重评 -> 0 blocking
- closes: 全局暂停按钮无可访问名称与 role，辅助技术不可操作 -> recirculate -> R4 修复（role=button + 可访问名）+ a11y 复走查重采 -> 0 blocking
