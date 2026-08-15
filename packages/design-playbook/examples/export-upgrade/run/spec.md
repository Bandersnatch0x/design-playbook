<!-- spec-schema: 2 -->

# 导出升级（全局数据任务中心第一步）交互设计 Spec

P3 全量档 run：修订既有 decided（l1.goal supersedes D-0008）+ region 构成变更（E 档 DD-0003/0004）。成形会话见 shaping/shaping-log.jsonl。

## L1 定位与意图

- 用户可见目标：把导出升级为全局数据任务中心的第一步——导出任务全程可见、跨页保持、结果可获知。
- 目标用户：运营角色，周频导出上周数据做周报。
- 场景清单：运营周报（l1.scenes 假设延续）。
- 非目标：不做定时/周期导出；不做全量历史导出（沿用既有 decided）。
- 行为边界：始终 = 行内批量导出当前视图列；询问后 = 超上限导出确认；永不 = 导出隐藏敏感列。

## L2 信息架构

- 空间区域定义：主列表区（行选择 + 行内批量导出入口）、全局状态区（导出任务 feed：进行中/最近完成，跨视图持久）。
- 区域边界规则：状态区只收纳导出任务；feed 上限 10 条（本轮）。
- 内容生长规则：列表增长仅纵向滚动；状态区条目固定高度。

### Page duties

| Page | Duty |
| --- | --- |
| main-list | 运营浏览与圈选上周数据，发起导出；全局状态区呈现任务进度与结果入口 |
| export-dialog | 确认列范围与规模，承载超限提示与导出确认 |

## L3 核心链路

- 状态清单：idle → selecting → export-open → exporting → done / cap-blocked。
- 主链路：main-list 选定范围 → export-dialog 确认 → exporting（状态区可见）→ done（完成态入口）。
- 分支链路：导出中切页/返回 → 状态区条目恢复显示；超上限 → cap-blocked。

### Paths

| Path | Steps |
| --- | --- |
| P1 | main-list 选定上周范围 → 确认导出 → exporting（全局状态区持续进度） |
| P2 | exporting 中离开 main-list → 返回 → 状态区条目恢复显示且完成后结果可获知 |
| P3 | 导出完成 → 状态区完成态条目 → 打开导出结果 |

## L4 组件功能细节

- 全局状态区：任务条目（进度/完成态）；进行中主按钮 busy 禁重复。
- 完成态条目：结果入口（下载/查看）；条目生命周期受 export.task_persist_ttl 假设约束。

L4 declares control behavior only; reuse / no-internal-change constraints must name exceptions (for example, allow a minimal patch when they conflict with L5).

## L5 边界条件

- 空态：无任务时状态区不渲染（不留空白面板）。
- 加载态：条目级进度；按钮 busy 态。
- 错误态：导出失败 → 条目错误态 + 重试；超上限走 toast。
- 权限降级：viewer 角色禁用导出并说明。

### Five-state matrix

| Page | initial | loading | success | failure | empty |
| --- | --- | --- | --- | --- | --- |
| main-list | 上周数据默认视图（状态区不渲染） | 条目级进度 + 按钮 busy | 完成态条目含结果入口 | 条目错误态 + 重试 | 空列表：非白屏空态 + CTA |
| export-dialog | 默认当前视图列 | 导出中 busy 禁重复 | 下载完成提示（状态区同步） | 超限提示（role=alert）/ 失败原因 + 重试 | 无选择时入口禁用（面板不打开） |

## L6 验收标准

- Given 导出进行中 When 查看全局状态区 Then 进行中任务有持续进度反馈（证据：交互记录）(path: P1)
- Given 导出进行中 When 离开并返回主列表 Then 任务条目恢复显示且完成后结果可获知（证据：交互记录）(path: P2)
- Given 导出完成 When 从状态区打开完成态条目 Then 可获得导出结果入口（证据：交互记录）(path: P3)
