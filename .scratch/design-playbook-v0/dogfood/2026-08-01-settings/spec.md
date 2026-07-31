# 系统设置页 交互设计 Spec

Produced by **ux-spec**（design-playbook 管道 dogfood，2026-08-01）。

## L1 定位与意图

- 一句话定义：应用系统设置页——偏好开关（深色模式、桌面通知、自动更新）与语言选择的集中管理；变更即时生效并有保存反馈。
- 目标用户：应用终端用户；无登录。
- 场景：偏好开关切换、语言选择、保存/重置。
- 非目标：不做账号/权限管理、不做后端持久化（demo 用 localStorage）、不做移动端深度适配。
- 行为边界：开关切换 = 即时生效（无需确认）；保存 = 显式按钮 + 成功反馈；重置 = 确认后恢复默认；语言选择 = 下拉 + 即时预览文案变化（demo 范围）。

## L2 信息架构

- 顶栏：标题「设置」+ 保存状态提示。
- 主区：设置分组（外观：深色模式开关；通知：桌面通知开关；系统：自动更新开关；语言：选择器）。
- 状态区：保存按钮 + 保存成功/未保存标记。
- 设置行：label + 控件 + 辅助说明。

## L3 核心链路

- 进入页面 → 设置项渲染（当前值）→ 浏览。
- 切换开关 → 值更新 + 「未保存」标记出现。
- 选择语言 → 预览文案切换（demo 局部）。
- 点击保存 → localStorage 持久化 + 「已保存」反馈。
- 点击重置 → 确认 → 恢复默认 + 未保存标记。

## L4 组件功能细节

- 设置行（setting-row）：label（含 for）+ 控件 + helper 说明；键盘可达。
- 开关（switch）：role="switch" + aria-checked 两态；键盘 Space 切换。
- 语言选择（select）：原生 select；aria-label。
- 保存按钮：action；保存中禁用（loading tier 2）。
- 状态提示：status 角色（未保存/已保存）。

## L5 边界条件

- **空态**：设置项全缺时显示「暂无设置项」+ 重载；非空白。
- **加载态**：初始骨架行占位。
- **错误态**：保存失败显示错误文案 + 重试。
- **权限态**：无权限要求；N/A。
- 每态给出下一步。

## L6 验收标准

- **L6.1 首屏渲染（Given -> When -> Then）**：Given 打开页面 When 加载完成 Then 显示设置分组（外观/通知/系统/语言），非空白，证据 = 首屏截图（capture seed: `ready-state screenshot`）。
- **L6.2 开关切换（Given -> When -> Then）**：Given 深色模式开关 When 点击 Then aria-checked 翻转 + 页面应用深色类 + 「未保存」出现，证据 = 交互 trace。
- **L6.3 语言选择（Given -> When -> Then）**：Given 语言下拉 When 选择 When → 选择值更新 + 预览文案变化，证据 = 交互 trace。
- **L6.4 保存反馈（Given -> When -> Then）**：Given 变更后 When 点击保存 Then 状态变「已保存」且 localStorage 持久化，证据 = 交互 trace。
- **L6.5 重置确认（Given -> When -> Then）**：Given 已变更 When 点击重置 Then 出现确认（confirm 对话框）且确认后恢复默认，证据 = 交互 trace。
- **L6.6 可访问性（Given -> When -> Then）**：Given a11y 树 When 检查 Then 每开关 role=switch + 可访问名、label 关联、select 有名字，证据 = a11y 树（capture seed: `a11y tree`）。
- **L6.7 空态（Given -> When -> Then）**：Given 设置项缺失 When 渲染 Then 显示「暂无设置项」非空白，证据 = 状态截图（capture seed: `empty-state screenshot`）。

每项声明证据类型（截图 / 交互 trace / a11y 树），runtime 状态命名 capture seed。
