# plan — 系统设置页

## 1. 本次 run 范围

- L2 主区（设置分组）+ 顶栏 + 状态区（保存/提示）。桌面优先；localStorage 持久化 demo。非目标见 spec L1。

## 2. 用户描述 → spec 映射

| ask 描述 | spec 落点 |
| --- | --- |
| 系统设置页 | L1 目标 / L2 分组 |
| 开关（深色/通知/自动更新） | L4 switch + L6.2 |
| 语言选择 | L3 + L6.3 |
| 保存/重置 | L3 + L6.4/6.5 |
| 交付页面 | 全部 L6，产物 = filled-ui.html |

未映射项：无。假设：localStorage 持久化（demo 语义）；语言预览仅头部文案（demo 范围）。

## 3. ui-picker 输入包

- scene：settings
- density：console-tight（设置分组行高紧凑）
- 约束：switch role=switch + aria-checked（L6.6）；label for 关联；保存两态（loading tier 2）；骨架与空态（L6.7）；自包含
- 排除：无账号/权限管理、无后端
- 参考 contract：无
