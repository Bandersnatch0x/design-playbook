<!-- spec-schema: 2 -->

# 队列监控升级（全局模拟运行中心第一步）交互设计 Spec

P3 全量档 run：修订既有 decided（l1.goal supersedes D-0008）+ region 构成变更（E 档 DD-0001/0002）。成形会话见 shaping/shaping-log.jsonl。Dogfood 目标面 = 本仓库 showcase 的 SwarSight 模拟运行队列监控页。

## L1 定位与意图

- 用户可见目标：把队列监控页升级为全局模拟运行中心的第一步——运行状态跨页可查、全局控制可用、失败可批量治理。
- 目标用户：运维分析师（周频巡检 + 事件响应）、场景设计者。
- 场景清单：日常监控在跑模拟；失败批量重试；资源异常定位（l1.scenes 假设延续）。
- 非目标：不在此编辑场景；不承载完整决策审计（在 Workbench）。
- 行为边界：始终 = 展示运行状态与资源占用；询问后 = 全局暂停/恢复、批量重试、中止运行中模拟；永不 = 明文展示敏感模拟参数（默认脱敏）。

## L2 信息架构

- 空间区域定义：全局运行控制台（running/paused/failed 汇总 + 运行 feed：进行中/最近完成，跨视图持久 + 全局暂停/恢复）、主列表区（运行列表 + 行选择）、侧区（失败趋势、队列压力、最近失败原因）。
- 区域边界规则：控制台只收纳模拟运行 feed 与全局控制；feed 上限 12 条（本轮）；批量操作条并入控制台（选中后浮现）。
- 内容生长规则：列表与 feed 增长仅纵向滚动；feed 条目固定高度。

### Page duties

| Page | Duty |
| --- | --- |
| run-queue | 运维浏览运行列表、圈选失败条目批量重试；全局运行控制台呈现 feed 进度与全局控制 |
| sim-detail | 单条运行的失败原因、重试与中止、资源占用明细 |

## L3 核心链路

- 状态清单：queued → running → completed；running → paused → running；running → failed → retry → queued；running → timeout → retry/abort。
- 主链路：run-queue 巡检 → 控制台 feed 读运行进度 → 失败条目圈选 → 批量重试 → queued 可见。
- 分支链路：全局暂停 → running 全部转 paused（手动单次重试除外，sim.control_scope 假设）；feed 达上限 → 最旧完成条目让位。

### Paths

| Path | Steps |
| --- | --- |
| P1 | run-queue 运行进行中 → 离开 → 返回 → 控制台 feed 恢复显示且状态可续读 |
| P2 | 多运行并发 → 控制台触发全局暂停 → running 转 paused 且控制台持续反馈 |
| P3 | feed 达上限 → 新运行入队 → 最旧完成条目让位且失败项不静默丢失 |

## L4 组件功能细节

- 全局运行控制台：汇总计数（running/paused/failed）+ 运行 feed（进度/完成态）；全局暂停/恢复按钮（含可访问名称与 role）。
- 运行 feed 条目：进度/完成态；完成态含结果入口；条目生命周期受 sim.control_scope 与上限治理约束。
- 批量操作条：选中失败条目后浮现（重试/中止）；破坏性动作保留显式文字。

L4 declares control behavior only; reuse / no-internal-change constraints must name exceptions (for example, allow a minimal patch when they conflict with L5).

## L5 边界条件

- 空态：无运行时控制台 feed 不渲染（不留空白面板）；列表空态非白屏 + CTA。
- 加载态：feed 条目级进度；批量动作 busy 态。
- 错误态：运行失败 → 条目错误态 + 重试；全局暂停失败 → toast（role=alert）。
- 权限降级：viewer 角色禁用全局控制并说明。

### Five-state matrix

| Page | initial | loading | success | failure | empty |
| --- | --- | --- | --- | --- | --- |
| run-queue | 当日默认视图（控制台 feed 按持久化状态恢复） | feed 条目级进度 + 批量动作 busy | 完成态条目含结果入口 | 条目错误态 + 重试 | 空列表：非白屏空态 + CTA；feed 不渲染 |
| sim-detail | 运行默认明细 | 明细加载条目级进度 | 明细含资源占用图表 | 失败原因 + 重试/中止 | 无该运行：返回入口 |

## L6 验收标准

- Given 模拟运行进行中 When 离开并返回队列页 Then 全局控制台运行 feed 恢复显示且状态可续读（证据：交互记录）(path: P1)
- Given 多运行并发 When 在全局控制台触发全局暂停 Then 进行中运行进入 paused 且控制台持续反馈（证据：交互记录）(path: P2)
- Given 控制台 feed 达到上限 When 新运行入队 Then 最旧完成条目让位且失败项不静默丢失（证据：交互记录）(path: P3)
