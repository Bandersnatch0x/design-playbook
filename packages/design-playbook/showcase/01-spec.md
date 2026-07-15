# Spec - SwarSight simulation run queue

Produced by **ux-spec**. Domain grounded in SwarSight `DESIGN.md` + `WorkbenchPage` (simulation control: start/pause/resume/stop; scenarios; entities; decision audit).

## L1 定位与意图

- 一句话定义：查看所有模拟运行的实时状态、失败重试与资源占用的队列监控页。
- 目标用户：运维分析师、场景设计者。
- 场景：日常监控在跑模拟；失败批量重试；资源异常定位。
- 非目标：不在此编辑场景；不承载完整决策审计（在 Workbench）。
- 行为边界：重试 = 询问后；中止运行中模拟 = 询问后；查看明文敏感参数 = 永不（默认脱敏）。

## L2 信息架构

- 顶栏：运行中 / 失败 / 排队 / 已完成 计数 + 时间窗筛选。
- 主区：运行列表（状态、场景名、触发人、耗时、资源占用、操作）。
- 侧区：失败趋势、队列压力、最近失败原因。
- 操作条：批量重试、批量中止（选中后浮现）。

## L3 核心链路

- queued -> running -> completed
- running -> paused -> running
- running -> failed -> retry -> queued
- running -> failed -> aborted
- running -> timeout -> retry / abort

## L4 组件功能细节

- 状态 Badge：queued / running / paused / failed / completed / aborted / timeout。
- 行操作：查看详情（Drawer）、重试、中止。
- 资源占用：mini sparkline（CPU/内存），只读。
- 批量条：选中失败项 -> 批量重试（二次确认）。

## L5 边界条件

- 空态：无运行 -> 「还没有模拟运行」+ 创建场景入口（非白屏）。
- 加载态：表结构骨架（SwarSight Abyss Canvas 底，不塌布局）。
- 错误态：模拟服务不可达 -> 原因 + 重试；单条重试失败 -> 行内错误 + 可再试。
- 权限降级：viewer 角色禁用重试/中止，tooltip 说明所需权限。

## L6 验收标准

- Given 一条 failed，When 展开详情，Then 可见失败原因 + 资源峰值，且可触发重试。
- Given 一条 failed，When 重试成功，Then 行转 queued 并可刷新到 running/completed。
- Given 无运行，Then 非白屏空态 + CTA。
- Given viewer，Then 重试/中止不可执行且有原因。
- Given 批量重试，Then 二次确认 + 后果文案后才执行。
