# Ops delivery log — sample spec.md

Illustrative only. Replace domain terms for your product.

## L1 定位与意图

- 一句话定义：查看某端点的 webhook 投递记录，并对失败项触发重试。
- 目标用户：集成开发者。
- 场景：日常排查投递失败；批量重试一段窗口内的失败。
- 非目标：不在此配置端点密钥；不做全站日志检索。
- 行为边界：重试 = 询问后；删除投递记录 = 永不（本页）。

## L2 信息架构

- 顶栏：端点选择、时间范围、状态筛选。
- 主区：投递列表（状态、HTTP、耗时、时间、操作）。
- 侧/展开：单次请求/响应摘要（默认脱敏）。
- 批量条：选中失败项后的重试入口。

## L3 核心链路

- pending → delivered
- pending → failed → retry → pending
- failed → ignore（仅隐藏于默认筛选，不删数据）

## L4 组件功能细节

- 状态 Badge：pending / delivered / failed。
- 行操作：查看详情、重试（loading / disabled / error）。
- 批量重试：二次确认后并行触发，逐行回写结果。

## L5 边界条件

- 空态：该端点暂无投递；说明如何触发一次测试投递。
- 加载：表结构骨架，不塌布局。
- 错误：列表拉取失败 → 原因 + 重试；单条重试失败 → 行内错误 + 可再试。
- 权限：只读角色禁用重试，并说明所需权限。

## L6 验收标准

- Given 一条 failed，When 打开详情，Then 可见状态码/错误摘要且敏感字段脱敏。
- Given 一条 failed，When 重试成功，Then 行转为 pending 且可刷新到 delivered。
- Given 无数据，Then 非白屏空态。
- Given 只读用户，Then 无法触发重试且有原因。
