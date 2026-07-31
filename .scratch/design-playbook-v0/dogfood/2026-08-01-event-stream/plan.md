# plan — 事件流监控页

## 1. 本次 run 范围

- L2 主区（事件列表）+ 详情展开 + 顶栏（暂停/筛选）+ 状态区（计数）。
- 桌面优先；模拟流前端实现（demo 语义，无后端）。非目标见 spec L1。

## 2. 用户描述 → spec 映射

| ask 描述 | spec 落点 |
| --- | --- |
| 事件流监控页 | L1 目标 / L2 主区列表 |
| 级别徽章（critical/warning/info） | L4 severity-badge + L6.2 |
| 暂停/恢复 | L3 链路 + L6.4 |
| 筛选 | L3 + L6.5 |
| 详情 | L3 + L6.3 |
| 交付页面 | 全部 L6，产物 = filled-ui.html |

未映射项：无。假设：模拟流用前端定时器追加（demo 数据 12 条起 + 追加），来源字段示例值。

## 3. ui-picker 输入包

- scene：list / timeline（事件流）
- density：console-tight（监控页信息密度高，行高紧凑）
- 约束：severity 双编码（色+文本，L6.2）；暂停两态 aria-pressed（L6.6）；骨架与空态（L6.7）；自包含无外部依赖
- 排除：无后端推送、无告警规则编辑、不做图表
- 参考 contract：无
