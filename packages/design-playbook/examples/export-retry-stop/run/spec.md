<!-- spec-schema: 2 -->

# 重试按钮无响应修复 交互设计 Spec

Base: the shipped retry-and-return spec (prior run, unchanged — this P1 run is read-only on the spec). Reproduced here as the run-root evidence seam.

## L1 定位与意图

- 用户可见目标：支持运营导出失败后可靠重试并保持进度可见。
- 目标用户：运营角色，导出任务失败后重试完成周报。
- 非目标：不做定时重试；不做全量历史任务列表。
- 行为边界：始终 = 手动重试当前失败任务；询问后 = 无；永不 = 自动静默重试。

## L2 信息架构

- 空间区域定义：主列表区（任务与失败态行内重试入口）、页面级提示区（toast）。
- 区域边界规则：重试入口仅存在于失败任务行；不新增全局重试工具栏。
- 内容生长规则：列表增长仅纵向滚动。

### Page duties

| Page | Duty |
| --- | --- |
| main-list | 运营查看导出任务状态，从失败行发起重试 |
| export-dialog | 无修复面（本 run 未触碰） |

## L3 核心链路

- 状态清单：idle → exporting → failed → retrying → done。
- 主链路：exporting → failed（原因 + 重试）→ retrying → done。
- 分支链路：导出中离开返回 → 进度保持可获知。

### Paths

| Path | Steps |
| --- | --- |
| P1 | main-list 导出失败 → 点击行内重试 → retrying → done（30 秒内重新发起并显示进度） |
| P2 | exporting 中离开 main-list → 返回 → 进度/结果仍可获知 |

## L4 组件功能细节

- 失败任务行：重试按钮（行内、显式文字 + 图标）；重试中置 busy 并禁重复触发。
- 页面级提示（toast）：失败原因 + 重试结果提示需可读名称。

## L5 边界条件

- 空态：无任务时列表空态 + CTA。
- 加载态：列表骨架；重试中按钮 busy 态。
- 错误态：导出失败 → 原因 + 重试；重试再失败 → 原因 + 重试（退避提示）。
- 权限降级：viewer 角色只读，重试禁用并说明。

### Five-state matrix

| Page | initial | loading | success | failure | empty |
| --- | --- | --- | --- | --- | --- |
| main-list | 上周任务默认视图 | 列表骨架 | 任务完成态含结果入口 | 导出失败：原因 + 重试 | 无任务：非白屏空态 + CTA |
| export-dialog | n/a（本 run 未触碰） | n/a | n/a | n/a | n/a |

## L6 验收标准

- Given 导出失败 When 点击重试 Then 30 秒内重新发起导出并显示进度（证据：交互记录）(path: P1)
- Given 导出进行中 When 离开并返回该页 Then 导出进度与结果仍可获知（证据：交互记录）(path: P2)
