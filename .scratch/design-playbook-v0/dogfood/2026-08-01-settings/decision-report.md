# Decision report — 系统设置页

design-baseline: 无既有产品基线（新页面，skip，ADR-0012 N/A）
scene: settings
density: console-tight
template: 设置分组表单（main = 分组列表，top = 标题/状态，action = 保存/重置）
regions:
  - top bar: 标题「设置」+ 状态提示（status）
  - main: 设置分组（外观/通知/系统/语言；每组 label + 控件 + helper）
  - actions: 保存 + 重置按钮
components:
  - setting-row：label(for) + 控件 + helper 说明
  - switch：role=switch + aria-checked 两态（深色/通知/自动更新）
  - select：原生 select（语言）；aria-label
  - save 按钮：action；保存中禁用（loading tier 2）；重置带 confirm
  - status 提示：未保存/已保存（role=status）
  - 骨架行：loading 态
  - 空态：显式文案 + 重载
baseline-changes: none
risks:
  - 深色模式应用范围 = 页面内（demo）；真实应用需接全局主题令牌
  - localStorage 持久化在无痕/沙箱环境可能被拒（保存反馈仍即时显示）
  - 语言预览仅头部文案（demo 范围，非 i18n 基建）
