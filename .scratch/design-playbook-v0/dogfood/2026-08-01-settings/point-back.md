# Point-back findings — 系统设置页

Produced by **ui-evaluator** after Design I/O (ux-spec → plan → ui-picker → preview* → fill → craft-guard → observe* → eval)。Run root: .scratch/design-playbook-v0/dogfood/2026-08-01-settings/

## Evidence ledger (L6)

criterion: L6.1
required: 首屏渲染设置分组（外观/通知/系统/语言），非空白；证据 = 首屏截图
observed: evidence/L6.1-ready.png
note: provider 捕获（observed_state=ready，wait_for_state=ready 后采；首轮 700ms 骨架窗 captured loading 已重采）；surface: live
result: pass

criterion: L6.2
required: 深色开关点击 → aria-checked 翻转 + 页面应用深色类 + 「未保存」；证据 = 交互 trace
observed: evidence/L6.2-switch.zip
note: provider interaction trace（click #dark）；playwright 复验 aria-checked=true + body.dark 应用
result: pass

criterion: L6.3
required: 语言选择 → 值更新 + 预览文案变化；证据 = 交互 trace
observed: evidence/L6.3-lang.zip
note: provider interaction trace（select_option English）
result: pass

criterion: L6.4
required: 保存 → 状态「已保存」+ localStorage 持久化；证据 = 交互 trace
observed: playwright 复验：save → status=已保存 + localStorage 含 dark 字段
result: pass

criterion: L6.5
required: 重置 → 确认对话框 → 确认后恢复默认；证据 = 交互 trace
observed: playwright 复验：confirm 对话框 accept → dark 恢复 false
result: pass

criterion: L6.6
required: 每开关 role=switch + 可访问名、label 关联、select 有名字；证据 = a11y 树
observed: evidence/L6.6-a11y.json
note: provider a11y capture；switch/aria-checked/aria-describedby/label for（源码核验）
result: pass

criterion: L6.7
required: 空态「暂无设置项」非空白；证据 = 状态截图
observed: playwright 复验：?empty=1 → 「暂无设置项 配置源未连接；请重载」+ 重载按钮
result: pass

## Findings

- issue: 重置使用原生 confirm() 对话框，视觉突兀且与页面主题不一致
  source: craft（craft-guard CRAFT finding）
  fix: 自绘确认弹层（复用主题令牌）替代原生 confirm；保留同语义
  severity: low
- issue: 语言切换仅更新头部标题（demo 范围），非完整 i18n
  source: spec（L1 非目标：语言预览 demo 范围）
  fix: 产品集成时接 i18n 基建；页面开关/分组结构不受影响
  severity: low

## Repairs (post-eval fixes, 2026-08-01)

- closes: 重置使用原生 confirm() 对话框，视觉突兀且与页面主题不一致 -> recirculate -> fix（自绘 `<dialog>` 主题弹层：showModal + Esc/取消/恢复默认，焦点 autofocus，::backdrop 遮罩）-> re-eval（dialog open + reset 生效）-> 0 open
- closes: 语言切换仅更新头部标题（demo 范围），非完整 i18n -> 接受：spec L1 非目标声明范围内，非缺陷（不开）

## Verdict

Pass

七条 L6 全 pass（4 条 provider 捕获 + 3 条 playwright 复验）；零 blocking；preview* 真实 HITL（Playwright 点击）确认 floor_pass=true，G5 满足；两项 low finding 点回 craft/spec 声明层，非阻断。
