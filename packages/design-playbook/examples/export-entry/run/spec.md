<!-- spec-schema: 2 -->

# 数据导出入口 交互设计 Spec

Produced by **ux-spec** through a full P2 shaping session (S0-S6; see `shaping/shaping-log.jsonl`). Six decisions (D-0001…D-0006) and four acknowledged assumptions are projected from the persistent contract.

## L1 定位与意图

- 用户可见目标：支持运营完成周报所需的数据导出——在主列表行内批量导出上周数据为 CSV。
- 目标用户：运营角色，周频导出上周数据做周报。
- 场景清单：首场景 = 运营周报（假设，契约字段 `l1.scenes`，回退：单场景）。
- 非目标：不做定时/周期导出；不做全量历史导出。
- 行为边界：始终 = 行内批量导出当前视图列；询问后 = 超上限导出确认；永不 = 导出隐藏敏感列（`export.column_scope` 假设：当前视图列含隐藏列开关）。

## L2 信息架构

- 空间区域定义：主列表区（行选择 + 行内批量导出入口）、导出选项面板（列范围/格式）、页面级提示区（toast）。
- 区域边界规则：导出入口仅存在于主列表行选择工具条；不新增全局工具栏入口。
- 内容生长规则：列表增长仅纵向滚动；导出面板固定宽度。

### Page duties

| Page | Duty |
| --- | --- |
| main-list | 运营浏览与圈选上周数据，发起行内批量导出 |
| export-dialog | 确认列范围与规模，承载超限提示与导出确认 |

## L3 核心链路

- 状态清单：idle → selecting → export-open → exporting → done / cap-blocked。
- 主链路：main-list 选定范围 → export-dialog 确认 → exporting → done（下载完成）。
- 分支链路：选定超上限 → cap-blocked（提示剩余量与收窄建议）；导出中离开返回 → 进度保持可获知。

### Paths

| Path | Steps |
| --- | --- |
| P1 | main-list 选定上周范围 → 打开 export-dialog → 确认导出 → exporting → done（限时内获得 CSV） |
| P2 | main-list 选定超上限范围 → 打开 export-dialog → 触发超限提示 → 收窄建议 |
| P3 | exporting 中离开 main-list → 返回 → 进度/结果仍可获知 |

## L4 组件功能细节

- 行选择工具条：批量导出按钮（唯一主行动）；导出进行中置 busy 且禁用重复触发（S2 finding 修复项）。
- 导出选项面板：列范围开关（当前视图列，含隐藏列开关）、格式固定 CSV。
- 页面级提示（toast）：超限提示需 role=alert 与可读名称（含超限数值）（S3 finding 修复项）。

L4 declares control behavior only; reuse / no-internal-change constraints must name exceptions (for example, allow a minimal patch when they conflict with L5).

## L5 边界条件

- 空态：无选择时批量导出入口禁用并说明原因。
- 加载态：列表骨架；导出中按钮 busy 态。
- 错误态：超上限 → 提示剩余量与「按周导出」收窄建议；导出失败 → 原因 + 重试。
- 权限降级：viewer 角色禁用导出并说明。

### Five-state matrix

| Page | initial | loading | success | failure | empty |
| --- | --- | --- | --- | --- | --- |
| main-list | 上周数据默认视图 | 列表骨架 | 行选择 + 导出入口可用 | 服务不可达：原因 + 重试 | 空列表：非白屏空态 + CTA |
| export-dialog | 默认当前视图列 | 导出中 busy 禁重复 | 下载完成提示 | 超限提示（role=alert）/ 失败原因 + 重试 | 无选择时入口禁用（面板不打开） |

## L6 验收标准

- Given 运营在主列表选定上周范围 When 触发行内批量导出 Then 30 秒内获得 CSV 且行数与选中范围一致（证据：交互记录）(path: P1)
- Given 选定范围超过 20 万行 When 确认导出 Then 提示剩余量与收窄建议（证据：错误态截图 capture seed）(path: P2)
- Given 导出进行中 When 用户离开并返回该页 Then 导出进度与结果仍可获知（证据：交互记录）(path: P3)

