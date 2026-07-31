# Decision report — 事件流监控页

design-baseline: 无既有产品基线（新页面，skip，ADR-0012 N/A）
scene: list / timeline（事件流）
density: console-tight
template: 列表 + 内联展开（main = 事件列表，top = 控制条，status = 计数徽章）
regions:
  - top bar: 标题 + 暂停/恢复按钮（action）+ 级别筛选（radio-group）+ 计数徽章（status）
  - main: 事件列表（event-row 组件，新事件顶部追加）
  - detail: 行内展开（inline expansion，非 Drawer——细读上下文需保持列表在场）
components:
  - event-row：列表行；关键级左侧警示条 + severity-badge（色+文本双编码）
  - severity-badge：status 角色（critical=红/warning=琥珀/info=灰）
  - pause 按钮：两态（暂停/恢复）aria-pressed；流停止时文本「恢复」
  - filter 组：radio-group 语义（全部/关键/警告/信息）
  - counter 徽章：status（总数 + 关键数）
  - 骨架行：loading 态
  - 空态：显式文案 + 刷新按钮
baseline-changes: none
risks:
  - 模拟流定时器在 headless 捕获中可能追加事件（确定性：暂停态捕获固定帧）
  - 徽章色觉：已用色+文本双编码（L6.2）
  - 无真数据源 → demo 事件数据（产品集成时换真流）
